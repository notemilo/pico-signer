# ups.py — อ่านสถานะแบตจาก Pico-UPS-B (ชิป INA219 บน I2C1)
#
# การต่อ: UPS เสียบซ้อนกับ Pico ตรง ๆ ไม่มีสายอะไรต้องเดิน
#   SDA = GP6 · SCL = GP7 (I2C1) · แอดเดรส 0x43
#   ⚠️ บนบอร์ดมีจัมเปอร์เลือกได้ระหว่าง I2C0 (GP20/21) กับ I2C1 (GP6/7)
#      โรงงานตั้งมาที่ GP6/7 แล้ว **ห้ามย้ายไป GP20/21** เพราะจอใช้ขาคู่นั้นอยู่
#      (GP20 = จอยขวา · GP21 = ปุ่ม Y)
#
# 🔑 ทำไมไม่ตั้งค่า calibration register:
#    เราอ่าน "แรงดันคร่อมตัวต้านทานวัดกระแส" ตรง ๆ แล้วคำนวณเอง
#    ตัวต้านทานบนบอร์ดคือ R010 = 0.01 โอห์ม (อ่านจากตัวเลขบนบอร์ดจริง)
#    ค่าที่อ่านได้ 1 หน่วย = 10 ไมโครโวลต์ -> 10uV / 0.01ohm = 1 mA พอดี
#    เลยแปลงเป็นมิลลิแอมป์ได้โดยไม่ต้องคูณอะไรเลย ลดโอกาสคำนวณพลาด

from machine import I2C, Pin

ADDR = 0x43
SDA_PIN = 6
SCL_PIN = 7

_REG_SHUNT = 0x01
_REG_BUS = 0x02

# ช่วงแรงดันของแบต Li-po 1 เซลล์ที่ใช้ประมาณเปอร์เซ็นต์
FULL_V = 4.2
EMPTY_V = 3.0


class UPS:
    def __init__(self, bus=1, sda=SDA_PIN, scl=SCL_PIN, addr=ADDR):
        self.addr = addr
        self.i2c = I2C(bus, sda=Pin(sda), scl=Pin(scl), freq=100000)

    def _read16(self, reg):
        d = self.i2c.readfrom_mem(self.addr, reg, 2)
        return (d[0] << 8) | d[1]

    def voltage(self):
        """แรงดันแบต (โวลต์) — ทะเบียนนี้เก็บค่าไว้ที่บิต 15-3 ทีละ 4 mV"""
        return (self._read16(_REG_BUS) >> 3) * 0.004

    def current_ma(self):
        """กระแส (mA) · บวก = กำลังชาร์จเข้า · ลบ = กำลังจ่ายออก"""
        raw = self._read16(_REG_SHUNT)
        if raw > 32767:          # ค่าติดลบเก็บแบบ two's complement
            raw -= 65536
        return raw               # 1 หน่วย = 1 mA พอดี (ดูหมายเหตุด้านบน)

    def percent(self):
        """เปอร์เซ็นต์โดยประมาณจากแรงดัน

        ⚠️ เป็นค่าประมาณเท่านั้น ตอนจ่ายไฟหนักแรงดันจะตกชั่วคราว
           ทำให้ตัวเลขดูน้อยกว่าความจริง — ห้ามเอาไปตัดสินใจอะไรสำคัญ
        """
        p = (self.voltage() - EMPTY_V) / (FULL_V - EMPTY_V) * 100
        if p < 0:
            p = 0
        elif p > 100:
            p = 100
        return int(p)

    def status(self):
        """คืน (เปอร์เซ็นต์, โวลต์, มิลลิแอมป์, ข้อความสั้น)"""
        v = self.voltage()
        ma = self.current_ma()
        p = self.percent()
        if ma > 20:
            note = "CHARGING"
        elif ma < -20:
            note = "ON BATTERY"
        else:
            note = "IDLE"
        return p, v, ma, note


def try_read():
    """อ่านแบบไม่โยน error — คืน None ถ้าไม่มี UPS ต่ออยู่

    เครื่องต้องใช้ได้ตามปกติแม้ถอด UPS ออก จึงห้ามให้ที่นี่ทำให้โปรแกรมตาย
    """
    try:
        return UPS().status()
    except Exception:
        return None
