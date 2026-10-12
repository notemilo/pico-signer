# boot.py — MicroPython รันไฟล์นี้ตอนเปิดเครื่อง "ก่อนเริ่ม USB" แล้วค่อยรัน main.py
#
# 🔴 13 ต.ค. 2026 (ผู้รีวิวภายนอก ข้อ 2): เดิม USB data + REPL เปิดตั้งแต่บูตจนกว่าจะเริ่มใส่ seed
#    เสียบชาร์จกับคอมที่มีมัลแวร์ตอนยังไม่มี seed → มัลแวร์กด Ctrl-C เข้า REPL แล้วแก้ไฟล์ .py ได้
#    (เช่นทำให้ seed จากเต๋าเดาได้ หรือแอบส่ง seed ทาง nonce) → รอบหน้าที่ใส่ seed ก็โดน
# วิธี: ตั้ง "USB แบบกำหนดเองที่ไม่มี interface" ตรงนี้ ซึ่งรันก่อน USB เริ่มทำงาน
#    → คอมไม่เคยเห็นพอร์ตเลยตั้งแต่เสียบ · ไฟยังเข้าชาร์จได้ · ไม่มีช่วงเวลาให้แทรก Ctrl-C
#    (เอกสาร machine.USBDevice หัวข้อ Lifecycle: boot.py รันก่อน USB subsystem เริ่ม)
#
# 🔑 ทางเข้าสำหรับพัฒนา/อัปเดต: **กดปุ่ม B ค้างตอนเปิดเครื่อง** → USB เปิดตามปกติ (+ main.py เข้า REPL)
#    คนที่จะใช้ทางนี้ต้องมีเครื่องอยู่ในมือและกดปุ่มเอง — คอมทำเองไม่ได้
#
# ⚠️ ถ้าไฟล์นี้พังจน B ใช้ไม่ได้: กดปุ่ม BOOTSEL บน Pico ค้างตอนเสียบ (อยู่ใน ROM ของชิป แก้ไม่ได้)
#    แล้วแฟลชเฟิร์มแวร์ใหม่ — ไฟล์บนเครื่องยังอยู่ ต้องลบ boot.py ทีหลังผ่าน REPL

import time

_USB_DEV = bytes([18, 1, 0x00, 0x02, 0, 0, 0, 64, 0x8A, 0x2E, 0x0F, 0x00, 0x00, 0x01, 0, 0, 0, 1])
_USB_CFG = bytes([9, 2, 9, 0, 0, 1, 0, 0x80, 50])      # configuration ที่ไม่มี interface


def _b_held():
    """ปุ่ม B (GP17) ถูกกดค้างไหม — เช็คราว 0.3 วิ"""
    try:
        from machine import Pin
        b = Pin(17, Pin.IN, Pin.PULL_UP)
        for _ in range(10):
            if b.value() == 0:
                return True
            time.sleep_ms(30)
    except Exception:
        pass
    return False


def _usb_data_off():
    try:
        import machine
        u = machine.USBDevice()
        u.active(False)
        u.builtin_driver = u.BUILTIN_NONE
        u.config(_USB_DEV, _USB_CFG, [None])
        u.active(True)
    except Exception:
        pass


if not _b_held():
    try:
        import micropython
        micropython.kbd_intr(-1)       # กันซ้ำอีกชั้น: Ctrl-C ไม่ขัดจังหวะโปรแกรม
    except Exception:
        pass
    _usb_data_off()

del _b_held, _usb_data_off
