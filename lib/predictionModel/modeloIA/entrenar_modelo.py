# ============================
# 1. Importar librerías necesarias
# ============================
import numpy as np
import pandas as pd                                   # Para cargar y manipular datos tabulares
from sklearn.model_selection import train_test_split  # Para dividir los datos en entrenamiento y prueba
from sklearn.preprocessing import StandardScaler      # Para escalar los datos numéricos
from arquitectura import model                        # Importa la arquitectura definida en arquitectura.py
import tensorflow as tf                               # Para guardar el modelo en formato TFLite
from imblearn.over_sampling import SMOTE              # Para balancear las clases en el conjunto de entrenamiento

# ============================
# 2. Cargar y preparar los datos
# ============================
# Carga los datos preprocesados desde un archivo csv 
df = pd.read_csv("lib/predictionModel/dataset/dataset_final_entrenamiento.csv") 
# Eliminar filas con valores faltantes antes de aplicar SMOTE
df = df.dropna() 

# Separa las columnas de entrada (X) y la etiqueta objetivo (y)
X = df[["spo2", "heart_rate", "temperature"]].values   # Variables de entrada
y = df["label"].values                                 # Etiqueta: 0 = no riesgo, 1 = riesgo

# Escala las características para que tengan media 0 y desviación típica 1
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)

# Divide el conjunto de datos en entrenamiento (80%) y prueba (20%)
X_train, X_test, y_train, y_test = train_test_split(X_scaled, y, test_size=0.2, random_state=42)
# Se usa random_state = 42 por convención

# ============================
# 3. Aplicar SMOTE para balancear clases
# ============================
smote = SMOTE(random_state=42)
X_train_balanced, y_train_balanced = smote.fit_resample(X_train, y_train)

# ============================
# 4. Entrenar el modelo
# ============================
# Entrena el modelo usando los datos de entrenamiento
from tensorflow.keras.callbacks import EarlyStopping
early_stop = EarlyStopping(monitor='val_loss', patience=10, restore_best_weights=True)
#Esto evita quedarse con un modelo sobreentrenado
epochs = 50      # Número de veces que el modelo verá todos los datos de entrenamiento
batch_size = 128 # Número de muestras por lote de entrenamiento
model.fit(X_train, y_train, epochs=epochs, batch_size=batch_size, validation_split=0.1, callbacks=[early_stop], verbose=1)
# Parámetros comunes de entrenamiento en redes neuronales (epochs = 30, batch_size = 16 y validation_split = 0.2)

# ============================
# 5. Evaluar el modelo
# ============================
# Evalúa la precisión del modelo en los datos de prueba
loss, accuracy = model.evaluate(X_test, y_test)
print(f"Precisión en datos de prueba: {accuracy*100:.2f}%")
print(df['label'].value_counts())

from sklearn.metrics import classification_report

y_pred = model.predict(X_test)
y_pred_classes = (y_pred > 0.5).astype(int)

print(classification_report(y_test, y_pred_classes))

# ============================
# 6. Guardar el modelo
# ============================

weights = model.get_weights()
np.save("lib/predictionModel/modeloIA/pesos.npy", np.array(weights, dtype=object), allow_pickle=True)

np.savez("lib/predictionModel/modeloIA/escala.npz", mean=scaler.mean_, scale=scaler.scale_)
