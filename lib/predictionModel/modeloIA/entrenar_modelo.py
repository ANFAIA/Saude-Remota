# ============================
# Split por paciente + chequeos
# ============================
import numpy as np
import pandas as pd
from sklearn.model_selection import GroupShuffleSplit
from sklearn.preprocessing import StandardScaler
from sklearn.utils.class_weight import compute_class_weight
from sklearn.metrics import classification_report
from arquitectura import model   # tu modelo Keras
import tensorflow as tf

# ---- 1) Cargar y limpiar ----
RUTA = "lib/predictionModel/dataset/dataset_final_entrenamiento.csv"
df = pd.read_csv(RUTA)

# columnas necesarias (ajusta si el ID de paciente tiene otro nombre)
PAC_COL = "subject_id"          
FEATS   = ["spo2", "heart_rate", "temperature"]
TARGET  = "label"

faltan = [c for c in [PAC_COL, *FEATS, TARGET] if c not in df.columns]
if faltan:
    raise ValueError(f"Faltan columnas requeridas: {faltan}")

df = df[[PAC_COL, *FEATS, TARGET]].dropna().copy()
df[TARGET] = df[TARGET].astype(int)

# ---- 2) Split por paciente (sin fuga entre grupos) ----
groups = df[PAC_COL].values
gss = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
train_idx, test_idx = next(gss.split(df, groups=groups))

train_df = df.iloc[train_idx].reset_index(drop=True)
test_df  = df.iloc[test_idx].reset_index(drop=True)

print("Pacientes únicos en train:", train_df[PAC_COL].nunique())
print("Pacientes únicos en test :", test_df[PAC_COL].nunique())
print("¿Intersección de pacientes?", 
      len(set(train_df[PAC_COL]) & set(test_df[PAC_COL])))

# ---- 3) Chequeo de duplicados EXACTOS entre splits (por si hubiera) ----
def row_hash(frame, cols):
    # hash rápido por fila en las columnas relevantes
    return pd.util.hash_pandas_object(frame[cols], index=False)

cols_chequeo = FEATS + [TARGET]
h_train = set(row_hash(train_df, cols_chequeo))
h_test  = set(row_hash(test_df,  cols_chequeo))
overlap = len(h_train & h_test)
print(f"Filas idénticas (features+label) presentes en train y test: {overlap}")

# ---- 4) Preparar X/y y escalar SIN fuga ----
X_train = train_df[FEATS].values
y_train = train_df[TARGET].values
X_test  = test_df[FEATS].values
y_test  = test_df[TARGET].values

scaler = StandardScaler()
X_train = scaler.fit_transform(X_train)   # fit SOLO en train
X_test  = scaler.transform(X_test)

# ---- 5) Class weights (sin SMOTE) ----
classes = np.unique(y_train)
weights = compute_class_weight(class_weight="balanced", classes=classes, y=y_train)
class_weight = dict(zip(classes, weights))
print("class_weight:", class_weight)

# ---- 6) Entrenar ----
callbacks = [
    tf.keras.callbacks.EarlyStopping(monitor='val_pr_auc', mode='max',
                                     patience=8, restore_best_weights=True),
    tf.keras.callbacks.ReduceLROnPlateau(monitor='val_pr_auc', mode='max',
                                         factor=0.5, patience=3, min_lr=1e-5),
]

model.compile(
    optimizer=tf.keras.optimizers.Adam(1e-3),
    loss='binary_crossentropy',
    metrics=[tf.keras.metrics.AUC(curve='PR', name='pr_auc'),
             tf.keras.metrics.Recall(name='recall'),
             'accuracy']
)

history = model.fit(
    X_train, y_train,
    epochs=50,
    batch_size=1024,
    validation_split=0.1,
    callbacks=callbacks,
    class_weight=class_weight,
    verbose=1
)

# ---- 7) Evaluar ----
loss, acc, pr_auc, rec = model.evaluate(X_test, y_test, verbose=0)
print(f"\nTest  | acc={acc:.3f}  pr_auc={pr_auc:.3f}  recall={rec:.3f}")

y_prob = model.predict(X_test, verbose=0).ravel()
y_pred = (y_prob >= 0.5).astype(int)
print("\nReporte de clasificación:\n", classification_report(y_test, y_pred, digits=3))

# ---- 8) Guardar pesos y escala ----
np.save("lib/predictionModel/modeloIA/pesos.npy",
        np.array(model.get_weights(), dtype=object), allow_pickle=True)
np.savez("lib/predictionModel/modeloIA/escala.npz",
         mean=scaler.mean_, scale=scaler.scale_)
