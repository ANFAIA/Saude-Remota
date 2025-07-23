import pandas as pd
from sklearn.utils import shuffle

#Cargar los dos archivos
demo = pd.read_csv("mimic_demo_riesgo.csv")
riesgo_1 = pd.read_csv("datos_sinteticos_riesgo_1.csv")

#Renombrar columnas si hace falta
demo = demo.rename(columns={
    "hr": "heart_rate",
    "temp": "temperature",
    "spo2": "spo2",
    "riesgo": "label"
})
riesgo_1 = riesgo_1.rename(columns={"riesgo": "label"})

#Seleccionar columnas en común
cols = ["spo2", "heart_rate", "temperature", "label"]
demo = demo[cols]
riesgo_1 = riesgo_1[cols]

#Combinar los dos datasets
df_total = pd.concat([demo, riesgo_1], ignore_index=True)

#Mezclar las filas para que no estén ordenadas por tipo
df_total = shuffle(df_total, random_state=42)

#Guardar el archivo combinado
df_total.to_csv("dataset_final_entrenamiento.csv", index=False)
print("Dataset combinado guardado como 'dataset_final_entrenamiento.csv'")
