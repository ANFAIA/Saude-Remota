# ============================
# 1. Importar librerías necesarias
# ============================
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from arquitectura import model
import tensorflow as tf
from imblearn.over_sampling import SMOTE
from sklearn.metrics import classification_report

# ============================
# 2. Cargar y preparar los datos
# ============================
df = pd.read_csv("lib/predictionModel/dataset/dataset_final_entrenamiento.csv")

X = df[["spo2", "heart_rate", "temperature"]].values
y = df["label"].values

# Escalar datos
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)

# Separar en entrenamiento y prueba
X_train, X_test, y_train, y_test = train_test_split(X_scaled, y, test_size=0.2, random_state=42)

# ============================
# 3. Preprocesamiento antes de SMOTE
# ============================
# Convertir a DataFrame para eliminar NaN
train_df = pd.DataFrame(X_train, columns=["spo2", "heart_rate", "temperature"])
train_df["label"] = y_train

# Eliminar filas con valores faltantes
train_df = train_df.dropna()

# Recuperar X_train y y_train limpios
X_train = train_df[["spo2", "heart_rate", "temperature"]].values
y_train = train_df["label"].values

# ============================
# 4. Aplicar SMOTE
# ============================
smote = SMOTE(random_state=42)
X_train_balanced, y_train_balanced = smote.fit_resample(X_train, y_train)

# ============================
# 5. Entrenar el modelo
# ============================
from tensorflow.keras.callbacks import EarlyStopping

early_stop = EarlyStopping(monitor='val_loss', patience=10, restore_best_weights=True)
epochs = 50
batch_size = 128

model.fit(
    X_train_balanced, y_train_balanced,
    epochs=epochs,
    batch_size=batch_size,
    validation_split=0.1,
    callbacks=[early_stop],
    verbose=1
)

# ============================
# 6. Evaluar el modelo
# ============================
loss, accuracy = model.evaluate(X_test, y_test)
print(f"Precisión en datos de prueba: {accuracy*100:.2f}%")
print(df['label'].value_counts())

y_pred = model.predict(X_test)
y_pred_classes = (y_pred > 0.5).astype(int)

print(classification_report(y_test, y_pred_classes))

# ============================
# 7. Guardar pesos y escala
# ============================
np.save("lib/predictionModel/modeloIA/pesos.npy", np.array(model.get_weights(), dtype=object), allow_pickle=True)
np.savez("lib/predictionModel/modeloIA/escala.npz", mean=scaler.mean_, scale=scaler.scale_)
