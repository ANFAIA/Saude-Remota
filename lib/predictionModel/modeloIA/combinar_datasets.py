import pandas as pd
from sklearn.utils import shuffle

# === 1. Cargar los tres archivos ===
demo = pd.read_csv("lib/predictionModel/dataset/mimic_demo_riesgo.csv")
human = pd.read_csv("lib/predictionModel/dataset/human_dataset_label.csv")
eicu = pd.read_csv("lib/predictionModel/dataset/eicu_dataset_procesado.csv")

# === 2. Renombrar columnas si hace falta ===
demo = demo.rename(columns={
    "hr": "heart_rate",
    "temp": "temperature",
    "spo2": "spo2",
    "riesgo": "label"
})
human = human.rename(columns={"riesgo": "label"})
eicu = eicu.rename(columns={"riesgo": "label"})

# Si algún dataset no tiene subject_id, se crea uno temporal único
for df, name in zip([demo, human, eicu], ["DEMO", "HUMAN", "EICU"]):
    if "subject_id" not in df.columns:
        df["subject_id"] = [f"{name}_{i}" for i in range(len(df))]

# === 3. Seleccionar columnas en común ===
cols = ["subject_id", "spo2", "heart_rate", "temperature", "label"]
demo = demo[cols]
human = human[cols]
eicu = eicu[cols]

# === 4. Combinar los tres datasets ===
df_total = pd.concat([demo, human, eicu], ignore_index=True)

# === 5. Mezclar filas (manteniendo aleatoriedad reproducible) ===
df_total = shuffle(df_total, random_state=42)

# === 6. Guardar dataset combinado ===
df_total.to_csv("lib/predictionModel/dataset/dataset_final_entrenamiento.csv", index=False)
print("Dataset combinado guardado como 'dataset_final_entrenamiento.csv'")

# === 7. Contar clases ===
conteo = df_total["label"].value_counts()
print("Riesgo 0:", conteo.get(0, 0))
print("Riesgo 1:", conteo.get(1, 0))
