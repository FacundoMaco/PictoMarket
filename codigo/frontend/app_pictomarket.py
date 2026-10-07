import base64
import json
import random
import re
import sys
import time
from pathlib import Path

import streamlit as st

RAIZ_PROYECTO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ_PROYECTO / "codigo"))
from backend import db  # noqa: E402
from ia_models import motor  # noqa: E402

RUTA_PICTOS = RAIZ_PROYECTO / "datos" / "pictogramas"
RUTA_ESCENARIOS = RAIZ_PROYECTO / "datos" / "escenarios.json"

COLUMNAS_MATRIZ = 3
MAX_FALLOS_DISCRETO = 3

st.set_page_config(page_title="PictoMarket", page_icon="🛒", layout="wide",
                   initial_sidebar_state="collapsed")

@st.cache_data
def cargar_datos(ruta: Path) -> dict:
    with open(ruta, encoding="utf-8") as f:
        datos = json.load(f)
    datos["catalogo"] = {int(k): v for k, v in datos["catalogo"].items()}
    return datos

DATOS = cargar_datos(RUTA_ESCENARIOS)
CATALOGO = DATOS["catalogo"]
CATEGORIAS = DATOS["categorias"]
RETOS = DATOS["retos"]

@st.cache_data
def url_pictograma(id_arasaac: int) -> str:
    """Pictograma local embebido (funciona sin internet); si falta, usa la URL de ARASAAC."""
    local = RUTA_PICTOS / f"{id_arasaac}.png"
    if local.exists():
        return "data:image/png;base64," + base64.b64encode(local.read_bytes()).decode()
    return DATOS["url_pictograma"].format(id=id_arasaac)

def palabras_objetivo(reto: dict) -> list:
    return re.findall(r"\[([^\]]+)\]", reto["objetivo"])

def iniciar_reto(indice: int) -> None:
    reto = RETOS[indice]
    matriz = list(reto["lista_correcta"]) + list(reto["distractores"])
    random.shuffle(matriz)

    ss = st.session_state
    ss.reto_idx = indice

    ss.items_restantes = list(reto["lista_correcta"])
    ss.items_en_carrito = []
    ss.intentos_fallidos = 0
    ss.nivel_pista = 0

    ss.productos_visibles = matriz      # posiciones fijas de la grilla
    ss.descartados = []                 # huecos: el descarte no reacomoda la grilla
    ss.monedas = reto["presupuesto"]
    ss.errores_totales = 0
    ss.celebrado = False
    ss.t_ultimo_evento = time.time()
    ss.log_eventos = []
    ss.setdefault("alias", "INVITADO")
    ss.setdefault("max_nivel", 3)
    con = db.conectar()
    ss.sesion_id = db.nueva_sesion(con, db.usuario_id(con, ss.alias), reto["id_reto"])
    con.close()
    ss.mensaje = {"tipo": "inicio",
                  "texto": f"¡HOLA! VAMOS A {' '.join(palabras_objetivo(reto))}. "
                           f"BUSCA: {CATALOGO[ss.items_restantes[0]]['nombre']}"}

def estado_actual() -> dict:
    ss = st.session_state
    return {
        "items_restantes": list(ss.items_restantes),
        "items_en_carrito": list(ss.items_en_carrito),
        "intentos_fallidos": min(ss.intentos_fallidos, MAX_FALLOS_DISCRETO),
        "nivel_pista": ss.nivel_pista,
    }

def item_objetivo():
    ss = st.session_state
    return ss.items_restantes[0] if ss.items_restantes else None

if "reto_idx" not in st.session_state:
    iniciar_reto(0)

def visibles_activos() -> list:
    ss = st.session_state
    return [p for p in ss.productos_visibles if p not in ss.descartados]

