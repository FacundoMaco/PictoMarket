"""Motor de decisión de PictoMarket: política de ayuda graduada + ID3 (entropía de Shannon).

Puro Python, sin Streamlit, para poder probarlo y reutilizarlo desde el panel.
"""
import math
from collections import Counter


def entropia(items: list, catalogo: dict, atributo: str = "categoria") -> float:
    """H(D) = -sum p_i log2 p_i sobre la distribución del atributo en los productos visibles."""
    n = len(items)
    if n == 0:
        return 0.0
    cuentas = Counter(catalogo[i][atributo] for i in items)
    return -sum((c / n) * math.log2(c / n) for c in cuentas.values())


def ganancia_quitar(visibles: list, candidato: int, catalogo: dict, atributo: str = "categoria") -> float:
    """Ganancia de información (bits) de descartar `candidato`: H(antes) - H(después)."""
    despues = [i for i in visibles if i != candidato]
    return entropia(visibles, catalogo, atributo) - entropia(despues, catalogo, atributo)


def elegir_distractor(visibles: list, distractores: list, catalogo: dict, tocado: int):
    """Distractor visible con mayor ganancia de información (ID3 voraz). Empate: el que tocó el usuario.

    Devuelve (producto, bits_ganados) o (None, 0.0) si no quedan distractores.
    """
    candidatos = [p for p in visibles if p in distractores]
    if not candidatos:
        return None, 0.0
    mejor = max(candidatos, key=lambda p: (round(ganancia_quitar(visibles, p, catalogo), 9), p == tocado))
    return mejor, ganancia_quitar(visibles, mejor, catalogo)


def politica(estado: dict, tocado: int, max_nivel: int = 3) -> str:
    """a0 aprueba; si hay error escala a1 (categoría) -> a2 (descarte) -> a3 (demostración).

    `max_nivel` lo fija el terapeuta: 1 = solo categoría, 2 = hasta descarte, 3 = hasta demostración.
    """
    if tocado in estado["items_restantes"]:
        return "a0"
    escala = min(estado["intentos_fallidos"], 2) + 1
    return f"a{min(escala, max_nivel)}"
