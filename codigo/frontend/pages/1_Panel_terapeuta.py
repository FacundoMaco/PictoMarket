import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "codigo"))
from backend import db  # noqa: E402

st.set_page_config(page_title="PictoMarket · Panel del terapeuta", page_icon="📊", layout="wide")
st.title("📊 Panel del terapeuta")
st.page_link("app_pictomarket.py", label="← Volver al juego")

con = db.conectar()
alias = st.selectbox("Usuario", db.usuarios(con))
if not alias:
    st.info("Aún no hay sesiones. Juega una compra o genera datos de demostración: "
            "`python codigo/backend/seed_demo.py`")
    st.stop()
if alias.startswith("DEMO-"):
    st.warning("Datos sintéticos de demostración, generados con la política real del agente. No son personas.")

filas = db.resumen_sesiones(con, alias)
if not filas:
    st.info("Este usuario aún no tiene sesiones.")
    st.stop()
df = pd.DataFrame(filas)
hechas = df[df["compras"] > 0]
if hechas.empty:
    st.info("Este usuario aún no completó ninguna compra. El progreso aparece desde la primera.")
    st.stop()

c1, c2, c3, c4 = st.columns(4)
c1.metric("Sesiones", len(df))
c2.metric("Compras autónomas (sin ayuda)", f"{int(hechas['autonomas'].sum())}/{int(hechas['compras'].sum())}")
c3.metric("Ayudas por compra (última)", hechas["ayudas_por_compra"].iloc[-1],
          delta=round(hechas["ayudas_por_compra"].iloc[-1] - hechas["ayudas_por_compra"].iloc[0], 2)
          if len(hechas) > 1 else None, delta_color="inverse")
c4.metric("Latencia mediana (s)", hechas["latencia_mediana_s"].median())

g1, g2 = st.columns(2)
with g1:
    st.subheader("Ayudas por compra, por sesión")
    st.caption("Baja = más autonomía (retirada gradual de ayudas).")
    st.line_chart(df.set_index("sesion")["ayudas_por_compra"])
with g2:
    st.subheader("Errores por categoría del objetivo")
    st.caption("Dónde se confunde: categorías a reforzar.")
    errores = db.errores_por_categoria(con, alias)
    if errores:
        st.bar_chart(pd.Series(errores, name="errores"))
    else:
        st.write("Sin errores registrados.")

st.subheader("Sesiones")
st.dataframe(df.drop(columns=["sesion"]), hide_index=True, width='stretch')
st.caption("Bits descartados = reducción de entropía visual por las pistas de descarte (ID3).")
