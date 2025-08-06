import pandas as pd
from sklearn.utils import shuffle

#Cargar los dos archivos
demo = pd.read_csv("lib/predictionModel/dataset/mimic_demo_riesgo.csv")
human = pd.read_csv("lib/predictionModel/dataset/human_dataset_label.csv")

#Renombrar columnas si hace falta
demo = demo.rename(columns={
    "hr": "heart_rate",
    "temp": "temperature",
    "spo2": "spo2",
    "riesgo": "label"
})
human = human.rename(columns={"riesgo": "label"})

#Seleccionar columnas en común
cols = ["spo2", "heart_rate", "temperature", "label"]
demo = demo[cols]
human = human[cols]

#Combinar los dos datasets
df_total = pd.concat([demo, human], ignore_index=True)

#Mezclar las filas para que no estén ordenadas por tipo
df_total = shuffle(df_total, random_state=42)

#Guardar el archivo combinado
df_total.to_csv("lib/predictionModel/dataset/dataset_final_entrenamiento.csv", index=False)
print("Dataset combinado guardado como 'dataset_final_entrenamiento.csv'")