def al_tocar_producto(producto: int) -> None:
    ss = st.session_state
    reto = RETOS[ss.reto_idx]
    s_antes = estado_actual()
    objetivo = item_objetivo()
    h_antes = motor.entropia(visibles_activos(), CATALOGO)

    ahora = time.time()
    t_ms = int((ahora - ss.t_ultimo_evento) * 1000)
    ss.t_ultimo_evento = ahora

    accion = motor.politica(s_antes, producto, ss.max_nivel)
    nombre = CATALOGO[producto]["nombre"]
    eliminado = None

    if accion == "a0":
        ss.items_restantes.remove(producto)
        ss.items_en_carrito.append(producto)
        ss.monedas -= CATALOGO[producto]["precio"]
        ss.intentos_fallidos = 0
        ss.nivel_pista = 0
        sig = item_objetivo()
        ss.mensaje = {"tipo": "exito",
                      "texto": f"¡MUY BIEN! {nombre} VA AL CARRITO."
                               + (f" AHORA BUSCA: {CATALOGO[sig]['nombre']}" if sig else "")}
    else:
        ss.intentos_fallidos += 1
        ss.errores_totales += 1
        cat = CATEGORIAS[CATALOGO[objetivo]["categoria"]]
        if accion == "a2":
            eliminado, _ = motor.elegir_distractor(visibles_activos(), reto["distractores"],
                                                   CATALOGO, producto)
            if eliminado is None:
                accion = "a3"
            else:
                ss.descartados.append(eliminado)
        ss.nivel_pista = max(ss.nivel_pista, {"a1": 1, "a2": 2, "a3": 3}[accion])

        textos = {
            "a1": f"{nombre} NO ESTÁ EN LA LISTA. BUSCA EN {cat['icono']} {cat['nombre']}",
            "a2": f"QUITÉ UN PRODUCTO PARA AYUDARTE. ¡TÚ PUEDES!",
            "a3": f"MIRA 👉 AQUÍ ESTÁ {CATALOGO[objetivo]['nombre']}",
        }
        ss.mensaje = {"tipo": "pista", "texto": textos[accion]}

    h_despues = motor.entropia(visibles_activos(), CATALOGO)
    ss.log_eventos.append({
        "escenario_id": reto["id_reto"],
        "t_ms": t_ms,
        "item_objetivo": objetivo,
        "item_tocado": producto,
        "correcto": accion == "a0",
        "estado_s": s_antes,
        "accion_agente": accion,
        "distractor_eliminado": eliminado,
        "entropia_antes": round(h_antes, 3),
        "entropia_despues": round(h_despues, 3),
        "recompensa": None,
    })
    con = db.conectar()
    db.registrar_evento(con, ss.sesion_id, {
        "t_ms": t_ms, "item_objetivo": objetivo, "item_tocado": producto,
        "categoria_objetivo": CATALOGO[objetivo]["categoria"], "correcto": accion == "a0",
        "accion": accion, "distractor_eliminado": eliminado, "h_antes": h_antes,
        "h_despues": h_despues, "fuera_de_orden": accion == "a0" and producto != objetivo})
    if not ss.items_restantes:
        db.marcar_completada(con, ss.sesion_id)
    con.close()

CSS_BASE = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible:wght@400;700&display=swap');

:root {
  --fondo: #F9F6F0; --tinta: #1A1A1A; --tarjeta: #FFFFFF;
  --exito: #0B5D1E; --exito-suave: #DFF3E4;
  --pista: #3D2E00; --pista-suave: #FFF1C2;
  --sombra: 0 6px 0 rgba(26,26,26,.18), 0 14px 30px rgba(26,26,26,.10);
  --fuente: 'Atkinson Hyperlegible', Arial, Helvetica, sans-serif;
}

/* --- Ocultar la interfaz propia de Streamlit --- */
#MainMenu, header[data-testid="stHeader"], footer, [data-testid="stToolbar"],
[data-testid="stDecoration"], [data-testid="stStatusWidget"], .stDeployButton,
[data-testid="stSidebarCollapsedControl"] { visibility: hidden; display: none; }

.stApp { background: var(--fondo); }
.stApp, .stApp p, .stApp button, .stApp label, [class^="pm-"], [class*=" pm-"] {
  font-family: var(--fuente); color: var(--tinta); }
