"""Persistencia local en SQLite. Solo alias (sin datos personales); la BD no sale de la máquina."""
import sqlite3
import time
from pathlib import Path
from statistics import median

RUTA_DB = Path(__file__).resolve().parents[2] / "datos" / "pictomarket.db"

ESQUEMA = """
CREATE TABLE IF NOT EXISTS usuario (id INTEGER PRIMARY KEY, alias TEXT UNIQUE NOT NULL, creado REAL NOT NULL);
CREATE TABLE IF NOT EXISTS sesion (
  id INTEGER PRIMARY KEY, usuario_id INTEGER NOT NULL REFERENCES usuario(id),
  escenario TEXT NOT NULL, inicio REAL NOT NULL, completada INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS evento (
  id INTEGER PRIMARY KEY, sesion_id INTEGER NOT NULL REFERENCES sesion(id),
  t_ms INTEGER, item_objetivo INTEGER, item_tocado INTEGER, categoria_objetivo TEXT,
  correcto INTEGER NOT NULL, accion TEXT NOT NULL, distractor_eliminado INTEGER,
  h_antes REAL, h_despues REAL, fuera_de_orden INTEGER NOT NULL DEFAULT 0);
"""


def conectar(ruta: Path = RUTA_DB) -> sqlite3.Connection:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(ruta)
    con.row_factory = sqlite3.Row
    con.executescript(ESQUEMA)
    return con


def usuario_id(con, alias: str) -> int:
    con.execute("INSERT OR IGNORE INTO usuario(alias, creado) VALUES (?, ?)", (alias, time.time()))
    con.commit()
    return con.execute("SELECT id FROM usuario WHERE alias=?", (alias,)).fetchone()["id"]


def nueva_sesion(con, uid: int, escenario: str, inicio: float | None = None) -> int:
    cur = con.execute("INSERT INTO sesion(usuario_id, escenario, inicio) VALUES (?,?,?)",
                      (uid, escenario, inicio or time.time()))
    con.commit()
    return cur.lastrowid


def registrar_evento(con, sesion_id: int, ev: dict) -> None:
    con.execute(
        "INSERT INTO evento(sesion_id,t_ms,item_objetivo,item_tocado,categoria_objetivo,correcto,accion,"
        "distractor_eliminado,h_antes,h_despues,fuera_de_orden) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (sesion_id, ev["t_ms"], ev["item_objetivo"], ev["item_tocado"], ev["categoria_objetivo"],
         int(ev["correcto"]), ev["accion"], ev["distractor_eliminado"], ev["h_antes"], ev["h_despues"],
         int(ev["fuera_de_orden"])))
    con.commit()


def marcar_completada(con, sesion_id: int) -> None:
    con.execute("UPDATE sesion SET completada=1 WHERE id=?", (sesion_id,))
    con.commit()


def usuarios(con) -> list:
    return [r["alias"] for r in con.execute("SELECT alias FROM usuario ORDER BY alias")]


def resumen_sesiones(con, alias: str) -> list:
    """Una fila por sesión: ayudas por compra, aciertos autónomos (0 ayudas), errores, latencia, bits."""
    filas = []
    sesiones = con.execute("SELECT s.* FROM sesion s JOIN usuario u ON u.id=s.usuario_id "
                           "WHERE u.alias=? ORDER BY s.inicio", (alias,)).fetchall()
    for s in sesiones:
        eventos = con.execute("SELECT * FROM evento WHERE sesion_id=? ORDER BY id", (s["id"],)).fetchall()
        ayudas, compras, autonomas, pend = [], 0, 0, 0
        for e in eventos:
            if e["correcto"]:
                compras += 1
                autonomas += pend == 0
                ayudas.append(pend)
                pend = 0
            else:
                pend += 1
        errores = sum(1 for e in eventos if not e["correcto"])
        bits = sum((e["h_antes"] or 0) - (e["h_despues"] or 0) for e in eventos if e["accion"] == "a2")
        latencias = [e["t_ms"] for e in eventos if e["t_ms"] is not None]
        filas.append({
            "sesion": s["id"], "fecha": time.strftime("%Y-%m-%d %H:%M", time.localtime(s["inicio"])),
            "escenario": s["escenario"], "completada": bool(s["completada"]), "compras": compras,
            "autonomas": autonomas, "ayudas_por_compra": round(sum(ayudas) / compras, 2) if compras else None,
            "errores": errores, "latencia_mediana_s": round(median(latencias) / 1000, 1) if latencias else None,
            "bits_descartados": round(bits, 2)})
    return filas


def errores_por_categoria(con, alias: str) -> dict:
    cur = con.execute(
        "SELECT e.categoria_objetivo c, COUNT(*) n FROM evento e JOIN sesion s ON s.id=e.sesion_id "
        "JOIN usuario u ON u.id=s.usuario_id WHERE u.alias=? AND e.correcto=0 GROUP BY c", (alias,))
    return {r["c"]: r["n"] for r in cur}
