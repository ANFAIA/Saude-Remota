## @package max30105
#  @brief Librería en MicroPython para el sensor MAX30105.
#
#  Proporciona funciones de configuración, lectura de datos de FIFO,
#  control de interrupciones, configuración de LED y lectura de temperatura interna.

import time
from machine import I2C, Pin

# MAX30105 I2C address
MAX30105_ADDRESS = 0x57

# Status Registers
MAX30105_INTSTAT1       = 0x00
MAX30105_INTSTAT2       = 0x01
MAX30105_INTENABLE1     = 0x02
MAX30105_INTENABLE2     = 0x03

# FIFO Registers
MAX30105_FIFOWRITEPTR   = 0x04
MAX30105_FIFOOVERFLOW   = 0x05
MAX30105_FIFOREADPTR    = 0x06
MAX30105_FIFODATA       = 0x07

# Configuration Registers
MAX30105_FIFOCONFIG     = 0x08
MAX30105_MODECONFIG     = 0x09
MAX30105_PARTICLECONFIG = 0x0A
MAX30105_LED1_PULSEAMP  = 0x0C
MAX30105_LED2_PULSEAMP  = 0x0D
MAX30105_LED3_PULSEAMP  = 0x0E
MAX30105_LED_PROX_AMP   = 0x10
MAX30105_MULTILEDCONFIG1= 0x11
MAX30105_MULTILEDCONFIG2= 0x12

# Die Temperature Registers
MAX30105_DIETEMPINT     = 0x1F
MAX30105_DIETEMPFRAC    = 0x20
MAX30105_DIETEMPCONFIG  = 0x21

# Proximity Function Registers
MAX30105_PROXINTTHRESH  = 0x30

# Part ID Registers
MAX30105_REVISIONID     = 0xFE
MAX30105_PARTID         = 0xFF

# EXPECTED PART ID
MAX_30105_EXPECTEDPARTID= 0x15

# Interrupt masks
MAX30105_INT_A_FULL_MASK      = ~0b10000000 & 0xFF
MAX30105_INT_A_FULL_ENABLE    = 0x80
MAX30105_INT_DATA_RDY_MASK    = ~0b01000000 & 0xFF
MAX30105_INT_DATA_RDY_ENABLE  = 0x40
MAX30105_INT_ALC_OVF_MASK     = ~0b00100000 & 0xFF
MAX30105_INT_ALC_OVF_ENABLE   = 0x20
MAX30105_INT_PROX_INT_MASK    = ~0b00010000 & 0xFF
MAX30105_INT_PROX_INT_ENABLE  = 0x10
MAX30105_INT_DIE_TEMP_RDY_MASK= ~0b00000010 & 0xFF
MAX30105_INT_DIE_TEMP_RDY_ENABLE=0x02

# FIFO config masks
MAX30105_SAMPLEAVG_MASK   = ~0b11100000 & 0xFF
MAX30105_SAMPLEAVG_1      = 0x00
MAX30105_SAMPLEAVG_2      = 0x20
MAX30105_SAMPLEAVG_4      = 0x40
MAX30105_SAMPLEAVG_8      = 0x60
MAX30105_SAMPLEAVG_16     = 0x80
MAX30105_SAMPLEAVG_32     = 0xA0
MAX30105_ROLLOVER_MASK    = ~0x10 & 0xFF
MAX30105_ROLLOVER_ENABLE  = 0x10
MAX30105_A_FULL_MASK      = 0xF0

# Mode config
MAX30105_SHUTDOWN_MASK    = 0x7F
MAX30105_SHUTDOWN         = 0x80
MAX30105_WAKEUP           = 0x00
MAX30105_RESET_MASK       = 0xBF
MAX30105_RESET            = 0x40
MAX30105_MODE_MASK        = 0xF8
MAX30105_MODE_REDONLY     = 0x02
MAX30105_MODE_REDIRONLY   = 0x03
MAX30105_MODE_MULTILED    = 0x07

# Particle sensing config
MAX30105_ADCRANGE_MASK    = 0x9F
MAX30105_ADCRANGE_2048    = 0x00
MAX30105_ADCRANGE_4096    = 0x20
MAX30105_ADCRANGE_8192    = 0x40
MAX30105_ADCRANGE_16384   = 0x60

