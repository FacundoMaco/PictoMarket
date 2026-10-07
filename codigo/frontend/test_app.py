"""Smoke test del flujo completo con el runner nativo de Streamlit. Uso: python codigo/frontend/test_app.py"""
import tempfile
from pathlib import Path

from streamlit.testing.v1 import AppTest

RAIZ = Path(__file__).resolve().parents[2]
sys_db = RAIZ / "codigo"

import sys  # noqa: E402
sys.path.insert(0, str(sys_db))
from backend import db  # noqa: E402

db.RUTA_DB = Path(tempfile.mkdtemp()) / "t.db"   # BD aislada
db.conectar.__defaults__ = (db.RUTA_DB,)

at = AppTest.from_file(str(RAIZ / "codigo/frontend/app_pictomarket.py"), default_timeout=30).run()
assert not at.exception, at.exception
ss = at.session_state
objetivo = ss.items_restantes[0]

# 3 errores seguidos: a1, a2, a3 -> sin crash, un descarte y la grilla conserva posiciones
n_grilla = len(ss.productos_visibles)
for _ in range(3):
    tocado = next(p for p in ss.productos_visibles
                  if p not in ss.items_restantes and p not in ss.descartados and p not in ss.items_en_carrito)
    at.button(key=f"btn_{tocado}").click().run()
    assert not at.exception, at.exception
assert [e["accion_agente"] for e in ss.log_eventos] == ["a1", "a2", "a3"], ss.log_eventos
assert len(ss.productos_visibles) == n_grilla and len(ss.descartados) == 1

# completar la compra
while ss.items_restantes:
    at.button(key=f"btn_{ss.items_restantes[0]}").click().run()
    assert not at.exception, at.exception
assert ss.items_en_carrito and not ss.items_restantes

con = db.conectar()
fila = db.resumen_sesiones(con, "INVITADO")[0]
assert fila["completada"] and fila["errores"] == 3, fila
print("ok", fila)
