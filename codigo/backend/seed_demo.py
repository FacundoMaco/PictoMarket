"""Datos SINTÉTICOS de demostración (alias DEMO-*), generados con la política real del motor.

No son datos de personas. Uso: python codigo/backend/seed_demo.py
"""
import json
import random
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "codigo"))
from backend import db  # noqa: E402
from ia_models import motor  # noqa: E402

DATOS = json.load(open(RAIZ / "datos" / "escenarios.json", encoding="utf-8"))
CAT = {int(k): v for k, v in DATOS["catalogo"].items()}

# prob. de error inicial por compra y cuánto baja por sesión (el perfil es lo que se quiere mostrar)
PERFILES = {"DEMO-ANA": (0.65, 0.07), "DEMO-LUIS": (0.55, 0.0), "DEMO-SOFIA": (0.30, 0.03)}


def simular(con, alias, p0, mejora, sesiones=8, rng=random.Random(7)):
    uid = db.usuario_id(con, alias)
    dia = 86400
    for n in range(sesiones):
        reto = DATOS["retos"][n % len(DATOS["retos"])]
        sid = db.nueva_sesion(con, uid, reto["id_reto"], time.time() - (sesiones - n) * 2 * dia)
        visibles = list(reto["lista_correcta"]) + list(reto["distractores"])
        pend, p_err = list(reto["lista_correcta"]), max(p0 - mejora * n, 0.05)
        fallos = 0
        while pend:
            obj = pend[0]
            if rng.random() < p_err:
                tocado = rng.choice([p for p in visibles if p not in pend])
            else:
                tocado = obj
            estado = {"items_restantes": pend, "intentos_fallidos": fallos}
            accion = motor.politica(estado, tocado)
            h0, quitado = motor.entropia(visibles, CAT), None
            if accion == "a2":
                quitado, _ = motor.elegir_distractor(visibles, reto["distractores"], CAT, tocado)
                if quitado:
                    visibles = [p for p in visibles if p != quitado]
            db.registrar_evento(con, sid, {
                "t_ms": int(rng.gauss(6000 + 4000 * p_err, 1500)) , "item_objetivo": obj, "item_tocado": tocado,
                "categoria_objetivo": CAT[obj]["categoria"], "correcto": accion == "a0", "accion": accion,
                "distractor_eliminado": quitado, "h_antes": h0, "h_despues": motor.entropia(visibles, CAT),
                "fuera_de_orden": False})
            if accion == "a0":
                pend.remove(tocado)
                fallos = 0
            else:
                fallos += 1
        db.marcar_completada(con, sid)


if __name__ == "__main__":
    con = db.conectar()
    con.execute("DELETE FROM evento WHERE sesion_id IN (SELECT s.id FROM sesion s JOIN usuario u ON u.id=s.usuario_id WHERE u.alias LIKE 'DEMO-%')")
    con.execute("DELETE FROM sesion WHERE usuario_id IN (SELECT id FROM usuario WHERE alias LIKE 'DEMO-%')")
    con.commit()
    for alias, (p0, mejora) in PERFILES.items():
        simular(con, alias, p0, mejora)
    print("demo ok:", {a: len(db.resumen_sesiones(con, a)) for a in PERFILES})