MAX30105_SAMPLERATE_MASK  = 0xE3
MAX30105_SAMPLERATE_50    = 0x00
MAX30105_SAMPLERATE_100   = 0x04
MAX30105_SAMPLERATE_200   = 0x08
MAX30105_SAMPLERATE_400   = 0x0C
MAX30105_SAMPLERATE_800   = 0x10
MAX30105_SAMPLERATE_1000  = 0x14
MAX30105_SAMPLERATE_1600  = 0x18
MAX30105_SAMPLERATE_3200  = 0x1C

MAX30105_PULSEWIDTH_MASK  = 0xFC
MAX30105_PULSEWIDTH_69    = 0x00
MAX30105_PULSEWIDTH_118   = 0x01
MAX30105_PULSEWIDTH_215   = 0x02
MAX30105_PULSEWIDTH_411   = 0x03

# Slot config
MAX30105_SLOT1_MASK       = 0xF8
MAX30105_SLOT2_MASK       = 0x8F
MAX30105_SLOT3_MASK       = 0xF8
MAX30105_SLOT4_MASK       = 0x8F

SLOT_NONE      = 0x00
SLOT_RED_LED   = 0x01
SLOT_IR_LED    = 0x02
SLOT_GREEN_LED = 0x03
SLOT_NONE_PILOT  = 0x04
SLOT_RED_PILOT   = 0x05
SLOT_IR_PILOT    = 0x06
SLOT_GREEN_PILOT = 0x07

