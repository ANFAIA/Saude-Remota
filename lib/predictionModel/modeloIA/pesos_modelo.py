import math
import ujson  # MicroPython usa ujson en vez de json

# ==== 1. Cargar pesos y biases desde archivo JSON ====
PESOS_PATH = "/lib/predictionModel/modeloIA/pesos.json"
ESCALA_PATH = "/lib/predictionModel/modeloIA/escala.json"

def _load_json(path):
    with open(path) as f:
        return ujson.load(f)

# Cargar pesos (lista)
pesos = _load_json(PESOS_PATH)
W1 = pesos[0]
b1 = pesos[1]
W2 = pesos[2]
b2 = pesos[3]
W3 = pesos[4]
b3 = pesos[5]

# Cargar escalas (diccionario)
escala = _load_json(ESCALA_PATH)
mean = escala["mean"]
scale = escala["scale"]

# ==== 2. Funciones auxiliares ====
def standardize(x):
    return [(x[i] - mean[i]) / scale[i] for i in range(len(x))]

def relu(x):
    return [max(0, i) for i in x]

def sigmoid(x):
    return 1 / (1 + math.exp(-x))

def dot(W, x, b):
    """Multiplicación de matriz W (n_entradas x n_neuronas) * x + bias"""
    result = []
    for i in range(len(W[0])):  # para cada neurona
        s = 0
        for j in range(len(x)):
            s += x[j] * W[j][i]
        s += b[i]
        result.append(s)
    return result

# ==== 3. Función de inferencia ====
def predict(features):
    # Estandarizar entrada
    x = standardize(features)

    # Capa 1
    z1 = dot(W1, x, b1)
    a1 = relu(z1)

    # Capa 2
    z2 = dot(W2, a1, b2)
    a2 = relu(z2)

    # Capa 3 (salida)
    z3 = 0
    for i in range(len(a2)):
        z3 += a2[i] * W3[i][0]
    z3 += b3[0]
    y = sigmoid(z3)

    # Umbral de clasificación
    return 1 if y > 0.5 else 0, y
