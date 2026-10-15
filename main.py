# main.py — ไฟล์ที่ MicroPython รันเองตอนเปิดเครื่อง
#
# เสียบไฟที่ไหนก็ใช้ได้ ไม่ต้องมีคอมพิวเตอร์
#
# 🔑 ทางหนีสำหรับตอนพัฒนา: **กดปุ่ม B ค้างไว้ตอนเสียบไฟ** จะไม่เข้าเมนู
#    แต่ตกไปที่ REPL แทน เพื่อให้อัปโหลดไฟล์/แก้โค้ดได้
#    (ถ้าไม่มีทางนี้ เมนูจะยึดพอร์ตอนุกรมไว้ตลอด แก้โค้ดไม่ได้เลย)

import time


def _escape_to_repl():
    """กด B ค้างตอนบูต = ข้ามเมนู ไปที่ REPL"""
    try:
        from machine import Pin
        b = Pin(17, Pin.IN, Pin.PULL_UP)      # B = GP17
        for _ in range(20):                    # เช็ค 1 วินาที
            if b.value() == 0:
                return True
            time.sleep_ms(50)
    except Exception:
        pass
    return False


if _escape_to_repl():
    print("ข้ามเมนู — เข้า REPL (กด B ค้างตอนบูต)")
else:
    try:
        import ui
        ui.main()
    except KeyboardInterrupt:
        print("หยุดด้วย Ctrl-C — เข้า REPL")
    except Exception as e:
        # อย่าให้ตายเงียบ ๆ — โชว์บนจอด้วยถ้าจอยังใช้ได้
        import sys
        sys.print_exception(e)
        # เก็บ traceback ลงไฟล์ — จอกว้างแค่ 29 ตัว เลขบรรทัดที่ต้องใช้ดีบักมักโดนตัดหายไปพอดี
        # 🔴 13 ต.ค. 2026: เก็บแค่ไฟล์/บรรทัด/ชนิด error ไม่เก็บข้อความ (อาจมีคำ seed) — ดู crashlog.py
        try:
            import crashlog
            crashlog.save(e)
        except Exception:
            pass
        try:
            import gc
            import lcd
            # 🔴 15 ต.ค. 2026: MemoryError แล้วจอค้างภาพเดิม กดอะไรก็ไม่ได้ (เหมือนเครื่องแฮงก์)
            #    เพราะ lcd.LCD() ต้องจองแรมก้อน 115 KB ใหม่ ซึ่งตอนแรมหมดจองไม่ได้ → ข้ามการวาดเงียบ ๆ
            #    → ใช้จอของแอปที่จองไว้แล้ว (ui.APP.d) ก่อน · ไม่มีค่อยจองใหม่
            gc.collect()
            d = None
            try:
                d = ui.APP.d
            except Exception:
                pass
            if d is None:
                d = lcd.LCD()
            d.backlight(True)
            d.clear(lcd.BLACK)
            d.text_big("CRASH", 60, 30, lcd.RED, 3)
            msg = "%s: %s" % (type(e).__name__, e)
            y = 80
            for i in range(0, min(len(msg), 29 * 5), 29):
                d.text(msg[i:i + 29], 6, y, lcd.WHITE)
                y += 14
            d.text("saved to crash.txt", 6, 190, lcd.GREY)
            d.text("hold B at boot for REPL", 6, 208, lcd.GREY)
            d.show()
        except Exception:
            pass
