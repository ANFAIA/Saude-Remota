import numpy as np

# === Cargar pesos ===
pesos = np.load("lib/predictionModel/modeloIA/pesos.npy", allow_pickle=True)

print("===== Pesos y Bias =====\n")
for i, p in enumerate(pesos):
    print(f"Pesos[{i}]:")
    print(p.tolist())  # lo convierte a lista para usar en MicroPython
    print()

# === Cargar media y escala del StandardScaler ===
escala = np.load("lib/predictionModel/modeloIA/escala.npz")

print("===== Media (mean) =====")
print(escala["mean"].tolist())  # [spo2_mean, hr_mean, temp_mean]

print("\n===== Escala (std) =====")
print(escala["scale"].tolist())  # [spo2_std, hr_std, temp_std]
