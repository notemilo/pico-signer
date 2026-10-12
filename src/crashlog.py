# crashlog.py — เขียน traceback ลงไฟล์โดย "ไม่เก็บข้อความ error"
#
# 🔴 13 ต.ค. 2026 (ผู้รีวิวภายนอก ข้อ 5): เดิม main.py เขียน traceback เต็มลง crash.txt บนแฟลช
#    ข้อความ error บางตัวมีข้อมูลผู้ใช้ เช่น bip39 เคยใส่ "คำที่พิมพ์ผิด" ไว้ในข้อความ
#    ไฟล์อยู่ถาวรและอ่านผ่าน USB ได้ภายหลัง = ขัดกับหลัก "ไม่มีอะไรของ seed ลงแฟลช"
#    ตอนนี้เก็บแค่ "ไฟล์ + เลขบรรทัด + ชนิด error" พอสำหรับดีบัก ไม่มีเนื้อข้อความ
#    (บนจอยังโชว์ข้อความได้ตามเดิม เพราะจอไม่ถาวร)
#
# ไฟล์นี้เป็น core (ไม่แตะฮาร์ดแวร์) เทสบนแมคได้

import sys


def safe_traceback(e):
    """traceback ที่ตัดข้อความของ error ทิ้ง เหลือแค่บรรทัด File/line และชื่อชนิด error"""
    try:
        import io
        buf = io.StringIO()
        sys.print_exception(e, buf)          # MicroPython
        text = buf.getvalue()
    except AttributeError:
        import traceback                     # CPython (เทสบนแมค)
        text = "".join(traceback.format_exception(type(e), e, e.__traceback__))
    keep = []
    for line in text.split("\n"):
        s = line.strip()
        if line.startswith("Traceback") or s.startswith("File "):
            keep.append(line)
    keep.append("%s (message not saved)" % type(e).__name__)
    return "\n".join(keep) + "\n"


def save(e, path="crash.txt"):
    """เขียนลงไฟล์ — ล้มก็ไม่เป็นไร (แฟลชเต็ม/ไม่มี filesystem)"""
    try:
        with open(path, "w") as f:
            f.write(safe_traceback(e))
    except Exception:
        pass
