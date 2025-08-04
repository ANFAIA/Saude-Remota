import math
import numpy as np
import os

# ==== 1. Cargar pesos y biases dinámicamente ====
# Obtener la ruta del directorio actual del script
current_dir = os.path.dirname(os.path.abspath(__file__))

# Cargar pesos del modelo desde archivo .npy
pesos_path = os.path.join(current_dir, "pesos.npy")
pesos = np.load(pesos_path, allow_pickle=True)

# Extraer pesos y biases de cada capa
W1 = pesos[0].tolist()  # Primera capa - pesos
b1 = pesos[1].tolist()  # Primera capa - bias

W2 = pesos[2].tolist()  # Segunda capa - pesos
b2 = pesos[3].tolist()  # Segunda capa - bias

W3 = pesos[4].tolist()  # Tercera capa - pesos
b3 = pesos[5].tolist()  # Tercera capa - bias

# Cargar escalas del StandardScaler desde archivo .npz
escala_path = os.path.join(current_dir, "escala.npz")
escala = np.load(escala_path)

mean = escala["mean"].tolist()   # Media del StandardScaler
scale = escala["scale"].tolist() # Desviación típica del StandardScaler

# ==== 2. Funciones auxiliares ====
def standardize(x):
    return [(x[i] - mean[i]) / scale[i] for i in range(len(x))]

def relu(x):
    return [max(0, i) for i in x]

def sigmoid(x):
    return 1 / (1 + math.exp(-x))

def dot(W, x, b):
    """Multiplicación de matriz W (n_neuronas x n_entradas) * x + bias"""
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
