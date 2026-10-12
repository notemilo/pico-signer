"""base64 เล็ก ๆ — MicroPython มี ubinascii แต่ CPython ใช้ base64
ห่อไว้ให้เรียกชื่อเดียวกันทั้งสองฝั่ง"""

try:
    import ubinascii as _b

    def b64decode(s):
        if isinstance(s, str):
            s = s.encode()
        return _b.a2b_base64(s)

    def b64encode(b):
        return _b.b2a_base64(b).decode().strip()

except ImportError:
    import base64 as _b

    def b64decode(s):
        if isinstance(s, str):
            s = s.encode()
        return _b.b64decode(s)

    def b64encode(b):
        return _b.b64encode(b).decode()
