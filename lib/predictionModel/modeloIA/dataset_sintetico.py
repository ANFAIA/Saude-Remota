import pandas as pd
import numpy as np

#Fijar semilla para reproducibilidad
np.random.seed(42)

#Número de muestras sintéticas de riesgo
n = 100 

#Generar valores fuera de los rangos normales para provocar riesgo
heart_rate = np.concatenate([
    np.random.uniform(30, 55, size=n // 2),  #Muy bajos
    np.random.uniform(105, 140, size=n // 2) #Muy altos
])

spo2 = np.random.uniform(80, 94, size=n)  #Todos por debajo de 95

temperature = np.concatenate([
    np.random.uniform(34.0, 35.9, size=n // 2),  #Hipotermia
    np.random.uniform(37.6, 40.0, size=n // 2)   #Fiebre
])

#Todos los datos son de riesgo 1
riesgo = np.ones(n, dtype=int)

#Crear DataFrame
df_riesgo_1 = pd.DataFrame({
    "heart_rate": heart_rate,
    "spo2": spo2,
    "temperature": temperature,
    "riesgo": riesgo
})

#Guardar a CSV
df_riesgo_1.to_csv("lib/predictionModel/dataset/datos_sinteticos_riesgo_1.csv", index=False)

print("Datos sintéticos con riesgo 1 generados y guardados")
