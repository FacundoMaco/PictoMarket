from motor import elegir_distractor, entropia, ganancia_quitar, politica

CAT = {
    1: {"categoria": "A"}, 2: {"categoria": "A"}, 3: {"categoria": "A"},
    4: {"categoria": "B"}, 5: {"categoria": "B"}, 6: {"categoria": "C"},
}


def test_entropia():
    assert entropia([], CAT) == 0.0
    assert entropia([1, 2], CAT) == 0.0                      # una sola categoría
    assert abs(entropia([1, 4], CAT) - 1.0) < 1e-9           # 50/50 = 1 bit


def test_id3_quita_el_que_mas_reduce_incertidumbre():
    visibles = [1, 2, 3, 4, 5, 6]                            # (3,2,1)
    prod, bits = elegir_distractor(visibles, [3, 5, 6], CAT, tocado=3)
    assert prod == 6 and bits > 0                            # quitar la categoría solitaria
    assert ganancia_quitar(visibles, 3, CAT) < 0             # quitar de la mayoritaria sube H


def test_id3_empate_prefiere_tocado():
    assert elegir_distractor([1, 4, 5, 6], [4, 5], CAT, tocado=5)[0] == 5


def test_politica():
    e = {"items_restantes": [1], "intentos_fallidos": 0}
    assert politica(e, 1) == "a0"
    assert [politica({**e, "intentos_fallidos": n}, 9) for n in (0, 1, 2, 3)] == ["a1", "a2", "a3", "a3"]
    assert politica({**e, "intentos_fallidos": 2}, 9, max_nivel=2) == "a2"


if __name__ == "__main__":
    for nombre, fn in list(globals().items()):
        if nombre.startswith("test_"):
            fn()
    print("ok")
