# PictoMarket

Agente de ayuda graduada para compras con pictogramas ARASAAC (Asociación Kallpa). Streamlit + SQLite.

```
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/streamlit run codigo/frontend/app_pictomarket.py
.venv/bin/python codigo/backend/seed_demo.py   # datos SINTÉTICOS DEMO-* para el panel
.venv/bin/python codigo/ia_models/test_motor.py && .venv/bin/python codigo/frontend/test_app.py
```

- `codigo/ia_models/motor.py`: política a0–a3 + ID3 (entropía de Shannon sobre categorías visibles; el descarte elige la mayor ganancia de información).
- `codigo/backend/db.py`: SQLite local (`datos/pictomarket.db`, ignorada por git). Solo alias, sin datos personales.
- `codigo/frontend/pages/1_Panel_terapeuta.py`: ayudas por compra, errores por categoría, latencia, bits.
- El descarte (a2) deja un hueco: la grilla no se reacomoda. El terapeuta fija la ayuda máxima (1–3).

Pictogramas: Sergio Palao, ARASAAC (arasaac.org), CC BY-NC-SA, Gobierno de Aragón. **Uso no comercial**: cualquier uso comercial requiere autorización de ARASAAC.
