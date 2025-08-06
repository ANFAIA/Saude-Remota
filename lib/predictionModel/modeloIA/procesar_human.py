import pandas as pd

# Cargar el dataset
df = pd.read_csv("lib/predictionModel/dataset/human_dataset_riesgo.csv")

# Asegurarse de que los nombres estén en minúscula por consistencia
df.columns = df.columns.str.lower()

# Eliminar columna 'riesgo' si existe
if 'riesgo' in df.columns:
    df.drop(columns=['riesgo'], inplace=True)

# Crear columna 'label' según tus criterios
def clasifica_riesgo(row):
    return int(
        (row.get('heart_rate', 0) > 90) or
        (row.get('heart_rate', 0) < 60) or
        (row.get('spo2', 100) < 95) or
        (row.get('temperature', 0) > 37.5) or
        (row.get('temperature', 0) < 36)
    )

df["label"] = df.apply(clasifica_riesgo, axis=1)

# Dejar sólo las columnas relevantes
df = df[["subject_id", "spo2", "heart_rate", "temperature", "label"]]

# Guardar el nuevo archivo
df.to_csv("lib/predictionModel/dataset/human_dataset_label.csv", index=False)
