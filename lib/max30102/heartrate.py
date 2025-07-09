import time

## @class HeartRate
#  @brief Clase para procesar señales de un sensor óptico de frecuencia cardíaca y detectar latidos.
#
#  Utiliza un estimador de componente DC y un filtro FIR de paso bajo para aislar la señal AC. La detección de latidos
#  se basa en el análisis de flancos de cruce por cero y umbrales dinámicos.
class HeartRate:
    ## @brief Coeficientes del filtro FIR (12 taps simétricos).
    FIR_COEFFS = [172, 321, 579, 927, 1360, 1858, 2390, 2916, 3391, 3768, 4012, 4096]
    
    ## @brief Tamaño del buffer circular para el FIR.
    BUF_SIZE = 32

    ## @brief Constructor de la clase. Inicializa todos los registros y buffers necesarios.
    def __init__(self):
        ## @brief Valor máximo actual de la señal AC IR.
        self.IR_AC_Max = 20
        ## @brief Valor mínimo actual de la señal AC IR.
        self.IR_AC_Min = -20

        ## @brief Valor actual de la señal AC filtrada.
        self.IR_AC_Signal_Current = 0
        ## @brief Valor previo de la señal AC filtrada.
        self.IR_AC_Signal_Previous = 0
        ## @brief Mínimo local detectado durante la fase negativa.
        self.IR_AC_Signal_min = 0
        ## @brief Máximo local detectado durante la fase positiva.
        self.IR_AC_Signal_max = 0

        ## @brief Registro de media móvil exponencial para estimar la componente DC.
        self.ir_avg_reg = 0
        ## @brief Valor actual estimado del componente DC.
        self.IR_Average_Estimated = 0

        ## @brief Flag para indicar flanco ascendente.
        self.positiveEdge = False
        ## @brief Flag para indicar flanco descendente.
        self.negativeEdge = False

        ## @brief Buffer circular de muestras para el FIR.
        self.cbuf = [0] * self.BUF_SIZE
        ## @brief Índice actual del buffer circular.
        self.offset = 0

    ## @brief Evalúa si una nueva muestra IR contiene un latido.
    #  @param sample Valor de intensidad IR actual.
    #  @return True si se detecta un latido; False en caso contrario.
    def check_for_beat(self, sample):
        """
        Procesa un nuevo valor IR (`sample`) y devuelve True si detecta un latido.
        """
        beatDetected = False

        # Guarda el estado anterior
        self.IR_AC_Signal_Previous = self.IR_AC_Signal_Current

        # Estima el componente DC y calcula la señal AC
        self.IR_Average_Estimated = self._average_dc_estimator(sample)
        self.IR_AC_Signal_Current = self._lowpass_fir_filter(sample - self.IR_Average_Estimated)

        # Detecta cruce positivo por cero (flanco ascendente)
        if (self.IR_AC_Signal_Previous < 0) and (self.IR_AC_Signal_Current >= 0):
            # Ajusta máximos y mínimos
            self.IR_AC_Max = self.IR_AC_Signal_max
            self.IR_AC_Min = self.IR_AC_Signal_min

            self.positiveEdge = True
            self.negativeEdge = False
            self.IR_AC_Signal_max = 0

            delta = self.IR_AC_Max - self.IR_AC_Min
            if 20 < delta < 1000:
                beatDetected = True

        # Detecta cruce negativo por cero (flanco descendente)
        if (self.IR_AC_Signal_Previous > 0) and (self.IR_AC_Signal_Current <= 0):
            self.positiveEdge = False
            self.negativeEdge = True
            self.IR_AC_Signal_min = 0

        # Busca máximo en ciclo positivo
        if self.positiveEdge and (self.IR_AC_Signal_Current > self.IR_AC_Signal_Previous):
            self.IR_AC_Signal_max = self.IR_AC_Signal_Current

        # Busca mínimo en ciclo negativo
        if self.negativeEdge and (self.IR_AC_Signal_Current < self.IR_AC_Signal_Previous):
            self.IR_AC_Signal_min = self.IR_AC_Signal_Current

        return beatDetected

    ## @brief Estimador de componente DC utilizando media móvil exponencial.
    #  @param x Muestra IR actual.
    #  @return Valor estimado de la componente DC.
    def _average_dc_estimator(self, x):
        """
        Estimador DC por media móvil exponencial:
        p += ((x<<15) - p) >> 4
        devuelve p>>15
        """
        # Emula entero de 32 bits con desplazamientos
        self.ir_avg_reg += (((x << 15) - self.ir_avg_reg) >> 4)
        return self.ir_avg_reg >> 15

    ## @brief Filtro FIR pasa bajos simétrico con buffer circular.
    #  @param din Valor de entrada (señal AC sin DC).
    #  @return Valor filtrado.
    def _lowpass_fir_filter(self, din):
        """
        Filtro FIR pasa bajos simétrico de 12 coeficientes con buffer circular de 32.
        """
        # Almacena la muestra en buffer
        self.cbuf[self.offset] = din

        # Contribución central (coef[11])
        z = self._mul16(self.FIR_COEFFS[11],
                        self.cbuf[(self.offset - 11) & (self.BUF_SIZE-1)])

        # Suma simétrica de pares
        for i in range(11):
            a = self.cbuf[(self.offset - i) & (self.BUF_SIZE-1)]
            b = self.cbuf[(self.offset - 22 + i) & (self.BUF_SIZE-1)]
            z += self._mul16(self.FIR_COEFFS[i], a + b)

        # Avanza y envuelve el offset
        self.offset = (self.offset + 1) % self.BUF_SIZE

        # Escala de vuelta
        return z >> 15

    ## @brief Multiplicación de enteros de 16 bits.
    #  @param x Primer operando (int).
    #  @param y Segundo operando (int).
    #  @return Resultado de x * y como entero de 32 bits.
    @staticmethod
    def _mul16(x, y):
        """
        Multiplicación de enteros de 16 bits, resultado en 32 bits.
        """
        return x * y
