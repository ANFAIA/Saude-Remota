from machine import I2C, Pin
import framebuf
import time

# ---------------------  Constantes SSD1306  ---------------------
SSD1306_I2C_ADDRESS      = 0x3C
SSD1306_SETCONTRAST      = 0x81
SSD1306_DISPLAYALLON_RESUME = 0xA4
SSD1306_DISPLAYALLON     = 0xA5
SSD1306_NORMALDISPLAY    = 0xA6
SSD1306_INVERTDISPLAY    = 0xA7
SSD1306_DISPLAYOFF       = 0xAE
SSD1306_DISPLAYON        = 0xAF
SSD1306_SETDISPLAYOFFSET = 0xD3
SSD1306_SETCOMPINS       = 0xDA
SSD1306_SETVCOMDETECT    = 0xDB
SSD1306_SETDISPLAYCLOCKDIV = 0xD5
SSD1306_SETPRECHARGE     = 0xD9
SSD1306_SETMULTIPLEX     = 0xA8
SSD1306_SETLOWCOLUMN     = 0x00
SSD1306_SETHIGHCOLUMN    = 0x10
SSD1306_SETSTARTLINE     = 0x40
SSD1306_MEMORYMODE       = 0x20
SSD1306_COLUMNADDR       = 0x21
SSD1306_PAGEADDR         = 0x22
SSD1306_COMSCANINC       = 0xC0
SSD1306_COMSCANDEC       = 0xC8
SSD1306_SEGREMAP         = 0xA0
SSD1306_CHARGEPUMP       = 0x8D
SSD1306_EXTERNALVCC      = 0x1
SSD1306_SWITCHCAPVCC     = 0x2

