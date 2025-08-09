import pandas as pd
from pathlib import Path

# ===== 1) Rutas =====
base = Path("lib/predictionModel/dataset/eicu-collaborative-research-database-demo-2.0")
p_periodic   = base / "vitalPeriodic.csv.gz"
p_aperiodic  = base / "vitalAperiodic.csv.gz"

print(f"Leyendo: {p_periodic.name}, {p_aperiodic.name}")
vp = pd.read_csv(p_periodic)
va = pd.read_csv(p_aperiodic)

# Helper: búsqueda tolerante por alias (ignora mayúsculas/minúsculas)
def pick_col(df, aliases):
    cols = {c.lower(): c for c in df.columns}
    for a in aliases:
        if a.lower() in cols:
            return cols[a.lower()]
    return None

# Aliases habituales en eICU (y variantes)
ALIASES = {
    "heart_rate":  ["heartRate", "heartrate", "hr", "pulse", "pulseRate"],
    "spo2":        ["spo2", "o2saturation", "sao2", "oxygensaturation", "O2Sat"],
    "temperature": ["temperature", "tempc", "temperaturec", "temp", "temperatureF", "tempf"],
}

def extract_signals(df, origin_name):
    out = {}
    found = {}
    for k, aliases in ALIASES.items():
        col = pick_col(df, aliases)
        if col:
            out[k] = col
            found[k] = f"{origin_name}.{col}"
    return out, found

map_vp, found_vp = extract_signals(vp, "vitalPeriodic")
map_va, found_va = extract_signals(va, "vitalAperiodic")

print("Encontradas en vitalPeriodic:", found_vp or "-")
print("Encontradas en vitalAperiodic:", found_va or "-")

frames = []

if map_vp:
    cols = ["patientunitstayid"] + [map_vp.get(k) for k in map_vp]
    df_vp = vp[cols].copy()
    df_vp.rename(columns={
        map_vp.get("heart_rate",  None): "heart_rate",
        map_vp.get("spo2",        None): "spo2",
        map_vp.get("temperature", None): "temperature",
    }, inplace=True)
    frames.append(df_vp)

if map_va:
    cols = ["patientunitstayid"] + [map_va.get(k) for k in map_va]
    df_va = va[cols].copy()
    df_va.rename(columns={
        map_va.get("heart_rate",  None): "heart_rate",
        map_va.get("spo2",        None): "spo2",
        map_va.get("temperature", None): "temperature",
    }, inplace=True)
    frames.append(df_va)

if not frames:
    raise RuntimeError("No se encontraron señales en ninguna tabla.")

# Unir y quedarnos solo con columnas de interés
vitals = pd.concat(frames, ignore_index=True)

# ——— REQUISITO: las tres señales deben existir en el dataset ———
required = {"heart_rate", "spo2", "temperature"}
missing_signals = required.difference(vitals.columns)
if missing_signals:
    raise RuntimeError(
        f"Faltan señales requeridas en los CSV: {sorted(missing_signals)}. "
        "Revisa los alias o la demo descargada."
    )

vitals = vitals[["patientunitstayid", "heart_rate", "spo2", "temperature"]]

# Quitar filas totalmente vacías (por si hay registros sin ninguna señal)
vitals.dropna(how="all", subset=["heart_rate", "spo2", "temperature"], inplace=True)

# Promedio por paciente
df_avg = vitals.groupby("patientunitstayid").mean(numeric_only=True).reset_index()

# ——— FILTRO FINAL: solo pacientes con las 3 señales presentes ———
df_avg = df_avg.dropna(subset=["heart_rate", "spo2", "temperature"], how="any")

# Clasifica riesgo 
def clasifica_riesgo(row):
    hr, sp, tc = row["heart_rate"], row["spo2"], row["temperature"]
    return int((hr > 90 or hr < 60) or (sp < 95) or (tc > 37.5 or tc < 36))

df_avg["riesgo"] = df_avg.apply(clasifica_riesgo, axis=1)

# Renombrar ID y exportar
df_avg.rename(columns={"patientunitstayid": "subject_id"}, inplace=True)
df_final = df_avg[["subject_id", "heart_rate", "spo2", "temperature", "riesgo"]].copy()

out_path = Path("lib/predictionModel/dataset/eicu_dataset_procesado.csv")
df_final.to_csv(out_path, index=False)

print(f"✅ Guardado: {out_path}  (pacientes con 3 señales={len(df_final)})")
print(df_final.head())
