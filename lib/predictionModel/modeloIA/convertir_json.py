import numpy as np
import json
from pathlib import Path

# Ruta al directorio
base = Path("lib/predictionModel/modeloIA")

# 1) pesos.npy  -> pesos.json  (lista: [W1, b1, W2, b2, W3, b3])
pesos = np.load(base / "pesos.npy", allow_pickle=True)
with open(base / "pesos.json", "w") as f:
    json.dump([p.tolist() for p in pesos], f, separators=(",", ":"))

# 2) escala.npz -> escala.json  (dict: {"mean": [...], "scale": [...]})
escala = np.load(base / "escala.npz")
with open(base / "escala.json", "w") as f:
    json.dump(
        {"mean": escala["mean"].tolist(), "scale": escala["scale"].tolist()},
        f, separators=(",", ":")
    )

print("OK: Generados pesos.json y escala.json")
