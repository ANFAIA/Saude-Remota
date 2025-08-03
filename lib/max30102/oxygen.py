## @file oxygen.py
#  @brief Algoritmo en MicroPython para estimar la saturación de oxígeno (SpO2)
#         y la frecuencia cardiaca usando señales IR y RED provenientes del
#         sensor MAX30105 (u otros fotopletismógrafos similares).
#  
#  Implementa la clase :pyclass:`OxygenSaturation`, basada en el famoso
#  algoritmo de “Maxim Integrated AN-6595”, adaptado para su uso en
#  micro-controladores con recursos limitados.  Incluye detección de valles en
#  la señal IR, cálculo de pulsos por minuto (bpm) y estimación de SpO2 a partir
#  de la relación de amplitudes AC/DC de las señales RED e IR.
#  
#  @author Alejandro Fernández Rodríguez
#  @contact github.com/afernandezLuc
#  @version 1.0.0
#  @date 2025-08-02
#  @copyright Copyright (c) 2025 Alejandro Fernández Rodríguez
#  @license MIT — Consulte el archivo LICENSE para más información.
#  
#  ---- Ejemplo de uso --------------------------------------------------------
#  @code{.py}
#  from oxygen import OxygenSaturation
#  from max30105 import MAX30105
#  
#  # Suponiendo sensor es una instancia MAX30105 configurada previamente
#  oxi = OxygenSaturation()
#  ir_buf  = []  # rellenar con muestras IR
#  red_buf = []  # rellenar con muestras RED
#  spo2, spo2_ok, hr, hr_ok = oxi.calculate_spo2_and_heart_rate(ir_buf, red_buf)
#  if spo2_ok:
#      print("SpO2:", spo2, "%")
#  if hr_ok:
#      print("HR:", hr, "bpm")
#  @endcode
#  ---------------------------------------------------------------------------