STORAGE_SIZE = 32        # FIFO size
## @class MAX30105
#  @brief Clase que permite el manejo del sensor óptico MAX30105.
#
#  Ofrece funcionalidades para configuración, lectura y procesamiento de datos de los LEDs rojo, IR y verde,
#  control de interrupciones, lectura de temperatura interna y control del FIFO.
class MAX30105:
    ## @brief Constructor de la clase MAX30105.
    #  @param i2c Objeto de interfaz I2C de la clase `machine.I2C`.
    #  @param addr Dirección del dispositivo I2C (por defecto 0x57).
    def __init__(self, i2c, addr=MAX30105_ADDRESS):
        self.i2c = i2c                      #: Interfaz I2C utilizada para la comunicación.
        self.addr = addr                    #: Dirección I2C del sensor.
        self.revisionID = 0                #: ID de revisión del chip.
        self.activeLEDs = 0                #: Número de LEDs activos configurados.

        # Buffers circulares para los datos de los LEDs
        self.head = 0                      #: Índice de escritura del buffer circular.
        self.tail = 0                      #: Índice de lectura del buffer circular.
        self.red   = [0]*STORAGE_SIZE              #: Almacena las muestras del LED rojo.
        self.IR    = [0]*STORAGE_SIZE              #: Almacena las muestras del LED infrarrojo.
        self.green = [0]*STORAGE_SIZE              #: Almacena las muestras del LED verde.

    ## @brief Inicializa el sensor MAX30105.
    #
    #  Verifica que el sensor responda correctamente leyendo su ID de parte,
    #  realiza un soft reset y limpia los buffers FIFO.
    #  @retval True si la inicialización fue exitosa.
    #  @retval False si el sensor no responde o el ID es incorrecto.
    def begin(self):
        if self.readPartID() != MAX_30105_EXPECTEDPARTID:
            print("MAX30105 no encontrado. Verifica conexión.")
            return False
        self.readRevisionID()

        self.softReset()
        time.sleep_ms(10)
        self.clearFIFO()

        return True

    ## @brief Lee un byte desde un registro del sensor.
    #  @param reg Dirección del registro a leer.
    #  @return Valor leído del registro (0-255). Si falla, devuelve 0.
    def readRegister(self, reg):
        try:
            data = self.i2c.readfrom_mem(self.addr, reg, 1)
            return data[0]
        except:
            return 0

    ## @brief Escribe un byte en un registro del sensor.
    #  @param reg Dirección del registro a escribir.
    #  @param val Valor de 8 bits que se desea escribir.
    #  @return True si la escritura fue exitosa; False si falló.
    def writeRegister(self, reg, val):
        try:
            self.i2c.writeto_mem(self.addr, reg, bytes([val]))
            return True
        except:
            return False

    ## @brief Modifica determinados bits de un registro usando una máscara.
    #
    #  Realiza una operación de máscara AND y OR sobre un registro para
    #  modificar solo los bits deseados sin afectar el resto.
    #  @param reg Dirección del registro a modificar.
    #  @param mask Máscara AND para limpiar los bits deseados.
    #  @param thing Valor OR para establecer los bits deseados.
    def bitMask(self, reg, mask, thing):
        orig = self.readRegister(reg)
        orig &= mask
        self.writeRegister(reg, orig | thing)

    ## @brief Lee el valor actual del registro de estado de interrupciones INT1.
    #  @return Valor del registro MAX30105_INTSTAT1.
    def getINT1(self): return self.readRegister(MAX30105_INTSTAT1)

    ## @brief Lee el valor actual del registro de estado de interrupciones INT2.
    #  @return Valor del registro MAX30105_INTSTAT2.
    def getINT2(self): return self.readRegister(MAX30105_INTSTAT2)

    ## @brief Habilita la interrupción cuando el FIFO está lleno (Almost Full).
    def enableAFULL(self):   self.bitMask(MAX30105_INTENABLE1, MAX30105_INT_A_FULL_MASK,   MAX30105_INT_A_FULL_ENABLE)

    ## @brief Deshabilita la interrupción por FIFO lleno.
    def disableAFULL(self):  self.bitMask(MAX30105_INTENABLE1, MAX30105_INT_A_FULL_MASK,   0)

    ## @brief Habilita la interrupción por disponibilidad de nuevos datos.
    def enableDATARDY(self): self.bitMask(MAX30105_INTENABLE1, MAX30105_INT_DATA_RDY_MASK, MAX30105_INT_DATA_RDY_ENABLE)

    ## @brief Deshabilita la interrupción por disponibilidad de nuevos datos.
    def disableDATARDY(self):self.bitMask(MAX30105_INTENABLE1, MAX30105_INT_DATA_RDY_MASK, 0)

    ## @brief Habilita la interrupción por desbordamiento de ALC (auto range).
    def enableALCOVF(self):  self.bitMask(MAX30105_INTENABLE1, MAX30105_INT_ALC_OVF_MASK,  MAX30105_INT_ALC_OVF_ENABLE)

    ## @brief Deshabilita la interrupción por desbordamiento de ALC.
    def disableALCOVF(self): self.bitMask(MAX30105_INTENABLE1, MAX30105_INT_ALC_OVF_MASK,  0)

    ## @brief Habilita la interrupción por proximidad.
    def enablePROXINT(self): self.bitMask(MAX30105_INTENABLE1, MAX30105_INT_PROX_INT_MASK, MAX30105_INT_PROX_INT_ENABLE)

    ## @brief Deshabilita la interrupción por proximidad.
    def disablePROXINT(self):self.bitMask(MAX30105_INTENABLE1, MAX30105_INT_PROX_INT_MASK, 0)

    ## @brief Habilita la interrupción cuando la temperatura interna está lista.
    def enableDIETEMPRDY(self): self.bitMask(MAX30105_INTENABLE2, MAX30105_INT_DIE_TEMP_RDY_MASK, MAX30105_INT_DIE_TEMP_RDY_ENABLE)

    ## @brief Deshabilita la interrupción por temperatura interna lista.
    def disableDIETEMPRDY(self):self.bitMask(MAX30105_INTENABLE2, MAX30105_INT_DIE_TEMP_RDY_MASK, 0)

    # Reset, shutdown, wakeup
    def softReset(self):
        self.bitMask(MAX30105_MODECONFIG, MAX30105_RESET_MASK, MAX30105_RESET)
        start = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), start) < 100:
            if (self.readRegister(MAX30105_MODECONFIG) & MAX30105_RESET)==0:
                break
            time.sleep_ms(1)

    def shutDown(self): self.bitMask(MAX30105_MODECONFIG, MAX30105_SHUTDOWN_MASK, MAX30105_SHUTDOWN)
    def wakeUp(self):   self.bitMask(MAX30105_MODECONFIG, MAX30105_SHUTDOWN_MASK, MAX30105_WAKEUP)

    # Configuration
    def setLEDMode(self, m):       self.bitMask(MAX30105_MODECONFIG, MAX30105_MODE_MASK, m)
    def setADCRange(self, r):      self.bitMask(MAX30105_PARTICLECONFIG, MAX30105_ADCRANGE_MASK, r)
    def setSampleRate(self, s):    self.bitMask(MAX30105_PARTICLECONFIG, MAX30105_SAMPLERATE_MASK, s)
    def setPulseWidth(self, pw):   self.bitMask(MAX30105_PARTICLECONFIG, MAX30105_PULSEWIDTH_MASK, pw)
    def setPulseAmplitudeRed(self, v):   self.writeRegister(MAX30105_LED1_PULSEAMP,  v)
    def setPulseAmplitudeIR(self, v):    self.writeRegister(MAX30105_LED2_PULSEAMP,  v)
    def setPulseAmplitudeGreen(self, v): self.writeRegister(MAX30105_LED3_PULSEAMP,  v)
    def setPulseAmplitudeProximity(self, v): self.writeRegister(MAX30105_LED_PROX_AMP, v)
    def setProximityThreshold(self, v):   self.writeRegister(MAX30105_PROXINTTHRESH, v)

    def enableSlot(self, num, device):
        if num==1: self.bitMask(MAX30105_MULTILEDCONFIG1, MAX30105_SLOT1_MASK, device)
        elif num==2: self.bitMask(MAX30105_MULTILEDCONFIG1, MAX30105_SLOT2_MASK, device<<4)
        elif num==3: self.bitMask(MAX30105_MULTILEDCONFIG2, MAX30105_SLOT3_MASK, device)
        elif num==4: self.bitMask(MAX30105_MULTILEDCONFIG2, MAX30105_SLOT4_MASK, device<<4)

    def disableSlots(self):
        self.writeRegister(MAX30105_MULTILEDCONFIG1, 0)
        self.writeRegister(MAX30105_MULTILEDCONFIG2, 0)

    # FIFO
    def setFIFOAverage(self, n):   self.bitMask(MAX30105_FIFOCONFIG, MAX30105_SAMPLEAVG_MASK, n)
    def clearFIFO(self):
        for r in (MAX30105_FIFOWRITEPTR, MAX30105_FIFOOVERFLOW, MAX30105_FIFOREADPTR):
            self.writeRegister(r, 0)
    def enableFIFORollover(self):  self.bitMask(MAX30105_FIFOCONFIG, MAX30105_ROLLOVER_MASK, MAX30105_ROLLOVER_ENABLE)
    def disableFIFORollover(self): self.bitMask(MAX30105_FIFOCONFIG, MAX30105_ROLLOVER_MASK, 0)
    def setFIFOAlmostFull(self, n):self.bitMask(MAX30105_FIFOCONFIG, MAX30105_A_FULL_MASK, n)
    def getWritePointer(self):     return self.readRegister(MAX30105_FIFOWRITEPTR)
    def getReadPointer(self):      return self.readRegister(MAX30105_FIFOREADPTR)

    # Temperature
    def readTemperature(self):
        self.writeRegister(MAX30105_DIETEMPCONFIG, 0x01)
        start = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), start)<100:
            if self.readRegister(MAX30105_INTSTAT2) & MAX30105_INT_DIE_TEMP_RDY_ENABLE:
                break
            time.sleep_ms(1)
        t_int  = self.readRegister(MAX30105_DIETEMPINT)
        t_frac = self.readRegister(MAX30105_DIETEMPFRAC)
        return t_int + (t_frac * 0.0625)

    def readTemperatureF(self):
        t = self.readTemperature()
        return t * 1.8 + 32 if t!=-999.0 else t

    # IDs
    def readPartID(self):   return self.readRegister(MAX30105_PARTID)
    def readRevisionID(self): self.revisionID = self.readRegister(MAX30105_REVISIONID)
    def getRevisionID(self): return self.revisionID

    # Setup convenience
    def setup(self, powerLevel, sampleAverage, ledMode, sampleRate, pulseWidth, adcRange):
        self.softReset()
        # FIFO Avg
        samp_map = {1:MAX30105_SAMPLEAVG_1,2:MAX30105_SAMPLEAVG_2,4:MAX30105_SAMPLEAVG_4,
                    8:MAX30105_SAMPLEAVG_8,16:MAX30105_SAMPLEAVG_16,32:MAX30105_SAMPLEAVG_32}
        self.setFIFOAverage(samp_map.get(sampleAverage, MAX30105_SAMPLEAVG_4))
        self.enableFIFORollover()
        # Mode
        modes = {1:MAX30105_MODE_REDONLY,2:MAX30105_MODE_REDIRONLY,3:MAX30105_MODE_MULTILED}
        self.setLEDMode(modes.get(ledMode, MAX30105_MODE_REDONLY))
        self.activeLEDs = ledMode
        # ADC range
        if   adcRange<4096:   self.setADCRange(MAX30105_ADCRANGE_2048)
        elif adcRange<8192:   self.setADCRange(MAX30105_ADCRANGE_4096)
        elif adcRange<16384:  self.setADCRange(MAX30105_ADCRANGE_8192)
        elif adcRange==16384: self.setADCRange(MAX30105_ADCRANGE_16384)
        else:                 self.setADCRange(MAX30105_ADCRANGE_2048)
        # Sample rate
        rate_map = [(100,MAX30105_SAMPLERATE_50),
                    (200,MAX30105_SAMPLERATE_100),
                    (400,MAX30105_SAMPLERATE_200),
                    (800,MAX30105_SAMPLERATE_400),
                    (1000,MAX30105_SAMPLERATE_800),
                    (1600,MAX30105_SAMPLERATE_1000),
                    (3200,MAX30105_SAMPLERATE_1600)]
        for thresh,code in rate_map:
            if sampleRate < thresh:
                self.setSampleRate(code)
                break
        else:
            self.setSampleRate(MAX30105_SAMPLERATE_3200 if sampleRate==3200 else MAX30105_SAMPLERATE_50)
        # Pulse width
        pw_map = [(118,MAX30105_PULSEWIDTH_69),
                  (215,MAX30105_PULSEWIDTH_118),
                  (411,MAX30105_PULSEWIDTH_215)]
        for thresh,code in pw_map:
            if pulseWidth < thresh:
                self.setPulseWidth(code)
                break
        else:
            self.setPulseWidth(MAX30105_PULSEWIDTH_411 if pulseWidth==411 else MAX30105_PULSEWIDTH_69)
        # LED amplitudes
        for fn in (self.setPulseAmplitudeRed,
                   self.setPulseAmplitudeIR,
                   self.setPulseAmplitudeGreen,
                   self.setPulseAmplitudeProximity):
            fn(powerLevel)
        # Multi-LED slots
        self.enableSlot(1, SLOT_RED_LED)
        if ledMode>1: self.enableSlot(2, SLOT_IR_LED)
        if ledMode>2: self.enableSlot(3, SLOT_GREEN_LED)
        self.clearFIFO()

    # Data collection
    def available(self):
        n = self.head - self.tail
        return n + STORAGE_SIZE if n<0 else n

    def getRed(self):
        return self.red[self.head] if self.safeCheck(250) else 0

    def getIR(self):
        return self.IR[self.head]  if self.safeCheck(250) else 0

    def getGreen(self):
        return self.green[self.head] if self.safeCheck(250) else 0

    def getFIFORed(self):   return self.red[self.tail]
    def getFIFOIR(self):    return self.IR[self.tail]
    def getFIFOGreen(self): return self.green[self.tail]

    def nextSample(self):
        if self.available():
            self.tail = (self.tail + 1) % STORAGE_SIZE

    def check(self):
        readPtr  = self.getReadPointer()
        writePtr = self.getWritePointer()
        if readPtr == writePtr:
            return 0
        num = writePtr - readPtr
        if num < 0: num += STORAGE_SIZE
        to_read = num * self.activeLEDs * 3

        # burst read
        while to_read > 0:
            chunk = min(to_read, 32)
            # align chunk to multiple of leds*3
            mod = chunk % (self.activeLEDs*3)
            if mod: 
                chunk -= mod
                if chunk == 0:  # no hay suficientes datos para leer
                    break
            try:
                buf = self.i2c.readfrom_mem(self.addr, MAX30105_FIFODATA, chunk)
            except OSError:
                return 0  # Error en I2C

            i = 0
            while i < len(buf):
                # Verificar que tenemos suficientes bytes para al menos una muestra
                if i + 3 > len(buf):
                    break
                    
                self.head = (self.head + 1) % STORAGE_SIZE
                
                # Leer valor RED (siempre presente)
                val = (buf[i] << 16) | (buf[i+1] << 8) | buf[i+2]
                val &= 0x3FFFF
                self.red[self.head] = val
                i += 3
                
                # Leer valor IR (si hay más de 1 LED activo)
                if self.activeLEDs > 1:
                    if i + 3 > len(buf):
                        break
                    val = (buf[i] << 16) | (buf[i+1] << 8) | buf[i+2]
                    val &= 0x3FFFF
                    self.IR[self.head] = val
                    i += 3
                
                # Leer valor GREEN (si hay más de 2 LEDs activos)
                if self.activeLEDs > 2:
                    if i + 3 > len(buf):
                        break
                    val = (buf[i] << 16) | (buf[i+1] << 8) | buf[i+2]
                    val &= 0x3FFFF
                    self.green[self.head] = val
                    i += 3
            
            to_read -= chunk
        return num

    def safeCheck(self, max_ms):
        start = time.ticks_ms()
        while True:
            if time.ticks_diff(time.ticks_ms(), start) > max_ms:
                return False
            if self.check():
                return True
            time.sleep_ms(1)