import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers, regularizers
#Estas tres líneas importan TensorFlow y sus módulos de alto nivel (Keras), lo cual permite crear modelos de redes neuronales de forma sencilla
model = keras.Sequential([
    #Se crea un modelo secuencial (las capas se añaden una detrás de otra, en orden), ideal para redes neuronales simples como esta
    layers.Input(shape=(3,)),
    #La entrada del modelo son 3 valores (SpO₂, ritmo cardíaco y temperatura), el parámetro shape=(3,) define que cada dato de entrada será un vector de 3 números
    layers.Dense(32, activation='relu', kernel_regularizer=regularizers.l2(1e-4)),
    #Se añade una capa oculta con 16 neuronas, dense significa que todas las neuronas están conectadas a las anteriores (capa densa), activation='relu' aplica la función ReLU, que ayuda a que la red aprenda relaciones no lineales
    layers.Dropout(0.2),                     
    #Ayuda a evitar sobreajuste (el 20% de las neuronas de esa capa se desactivan aleatoriamente en cada iteración)
    layers.Dense(16, activation='relu', kernel_regularizer=regularizers.l2(1e-4)),
    #Otra capa igual que la anterior, tener dos capas le da más capacidad para aprender patrones complejos, a veces una sola capa no es suficiente para separar clases de forma correcta
    layers.Dropout(0.2),
    layers.Dense(1, activation='sigmoid')
    #Esta es la capa de salida, tiene 1 sola neurona porque es una clasificación binaria (riesgo o no riesgo), la activación sigmoid comprime la salida entre 0 y 1 (se interpreta como probabilidad)
])
#Cierra la definición del modelo secuencial
model.compile(optimizer=tf.keras.optimizers.Adam(1e-3), loss='binary_crossentropy', metrics=[tf.keras.metrics.AUC(curve='PR', name='pr_auc'),tf.keras.metrics.Recall(name='recall'),'accuracy'])
#Se compila el modelo, lo que significa que se prepara para ser entrenado, optimizer='adam' (método que ajusta los pesos de la red para que aprenda mejor), loss='binary_crossentropy' (función de error usada para clasificación binaria), metrics=['accuracy'] (para monitorizar qué tan bien acierta en las predicciones)
model.summary()
#Muestra un resumen del modelo con: número de capas, número de parámetros entrenables y forma de entrada/salida