# ---------------------  Clase mejorada  ---------------------
class SSD1306:
    """Controlador SSD1306 con autochequeo de presencia.

    • self.connected  -> True si la pantalla respondió.
    • is_connected()  -> Método auxiliar.
    • Si no hay pantalla, las funciones de dibujo no hacen nada.
    """
    def __init__(self, width=128, height=64, i2c=None, addr=SSD1306_I2C_ADDRESS):
        self.width     = width
        self.height    = height
        self.pages     = height // 8
        self.addr      = addr

        # --- I²C ---
        if i2c is None:
            self.i2c = I2C(0, scl=Pin(22), sda=Pin(21), freq=400_000)
        else:
            self.i2c = i2c

        # --- ¿Pantalla presente? ---
        self.connected = self._detect_display()

        # Buffer y framebuf se crean siempre; así el código que escribe
        # texto/dibujos no revienta, aunque luego no se envíe a HW
        self.buffer   = bytearray(self.pages * self.width)
        self.framebuf = framebuf.FrameBuffer(self.buffer, self.width,
                                             self.height, framebuf.MONO_VLSB)

        if self.connected:
            self._init_display()
        else:
            # Convertir llamadas críticas en NOP
            self.write_cmd  = self._noop
            self.write_data = self._noop
            self.show       = self._noop
            # Opcional: avisar 1 sola vez
            print("[SSD1306] Pantalla no detectada; se omitirá salida gráfica.")

    # ---------- Utilidades internas ----------
    def _detect_display(self):
        """Escanea el bus para ver si la dirección existe."""
        try:
            return self.addr in self.i2c.scan()
        except OSError:
            # Por ejemplo, si el bus no existe todavía
            return False

    def _noop(self, *_, **__):
        """Función vacía para sustituir I/O cuando no hay pantalla."""
        pass

    def is_connected(self):
        """Devuelve True/False según la presencia del display."""
        return self.connected

    # ---------- Inicialización ----------
    def _init_display(self):
        cmds = [
            SSD1306_DISPLAYOFF,
            SSD1306_SETDISPLAYCLOCKDIV, 0x80,
            SSD1306_SETMULTIPLEX, self.height - 1,
            SSD1306_SETDISPLAYOFFSET, 0x00,
            SSD1306_SETSTARTLINE | 0x00,
            SSD1306_CHARGEPUMP, 0x14,
            SSD1306_MEMORYMODE, 0x00,
            SSD1306_SEGREMAP | 0x01,
            SSD1306_COMSCANDEC,
            SSD1306_SETCOMPINS, 0x12 if self.height == 64 else 0x02,
            SSD1306_SETCONTRAST, 0xCF,
            SSD1306_SETPRECHARGE, 0xF1,
            SSD1306_SETVCOMDETECT, 0x40,
            SSD1306_DISPLAYALLON_RESUME,
            SSD1306_NORMALDISPLAY,
            SSD1306_DISPLAYON
        ]
        for cmd in cmds:
            self.write_cmd(cmd)
        self.clear()
        self.show()

    # ---------- Bajo nivel ----------
    def write_cmd(self, cmd):
        try:
            self.i2c.writeto(self.addr, bytes([0x80, cmd]))
        except OSError:
            # Cable suelto durante la marcha → Marcar como desconectado
            self.connected = False
            self.write_cmd = self._noop
            self.write_data = self._noop
            self.show = self._noop

    def write_data(self, buf):
        try:
            self.i2c.writeto(self.addr, b'\x40' + buf)
        except OSError:
            self.connected = False
            self.write_cmd = self._noop
            self.write_data = self._noop
            self.show = self._noop

    # ---------- API de usuario ----------
    def clear(self):
        self.framebuf.fill(0)

    def show(self):
        self.write_cmd(SSD1306_COLUMNADDR)
        self.write_cmd(0)
        self.write_cmd(self.width - 1)
        self.write_cmd(SSD1306_PAGEADDR)
        self.write_cmd(0)
        self.write_cmd(self.pages - 1)
        self.write_data(self.buffer)

    def text(self, string, x, y, color=1):
        self.framebuf.text(string, x, y, color)

    
    def text_scaled(self, string, x, y, scale=1, color=1):
        """Renderiza texto escalado"""
        for char in string:
            # Buffer temporal para el caracter
            char_width = 8
            char_height = 8
            buf_temp = bytearray(char_width * char_height // 8)
            fb_temp = framebuf.FrameBuffer(buf_temp, char_width, char_height, framebuf.MONO_VLSB)
            
            # Renderizar caracter
            fb_temp.fill(0)
            fb_temp.text(char, 0, 0, color)
            
            # Transferir con escala
            for py in range(char_height):
                for px in range(char_width):
                    if fb_temp.pixel(px, py):
                        self.framebuf.fill_rect(
                            x + px * scale,
                            y + py * scale,
                            scale, scale, color)
            
            x += char_width * scale
    
    def draw_heart(self, x, y, size=1, color=1):
        """Corazón optimizado"""
        heart = [
            [0, 1, 1, 0, 1, 1, 0],
            [1, 1, 1, 1, 1, 1, 1],
            [1, 1, 1, 1, 1, 1, 1],
            [1, 1, 1, 1, 1, 1, 1],
            [0, 1, 1, 1, 1, 1, 0],
            [0, 0, 1, 1, 1, 0, 0],
        ]
        
        for dy, row in enumerate(heart):
            for dx, pixel in enumerate(row):
                if pixel:
                    self.framebuf.fill_rect(x + dx*size, y + dy*size, size, size, color)
    
    def display_parameter(self, param_name, value, unit, icon=None):
        """Muestra parámetro con diseño mejorado"""
        self.clear()
        
        # Título superior
        self.text("Monitor Salud", 35, 2)
        
        # Línea divisoria
        self.framebuf.hline(0, 12, self.width, 1)
        
        # Icono compacto
        if icon == "heart":
            self.draw_heart(100, 2)
        elif icon == "temp":
            self.draw_thermometer(100, 2)
        elif icon == "oxygen":
            self.draw_oxygen(100, 2)
        
        # Nombre del parámetro
        param_x = max(0, (self.width - len(param_name) * 8) // 2)
        self.text(param_name, param_x, 16)
        
        # Valor principal (doble tamaño)
        value_str = "{:.1f}".format(value) if isinstance(value, float) else str(value)
        value_x = max(0, (self.width - len(value_str) * 16) // 2)
        self.text_scaled(value_str, value_x, 28, scale=2, color=1)
        
        # Línea divisoria
        self.framebuf.hline(0, 45, self.width, 1)
        
        # Unidad
        unit_x = max(0, (self.width - len(unit) * 8) // 2)
        self.text(unit, unit_x, 50)
        
        self.show()
    
    def draw_thermometer(self, x, y):
        """Termómetro optimizado"""
        # Bulbo
        self.framebuf.fill_rect(x+2, y+10, 3, 3, 1)
        # Vara
        self.framebuf.vline(x+3, y+2, 8, 1)
        # Parte superior
        self.framebuf.fill_rect(x+2, y, 3, 2, 1)
    
    def draw_oxygen(self, x, y):
        """Icono de oxígeno optimizado"""
        # Letra O
        self.framebuf.ellipse(x+4, y+6, 3, 3, 1)
        # Número 2
        self.framebuf.text("2", x+8, y+2, 1)
    
    def display_finger_message(self):
        """Mensaje para colocar dedo"""
        self.clear()
        self.text_scaled("Coloque su", 10, 0, scale=2)
        self.text_scaled("DEDO", 40, 20, scale=2)
        self.text_scaled("en el sensor", 10, 50, scale=2)
        self.show()
    
    def display_weak_signal(self):
        """Mensaje de señal débil"""
        self.clear()
        self.text("Señal debil", 25, 10)
        self.text_scaled("AJUSTE", 35, 20, scale=2)
        self.text("la posicion", 25, 45)
        self.show()