## @class OxygenSaturation
#  @brief Clase para calcular la saturación de oxygeno en sangre a partir de los datos del sensor MAX30105.
#
#  Obrece una api pública para calcular SpO2 y ritmo cardiaco (bpm) a partir de
#  muestras de luz infrarroja (IR) y roja (RED). Utiliza un algoritmo
#  basado en el AN-6595 de Maxim Integrated, adaptado para micro-controladores.
#  Incluye detección de picos, filtrado y estimación de SpO2 mediante
#  la relación de amplitudes AC/DC de las señales IR y RED.
class OxygenSaturation:
    FreqS = 25
    BUFFER_SIZE = FreqS * 4
    MA4_SIZE = 4

    SPO2_TABLE = [
        95, 95, 95, 96, 96, 96, 97, 97, 97, 97, 97, 98, 98, 98, 98, 98, 99, 99, 99, 99,
        99, 99, 99, 99, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100,
        100, 100, 100, 100, 99, 99, 99, 99, 99, 99, 99, 99, 98, 98, 98, 98, 98, 98, 97, 97,
        97, 97, 96, 96, 96, 96, 95, 95, 95, 94, 94, 94, 93, 93, 93, 92, 92, 92, 91, 91,
        90, 90, 89, 89, 89, 88, 88, 87, 87, 86, 86, 85, 85, 84, 84, 83, 82, 82, 81, 81,
        80, 80, 79, 78, 78, 77, 76, 76, 75, 74, 74, 73, 72, 72, 71, 70, 69, 69, 68, 67,
        66, 66, 65, 64, 63, 62, 62, 61, 60, 59, 58, 57, 56, 56, 55, 54, 53, 52, 51, 50,
        49, 48, 47, 46, 45, 44, 43, 42, 41, 40, 39, 38, 37, 36, 35, 34, 33, 31, 30, 29,
        28, 27, 26, 25, 23, 22, 21, 20, 19, 17, 16, 15, 14, 12, 11, 10, 9, 7, 6, 5,
        3, 2, 1
    ]

    def __init__(self, sample_rate_hz=400):
        #self.FreqS = sample_rate_hz
        #self.BUFFER_SIZE = self.FreqS * 4        # 4 s de señal
        #self.MA4_SIZE = sample_rate_hz/10    # 100 ms de media móvil
        pass

    def _mean(self, arr):
        return sum(arr) / len(arr) if arr else 0

    def _max(self, arr):
        max_val = arr[0]
        max_idx = 0
        for i, v in enumerate(arr):
            if v > max_val:
                max_val = v
                max_idx = i
        return max_val, max_idx
    
    # ------------------------------------------------------------------
    # >> API pública
    # ------------------------------------------------------------------
    ## @brief Calcula SpO2 (%) y ritmo cardiaco (bpm).
    #  
    #  @param ir_buffer  Lista con muestras de infrarrojo (enteros sin signo).
    #  @param red_buffer Lista con muestras de rojo.
    #  @return Tupla ``(spo2, spo2_valid, heart_rate, hr_valid)`` donde:
    #          - *spo2*      Saturación estimada 0‑100 %.  ``-999`` si inválido.
    #          - *spo2_valid* ``1`` si la estimación es válida, ``0`` si no.
    #          - *heart_rate* Frecuencia cardiaca (bpm). ``-999`` si inválida.
    #          - *hr_valid*  ``1`` si *heart_rate* es válida.
    def calculate_spo2_and_heart_rate(self, ir_buffer, red_buffer):
        """Algoritmo completo descrito en AN‑6595; vermente implementa:
        1. Eliminación de componente DC e inversión de señal IR.
        2. Suavizado con media móvil de 4 puntos.
        3. Cálculo de umbral dinámico y detección de valles.
        4. Estimación de bpm mediante intervalos entre valles.
        5. Estimación de SpO2 usando relación AC/DC y la tabla ``SPO2_TABLE``.
        Consulte el código para detalle de cálculos intermedios."""
        # Verificar que los buffers tengan la misma longitud y sean válidos
        if len(ir_buffer) != len(red_buffer) or len(ir_buffer) < 4:
            return -999, 0, -999, 0

        # 1. Calcula la media DC y elimina DC de IR, invierte señal
        un_ir_mean = self._mean(ir_buffer)
        an_x = [-1 * (val - un_ir_mean) for val in ir_buffer]

        # 2. Media móvil de 4 puntos - CORRECCIÓN: usar longitud real del buffer
        an_x_ma4 = an_x.copy()
        buffer_length = len(an_x)
        for k in range(buffer_length - self.MA4_SIZE):
            an_x_ma4[k] = sum(an_x[k:k+self.MA4_SIZE]) // self.MA4_SIZE

        # 3. Calcula umbral
        n_th1 = int(self._mean(an_x_ma4[:buffer_length - self.MA4_SIZE]))
        n_th1 = max(30, min(n_th1, 60))

        # 4. Detección de valles (picos en señal invertida)
        # mínimo 160 ms entre valles  ⇒ muestras = FreqS * 0.16
        #min_gap = self.FreqS // 6          # ≈0.166 s
        #an_ir_valley_locs = self._find_peaks(an_x_ma4, n_th1, min_gap, 15)
        an_ir_valley_locs = self._find_peaks(an_x_ma4, n_th1, 4, 15)

        n_npks = len(an_ir_valley_locs)

        # 5. Heart rate
        if n_npks >= 2:
            n_peak_interval_sum = 0
            for k in range(1, n_npks):
                # Asegurar que los índices estén dentro del rango
                if (an_ir_valley_locs[k] < buffer_length and 
                    an_ir_valley_locs[k-1] < buffer_length):
                    n_peak_interval_sum += (an_ir_valley_locs[k] - an_ir_valley_locs[k-1])
            if n_peak_interval_sum > 0:
                n_peak_interval_sum //= (n_npks - 1)
                heart_rate = int((self.FreqS * 60) / n_peak_interval_sum)
                hr_valid = 1
            else:
                heart_rate = -999
                hr_valid = 0
        else:
            heart_rate = -999
            hr_valid = 0

        # 6. Carga valores originales para SpO2
        an_x = list(ir_buffer)
        an_y = list(red_buffer)

        # 7. Calcula SpO2 usando los valles detectados
        n_exact_ir_valley_locs_count = n_npks
        an_ratio = []
        for k in range(n_exact_ir_valley_locs_count - 1):
            loc_k = an_ir_valley_locs[k]
            loc_k1 = an_ir_valley_locs[k+1]
            
            # Verificar que los índices estén dentro del rango CORRECCIÓN PRINCIPAL
            if (loc_k < buffer_length and loc_k1 < buffer_length and 
                loc_k1 > loc_k and loc_k1 - loc_k > 3):
                
                # Busca máximos DC en el segmento
                segment_end = min(loc_k1 + 1, buffer_length)
                segment_x = an_x[loc_k:segment_end]
                segment_y = an_y[loc_k:segment_end]
                
                if segment_x and segment_y:
                    n_x_dc_max, n_x_dc_max_idx_rel = self._max(segment_x)
                    n_x_dc_max_idx = loc_k + n_x_dc_max_idx_rel
                    n_y_dc_max, n_y_dc_max_idx_rel = self._max(segment_y)
                    n_y_dc_max_idx = loc_k + n_y_dc_max_idx_rel

                    # AC componente IR y RED
                    # Cálculo seguro con verificación de índices
                    if loc_k1 < buffer_length:
                        n_y_ac = (an_y[loc_k1] - an_y[loc_k]) * (n_y_dc_max_idx - loc_k)
                        n_y_ac = an_y[loc_k] + n_y_ac // (loc_k1 - loc_k)
                        n_y_ac = an_y[n_y_dc_max_idx] - n_y_ac

                        n_x_ac = (an_x[loc_k1] - an_x[loc_k]) * (n_x_dc_max_idx - loc_k)
                        n_x_ac = an_x[loc_k] + n_x_ac // (loc_k1 - loc_k)
                        n_x_ac = an_x[n_x_dc_max_idx] - n_x_ac

                        n_nume = (n_y_ac * n_x_dc_max) >> 7
                        n_denom = (n_x_ac * n_y_dc_max) >> 7
                        
                        if n_denom > 0 and n_nume != 0:
                            ratio = (n_nume * 100) // n_denom
                            an_ratio.append(ratio)

        # 8. Mediana de ratios
        if len(an_ratio) > 0:
            an_ratio.sort()
            n_middle_idx = len(an_ratio) // 2
            if n_middle_idx > 0:
                n_ratio_average = (an_ratio[n_middle_idx-1] + an_ratio[n_middle_idx]) // 2
            else:
                n_ratio_average = an_ratio[n_middle_idx]
        else:
            n_ratio_average = -1

        # 9. Busca SpO2 en tabla
        if 2 < n_ratio_average < len(self.SPO2_TABLE):
            spo2 = self.SPO2_TABLE[int(n_ratio_average)]
            spo2_valid = 1
        else:
            spo2 = -999
            spo2_valid = 0

        return spo2, spo2_valid, heart_rate, hr_valid
    
    # ------------------------------------------------------------------
    # >> Detección de picos (funciones auxiliares)
    # ------------------------------------------------------------------
    ## @brief Encuentra hasta *max_num* picos en *x* mayores que *min_height* y separados al menos *min_distance*.
    #  @return Lista de índices de picos."""
    def _find_peaks(self, x, min_height, min_distance, max_num):
        """
        Encuentra hasta max_num picos en x mayores que min_height y separados al menos min_distance.
        Devuelve lista de índices.
        """
        peaks = []
        i = 1
        n_size = len(x)
        while i < n_size - 1:
            if x[i] > min_height and x[i] > x[i-1]:
                width = 1
                # Evitar desbordamiento en el bucle while
                while (i + width < n_size) and (x[i] == x[i+width]):
                    width += 1
                if (i + width < n_size) and (x[i] > x[i+width]):
                    peaks.append(i)
                    i += width + 1
                else:
                    i += width
            else:
                i += 1
        # Elimina picos demasiado cercanos
        peaks = self._remove_close_peaks(x, peaks, min_distance)
        # Limita a max_num
        peaks = peaks[:max_num]
        return peaks

    # ------------------------------------------------------------------
    # >> Detección de picos (funciones auxiliares)
    # ------------------------------------------------------------------
    ## @brief Encuentra hasta *max_num* picos en *x* mayores que *min_height* y separados al menos *min_distance*.
    #  @return Lista de índices de picos."""
    def _remove_close_peaks(self, x, peaks, min_distance):
        """
        Ordena los picos por altura descendente y elimina los que estén demasiado cerca.
        """
        if not peaks:
            return []
        # Ordena por valor descendente
        peaks_sorted = sorted(peaks, key=lambda idx: x[idx], reverse=True)
        filtered = []
        for idx in peaks_sorted:
            if all(abs(idx - fidx) > min_distance for fidx in filtered):
                filtered.append(idx)
        # Devuelve ordenados por posición ascendente
        return sorted(filtered)