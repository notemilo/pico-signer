#!/bin/sh
# รันเทสทั้งหมด
#   tests/test_*.py          = เทสตัวเอง (รันได้เสมอ ไม่ต้องพึ่งอะไรข้างนอก)
#   tests/interop/test_*.py  = เทสไขว้กับ implementation จริงของคนอื่น (ต้องมี node)
#                              ข้ามให้อัตโนมัติถ้าไม่มี node — จะได้ไม่พังตอนรันบนเครื่องเปล่า
set -e
for t in tests/test_*.py; do
    echo "── $t"
    python3 "$t"
    echo
done

if command -v node >/dev/null 2>&1; then
    for t in tests/interop/test_*.py; do
        [ -e "$t" ] || continue
        echo "── $t  (เทียบกับของจริงคนละภาษา)"
        python3 "$t"
        echo
    done
else
    echo "⚠️  ข้ามเทสไขว้: ไม่มี node ในเครื่องนี้"
    echo
fi

# libsecp256k1 (โมดูล C ในเฟิร์มแวร์ Pico) เทียบกับโค้ด Python เดิม — ต้องใช้ MicroPython unix ที่ build พร้อมโมดูล
#   build: make -C ports/unix MICROPY_PY_FFI=0 USER_C_MODULES=<repo>/firmware  (ดู firmware/pico/README.md)
MP_UNIX="${MP_UNIX:-$HOME/picobuild/micropython/ports/unix/build-standard/micropython}"
if [ -x "$MP_UNIX" ] && "$MP_UNIX" -c "import secp256k1c" >/dev/null 2>&1; then
    echo "── tests/mp_secp256k1c_crosscheck.py  (MicroPython + libsecp256k1)"
    "$MP_UNIX" tests/mp_secp256k1c_crosscheck.py
    echo
else
    echo "⚠️  ข้ามเทส libsecp256k1: ไม่มี MicroPython unix ที่มีโมดูล secp256k1c ($MP_UNIX)"
    echo
fi

echo "✅ ผ่านครบทุกชุด"