.block-container { padding: 1rem 2rem 1rem 2rem; max-width: 1500px; }

/* --- Barra superior (objetivo de la compra) --- */
.pm-barra { background: var(--tarjeta); border: 4px solid var(--tinta); border-radius: 20px;
  box-shadow: var(--sombra); padding: 12px 20px; display: flex; flex-wrap: wrap;
  align-items: flex-start; gap: 12px 20px; margin-bottom: 12px; }
.pm-logo { font-size: 26px; font-weight: 700; letter-spacing: 1px; white-space: nowrap; margin-top: 4px; }
.pm-frase { display: flex; gap: 8px; flex-wrap: wrap; }
.pm-chip { background: var(--pista-suave); border: 3px solid var(--tinta); border-radius: 10px;
  padding: 4px 12px; font-size: 24px; font-weight: 700; letter-spacing: 1px; }
.pm-lista { display: flex; gap: 10px; flex-wrap: wrap; margin-left: auto; }
.pm-mini { width: 84px; text-align: center; border: 3px solid var(--tinta); border-radius: 14px;
  padding: 4px 4px; background: #fff; position: relative; }
.pm-mini img { width: 56px; height: 56px; }
.pm-mini .t { font-size: 13px; font-weight: 700; line-height: 1.1; }
.pm-mini.hecho { background: var(--exito-suave); border-color: var(--exito); }
.pm-mini.hecho img { opacity: .55; }
.pm-mini.ahora { border-width: 5px; transform: scale(1.05); }
.pm-mini .marca { position: absolute; top: -10px; right: -10px; font-size: 20px; }
.pm-mini .ahora-txt { position: absolute; top: -12px; left: 50%; transform: translateX(-50%);
  background: var(--tinta); color: #fff !important; font-size: 11px; font-weight: 700;
  padding: 2px 6px; border-radius: 6px; white-space: nowrap; }

/* --- Burbuja del agente --- */
.pm-agente { display: flex; align-items: center; gap: 12px; border-radius: 18px;
  border: 3px solid var(--tinta); padding: 10px 16px; margin-bottom: 16px; }
.pm-agente .txt { font-size: 24px; font-weight: 700; line-height: 1.2; letter-spacing: .5px; }
.pm-agente.inicio { background: #fff; }
.pm-agente.exito  { background: var(--exito-suave); border-color: var(--exito); }
.pm-agente.pista  { background: var(--pista-suave); border-color: var(--pista); }

/* Fondo de supermercado para la app completa */
.stApp {
  background-color: #F1E8D9 !important; /* Marrón clarito */
}
/* Pasillos de fondo */
.stApp::before {
  content: ''; position: fixed; top: 0; left: 0; width: 100%; height: 100%;
  background-image: linear-gradient(90deg, rgba(255,255,255,0.4) 50%, transparent 50%);
  background-size: 120px 100%; z-index: -1; pointer-events: none;
}

/* --- Tarjetas de producto (estantes) --- */
div[class*="st-key-card_"] {
  background: transparent !important; border: none !important; box-shadow: none !important;
  padding: 0 !important; position: relative;
  min-height: 220px; transition: transform .12s ease; margin-bottom: 12px;
}
div[class*="st-key-card_"]:hover { transform: translateY(-4px); }
div[class*="st-key-card_"]:active { transform: translateY(2px); }

/* Contenedor del producto que se sienta en el estante */
.pm-card-wrapper {
  display: flex; flex-direction: column; align-items: center; justify-content: flex-end;
  height: 100%; width: 100%;
}
.pm-producto-area {
  display: flex; justify-content: center; align-items: flex-end;
  padding-bottom: 0px; width: 100%; z-index: 2; position: relative;
}
.pm-producto-area img {
  width: 100%; max-width: 130px; aspect-ratio: 1/1; object-fit: contain;
  filter: drop-shadow(0 6px 4px rgba(0,0,0,0.25));
}

/* El estante plano vectorizado */
.pm-estante-madera {
  width: 120%; /* Sobresale para unir las columnas */
  height: 18px;
  background: #DE9B52; /* Madera clara */
  border-bottom: 6px solid #A66A33; /* Sombra del borde */
  border-top: 2px solid #F3C391; /* Luz superior */
  position: relative; z-index: 1; margin-left: -10%;
}

/* Etiqueta de precio blanca */
.pm-etiqueta-precio {
  background: #FFFFFF; border: 3px solid #A66A33; border-radius: 8px;
  padding: 6px 12px; margin-top: -6px; position: relative; z-index: 5;
  box-shadow: 0 4px 8px rgba(0,0,0,0.15); text-align: center; min-width: 100px;
}
.pm-etiqueta-precio::before {
  content: ''; position: absolute; top: -10px; left: 50%; transform: translateX(-50%);
  width: 12px; height: 14px; background: #E0E0E0;
  border: 2px solid #808080; border-radius: 3px; z-index: -1;
}
.pm-etiqueta-precio .nombre {
  font-size: 16px; font-weight: 800; color: #5A3A22; text-transform: uppercase; line-height: 1.1; margin-bottom: 4px;
}
.pm-etiqueta-precio .precio { font-size: 20px; color: #1A1A1A; letter-spacing: 2px; display:flex; align-items:center; justify-content:center; gap:2px; }

.pm-badge { position: absolute; top: -20px; left: 50%; transform: translateX(-50%);
  color: #fff !important; font-size: 15px; font-weight: 700; padding: 4px 10px;
  border-radius: 10px; white-space: nowrap; z-index: 6; border: 2px solid var(--tinta); }

/* Moneda CSS */
.pm-moneda {
  display: inline-block; width: 18px; height: 18px; border-radius: 50%;
  background: #F2C454; border: 2px solid #C9962E;
  box-shadow: inset 0 0 0 2px rgba(255,255,255,0.4);
}
.pm-moneda-grande {
  display: inline-block; width: 32px; height: 32px; border-radius: 50%;
  background: #F2C454; border: 3px solid #C9962E;
  box-shadow: inset 0 0 0 3px rgba(255,255,255,0.4); margin: 0 2px;
}

/* El botón de Streamlit cubre TODA la tarjeta (objetivo táctil grande, WCAG 2.5.5) */
div[class*="st-key-card_"] div[class*="st-key-btn_"] {
  position: absolute; inset: 0; z-index: 4; margin: 0 !important; }
div[class*="st-key-card_"] div[class*="st-key-btn_"] * { width: 100%; height: 100%; }
div[class*="st-key-card_"] div[class*="st-key-btn_"] button {
  background: transparent !important; border: none !important; border-radius: 16px;
  color: transparent !important; cursor: pointer; box-shadow: none !important; }
div[class*="st-key-card_"] div[class*="st-key-btn_"] button p { color: transparent !important; }
div[class*="st-key-card_"] div[class*="st-key-btn_"] button:focus-visible {
  outline: 4px solid #004C99 !important; outline-offset: 4px; }
div[class*="st-key-card_"] div[class*="st-key-btn_"] button:disabled { cursor: default; }

/* --- Panel lateral: billetera y carrito --- */
.pm-panel { background: var(--tarjeta); border: 4px solid var(--tinta); border-radius: 20px;
  box-shadow: var(--sombra); padding: 12px 16px; margin-bottom: 16px; }
.pm-panel h3 { font-size: 20px; font-weight: 700; margin: 0 0 8px 0; letter-spacing: 1px; }
.pm-monedas { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 4px; }
.pm-monedas .gastada { filter: grayscale(1); opacity: .25; display:flex; gap:4px; }
.pm-cuenta { font-size: 18px; font-weight: 700; margin-top: 4px; }
.pm-carrito { display: flex; flex-wrap: wrap; gap: 8px; }
.pm-carrito .it { width: 72px; text-align: center; border: 2px solid var(--exito);
  border-radius: 12px; background: var(--exito-suave); padding: 4px 2px; }
.pm-carrito .it img { width: 48px; height: 48px; }
.pm-carrito .it .t { font-size: 11px; font-weight: 700; line-height: 1.1; }
.pm-vacio { font-size: 18px; font-weight: 700; opacity: .9; }

.pm-final { background: var(--exito-suave); border: 5px solid var(--exito); border-radius: 24px;
  box-shadow: var(--sombra); padding: 24px; text-align: center; margin-bottom: 16px; }
.pm-final .titulo { font-size: 36px; font-weight: 700; letter-spacing: 1px; }
.pm-final .fila { display: flex; justify-content: center; gap: 14px; flex-wrap: wrap; margin-top: 14px; }
.pm-final img { width: 100px; height: 100px; background: #fff; border-radius: 16px;
  border: 3px solid var(--exito); padding: 6px; }

.st-key-btn_siguiente button { background: var(--exito) !important; border: 3px solid var(--tinta) !important;
  border-radius: 18px !important; min-height: 64px; box-shadow: var(--sombra); }
.st-key-btn_siguiente button p { color: #fff !important; font-size: 24px !important; font-weight: 700; }

/* --- Panel del terapeuta (discreto) --- */
[data-testid="stExpander"] details { background: #fff; border: 2px solid #6b6b6b; border-radius: 14px; }

/* --- Pantallas pequeñas (tablet vertical / celular) --- */
@media (max-width: 640px) {
  .block-container { padding: .8rem 1rem 2rem 1rem; }
  .pm-barra { padding: 14px 16px; gap: 12px; }
  .pm-logo { font-size: 22px; }
  .pm-chip { font-size: 20px; padding: 4px 10px; }
  .pm-lista { margin-left: 0; }
  .pm-mini { width: 92px; } .pm-mini img { width: 56px; height: 56px; }
  .pm-mini .t { font-size: 12px; word-break: keep-all; }
  .pm-agente .ico { font-size: 34px; } .pm-agente .txt { font-size: 21px; }
  div[class*="st-key-card_"] { min-height: 240px; }
  .pm-card img { max-width: 160px; }
}

@media (prefers-reduced-motion: reduce) {
  * { animation: none !important; transition: none !important; }
}
@keyframes pm-pulso { 0%,100% { box-shadow: 0 0 0 0 rgba(11,93,30,.55); }
                      50% { box-shadow: 0 0 0 16px rgba(11,93,30,0); } }
</style>
"""

def css_dinamico() -> str:
    ss = st.session_state
    obj = item_objetivo()
    reglas = []
    if obj is not None and ss.nivel_pista >= 1:

        cat_obj = CATALOGO[obj]["categoria"]
        color = CATEGORIAS[cat_obj]["color"]
        for p in ss.productos_visibles:
            if CATALOGO[p]["categoria"] == cat_obj and p not in ss.items_en_carrito:
                reglas.append(f".st-key-card_{p} .pm-etiqueta-precio {{ border: 6px solid {color} !important; box-shadow: 0 0 15px {color}; }}")
    if obj is not None and ss.nivel_pista >= 3:

        reglas.append(f".st-key-card_{obj} .pm-etiqueta-precio {{ border: 8px solid var(--exito) !important;"
                      f" animation: pm-pulso 1.4s ease-in-out infinite; }}")
    for p in ss.items_en_carrito:
        reglas.append(f".st-key-card_{p} .pm-producto-area img {{ opacity: 0.3; filter: grayscale(1); }} "
                      f".st-key-card_{p} .pm-etiqueta-precio {{ opacity: 0.6; background: var(--exito-suave); border-color: var(--exito); }}")
    return "<style>" + "\n".join(reglas) + "</style>"

def html_monedas(cantidad: int, grande: bool = False) -> str:
    clase = "pm-moneda-grande" if grande else "pm-moneda"
    return "".join(f"<span class='{clase}'></span>" for _ in range(cantidad))

def barra_superior(reto: dict) -> None:
    ss = st.session_state
    obj = item_objetivo()
    chips = "".join(f"<span class='pm-chip'>{w}</span>" for w in palabras_objetivo(reto))
    minis = []
    for p in reto["lista_correcta"]:
        hecho = p in ss.items_en_carrito
        clase = "pm-mini hecho" if hecho else ("pm-mini ahora" if p == obj else "pm-mini")
        extra = "<span class='marca'>✅</span>" if hecho else (
            "<span class='ahora-txt'>AHORA</span>" if p == obj else "")
        minis.append(f"<div class='{clase}'>{extra}"
                     f"<img src='{url_pictograma(p)}' alt='{CATALOGO[p]['nombre']}'/>"
                     f"<div class='t'>{CATALOGO[p]['nombre']}</div></div>")
    st.markdown(
        f"<div class='pm-barra'><div class='pm-logo'>🛒 PICTOMARKET</div>"
        f"<div class='pm-frase'>{chips}</div>"
        f"<div class='pm-lista' role='list' aria-label='Lista de compras'>{''.join(minis)}</div></div>",
        unsafe_allow_html=True)

def burbuja_agente() -> None:
    m = st.session_state.mensaje
    st.markdown(f"<div class='pm-agente {m['tipo']}' role='status' aria-live='polite'>"
                f"<span class='txt'>{m['texto']}</span></div>",
                unsafe_allow_html=True)

def tarjeta_producto(producto: int) -> None:
    ss = st.session_state
    info = CATALOGO[producto]
    en_carrito = producto in ss.items_en_carrito
    obj = item_objetivo()

    insignia = ""
    if en_carrito:
        insignia = "<span class='pm-badge' style='background:#0B5D1E'>✅ EN EL CARRITO</span>"
    elif obj is not None and ss.nivel_pista >= 3 and producto == obj:
        insignia = "<span class='pm-badge' style='background:#0B5D1E'>👉 ¡ESTE!</span>"
    elif obj is not None and ss.nivel_pista >= 1 and info["categoria"] == CATALOGO[obj]["categoria"]:
        cat = CATEGORIAS[info["categoria"]]
        insignia = (f"<span class='pm-badge' style='background:{cat['color']}'>"
                    f"{cat['icono']} {cat['nombre']}</span>")

    with st.container(key=f"card_{producto}"):
        st.markdown(
            f"<div class='pm-card-wrapper'>"
            f"  <div class='pm-producto-area'>"
            f"    {insignia}"
            f"    <img src='{url_pictograma(producto)}' alt='{info['nombre']}'/>"
            f"  </div>"
            f"  <div class='pm-estante-madera'></div>"
            f"  <div class='pm-etiqueta-precio'>"
            f"    <div class='nombre'>{info['nombre']}</div>"
            f"    <div class='precio' aria-label='{info['precio']} monedas'>{html_monedas(info['precio'])}</div>"
            f"  </div>"
            f"</div>", unsafe_allow_html=True)
        st.button(info["nombre"], key=f"btn_{producto}", on_click=al_tocar_producto,
                  args=(producto,), disabled=en_carrito, use_container_width=True)

def matriz_productos() -> None:
    visibles = st.session_state.productos_visibles
    descartados = st.session_state.descartados
    for inicio in range(0, len(visibles), COLUMNAS_MATRIZ):
        cols = st.columns(COLUMNAS_MATRIZ, gap="large")
        for col, producto in zip(cols, visibles[inicio:inicio + COLUMNAS_MATRIZ]):
            with col:
                if producto in descartados:
                    st.markdown("<div style='min-height:240px'></div>", unsafe_allow_html=True)
                else:
                    tarjeta_producto(producto)
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

def panel_billetera(reto: dict) -> None:
    ss = st.session_state
    gastadas = reto["presupuesto"] - ss.monedas
    st.markdown(
        f"<div class='pm-panel'><h3>MI BILLETERA</h3>"
        f"<div class='pm-monedas' aria-hidden='true'><span>{html_monedas(ss.monedas, grande=True)}</span>"
        f"<span class='gastada'>{html_monedas(gastadas, grande=True)}</span></div>"
        f"<div class='pm-cuenta'>TENGO {ss.monedas} DE {reto['presupuesto']} MONEDAS</div></div>",
        unsafe_allow_html=True)

def panel_carrito() -> None:
    items = st.session_state.items_en_carrito
    if items:
        cuerpo = "".join(f"<div class='it'><img src='{url_pictograma(p)}' alt='{CATALOGO[p]['nombre']}'/>"
                         f"<div class='t'>{CATALOGO[p]['nombre']}</div></div>" for p in items)
        cuerpo = f"<div class='pm-carrito'>{cuerpo}</div>"
    else:
        cuerpo = "<div class='pm-vacio'>VACÍO</div>"
    st.markdown(f"<div class='pm-panel'><h3>MI CARRITO</h3>{cuerpo}</div>",
                unsafe_allow_html=True)

def pantalla_final(reto: dict) -> None:
    ss = st.session_state
    if not ss.celebrado:
        st.balloons()
        ss.celebrado = True
    fotos = "".join(f"<img src='{url_pictograma(p)}' alt='{CATALOGO[p]['nombre']}'/>"
                    for p in ss.items_en_carrito)
    st.markdown(f"<div class='pm-final'>"
                f"<div class='titulo'>¡LO LOGRASTE! COMPRASTE TODO</div>"
                f"<div class='fila'>{fotos}</div></div>", unsafe_allow_html=True)
    siguiente = (ss.reto_idx + 1) % len(RETOS)
    st.button("OTRA COMPRA", key="btn_siguiente", on_click=iniciar_reto,
              args=(siguiente,), use_container_width=True)

def panel_terapeuta() -> None:
    ss = st.session_state
    with st.expander("Panel del terapeuta"):
        st.selectbox("Escenario", options=range(len(RETOS)), index=ss.reto_idx,
                     format_func=lambda i: f"{RETOS[i]['id_reto']} (nivel {RETOS[i]['nivel']})",
                     key="selector_reto",
                     on_change=lambda: iniciar_reto(st.session_state.selector_reto))
        st.text_input("Usuario (alias, sin datos personales)", key="alias_input", value=ss.alias,
                      on_change=lambda: (st.session_state.update(alias=st.session_state.alias_input.strip().upper() or "INVITADO"),
                                         iniciar_reto(st.session_state.reto_idx)))
        st.select_slider("Ayuda máxima", options=[1, 2, 3], key="max_nivel",
                         format_func=lambda n: {1: "1 · categoría", 2: "2 · + descarte", 3: "3 · + demostración"}[n])
        st.button("Reiniciar escenario", on_click=iniciar_reto, args=(ss.reto_idx,))
        st.page_link("pages/1_Panel_terapeuta.py", label="📊 Progreso por usuario")
        st.caption(f"Errores totales: {ss.errores_totales}")
        st.caption("Estado s actual")
        st.json(estado_actual())
        st.caption("Log de eventos")
        st.json(ss.log_eventos, expanded=False)

st.markdown(CSS_BASE, unsafe_allow_html=True)
st.markdown(css_dinamico(), unsafe_allow_html=True)

reto_actual = RETOS[st.session_state.reto_idx]
barra_superior(reto_actual)

col_juego, col_lateral = st.columns([3.2, 1], gap="medium")

with col_juego:
    if not st.session_state.items_restantes:
        pantalla_final(reto_actual)
    else:
        burbuja_agente()
        matriz_productos()

with col_lateral:
    panel_billetera(reto_actual)
    panel_carrito()
    panel_terapeuta()

st.markdown("<p style='text-align:center;font-size:12px;margin-top:10px'>Pictogramas: Sergio Palao. "
            "Origen: ARASAAC (arasaac.org). Licencia CC BY-NC-SA. Propiedad: Gobierno de Aragón.</p>",
            unsafe_allow_html=True)
