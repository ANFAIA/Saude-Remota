import pandas as pd
#Importa la librería pandas, que sirve para manipular datos tabulares (como los csv)
items = pd.read_csv("mimic-iv-clinical-database-demo-2.2/icu/d_items.csv.gz", compression="gzip")
chartevents = pd.read_csv("mimic-iv-clinical-database-demo-2.2/icu/chartevents.csv.gz", compression="gzip")
patients = pd.read_csv("mimic-iv-clinical-database-demo-2.2/hosp/patients.csv.gz", compression="gzip")
#Carga tres archivos del dataset MIMIC-IV demo: chartevents.csv (contiene miles de registros de signos vitales por paciente), d_items.csv y patients.csv (tiene datos básicos por paciente)
ITEMID_MAP = {
    220045: 'heart_rate',      
    220277: 'spo2',            
    223761: 'temperature'      
}
#Define qué itemid corresponde a qué variable, esto se extrae del diccionario d_items.csv
vitals = chartevents[chartevents['itemid'].isin(ITEMID_MAP.keys())].copy()
#vitals selecciona sOlo las filas que contienen los itemid de las variables que interesan
vitals['label'] = vitals['itemid'].map(ITEMID_MAP)
#vitals['label'] crea una nueva columna llamada label con el nombre legible de la variable 
temp_idx = (vitals['itemid'] == 223761) & (vitals['valuenum'] > 80)
vitals.loc[temp_idx, 'valuenum'] = (vitals.loc[temp_idx, 'valuenum'] - 32) * (5/9)
#Convertir temperaturas sospechosamente altas (>80) de Fahrenheit a Celsius
pivot = (vitals
         .groupby(['subject_id', 'label'])['valuenum']
         .mean()
         .unstack())
#Agrupa por subject_id (paciente) y label (variable), y calcula el promedio de los valores (valuenum), como resultado se obtiene una tabla con una fila por paciente y una columna por variable
pivot = pivot.dropna(thresh=2)
#Elimina a los pacientes que tengan menos de 2 de las 3 variables disponibles (para no trabajar con datos demasiado incompletos)
def clasifica_riesgo(row):
    return int(
        (row.get('heart_rate', 0) > 100) or
        (row.get('heart_rate', 0) < 60) or
        (row.get('spo2', 100) < 95) or
        (row.get('temperature', 0) > 37.5) or
        (row.get('temperature', 0) < 36)
    )
pivot['riesgo'] = pivot.apply(clasifica_riesgo, axis=1)
#Define una función que analiza cada fila y devuelve: 1 (riesgo) si frecuencia cardíaca > 100 o SpO₂ < 95 o temperatura > 37.5 °C, y 0 si todo está dentro del rango normal, aplica la función a cada fila del DataFrame (axis=1) y guarda el resultado en la nueva columna riesgo
pivot.to_csv("mimic_demo_riesgo.csv")
print("Archivo mimic_demo_riesgo.csv creado con éxito.")
#Guarda el DataFrame procesado en un nuevo archivo mimic_demo_riesgo.csv y muestra un mensaje en consola para confirmar que todo fue bien


