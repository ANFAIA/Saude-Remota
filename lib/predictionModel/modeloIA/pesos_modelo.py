# pesos_modelo.py — versión MicroPython (sin numpy)
import math
import os

try:
    import ujson as json  # MicroPython
except ImportError:
    import json           # por si se ejecuta en CPython

# --- util path: carpeta donde está este archivo ---
def _this_dir():
    try:
        # MicroPython suele exponer __file__
        d = __file__
    except NameError:
        # fallback si no existe (poco probable en MP)
        d = ""
    if not d:
        return "."
    parts = d.split("/")
    return "/".join(parts[:-1]) or "."

_CUR = _this_dir()

def _load_json(name):
    with open("{}/{}".format(_CUR, name), "r") as f:
        return json.load(f)

# ==== 1. Cargar pesos y escalas desde JSON ====
# pesos.json: [W1, b1, W2, b2, W3, b3]
# escala.json: {"mean": [...], "scale": [...]}
_pesos = _load_json("lib/predictionModel/modeloIA/pesos.json")
W1, b1, W2, b2, W3, b3 = _pesos

_esc = _load_json("lib/predictionModel/modeloIA/escala.json")
mean = _esc["mean"]
scale = _esc["scale"]

# ==== 2. Funciones auxiliares ====
def standardize(x):
    # (x - mean) / scale
    return [(x[i] - mean[i]) / scale[i] for i in range(len(x))]

def relu(vec):
    return [v if v > 0 else 0 for v in vec]

def sigmoid(z):
    # cuidado con overflow en exp() si z es muy grande/pequeño
    if z >= 0:
        ez = math.exp(-z)
        return 1.0 / (1.0 + ez)
    else:
        ez = math.exp(z)
        return ez / (1.0 + ez)

def dot(W, x, b):
    """
    Multiplica W^T * x + b asumiendo que W está con forma (n_inputs x n_neuronas),
    es decir W[j][i] = peso desde entrada j a neurona i.
    """
    n_inputs = len(W)
    n_neuronas = len(W[0]) if n_inputs > 0 else 0
    out = []
    for i in range(n_neuronas):
        s = 0.0
        for j in range(n_inputs):
            s += x[j] * W[j][i]
        s += b[i]
        out.append(s)
    return out

# ==== 3. Inferencia ====
def predict(features):
    """
    features: lista [spo2, heart_rate, temperature]
    Devuelve: (clase, prob_riesgo)
    """
    # 1) estandarización
    x = standardize(features)

    # 2) capa 1
    a1 = relu(dot(W1, x, b1))

    # 3) capa 2
    a2 = relu(dot(W2, a1, b2))

    # 4) salida (neurona única)
    z3 = 0.0
    for i in range(len(a2)):
        z3 += a2[i] * W3[i][0]
    z3 += b3[0]
    p = sigmoid(z3)

    return (1 if p > 0.5 else 0, p)
