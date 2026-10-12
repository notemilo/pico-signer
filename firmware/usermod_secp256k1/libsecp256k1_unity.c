/* รวมซอร์ส libsecp256k1 เป็นไฟล์เดียว เพื่อปิดคำเตือนเฉพาะโค้ดของไลบรารี
 *
 * MicroPython คอมไพล์ด้วย -Wall -Werror · libsecp256k1 มีฟังก์ชัน static ที่ไม่ได้ใช้ในชุดที่เราเลือก
 * (เราไม่เปิด module เสริม) → คำเตือน unused-function กลายเป็น error
 * ใช้ pragma ตรงนี้แทนการแก้ flag ทั้งโปรเจค — โค้ดของเรา (secp256k1mod.c) ยังโดนตรวจเข้มเหมือนเดิม
 * ไม่ได้แก้โค้ดของไลบรารีแม้แต่บรรทัดเดียว แค่ #include ทั้งไฟล์
 */
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wunused-function"
#pragma GCC diagnostic ignored "-Wunused-parameter"
#include "secp256k1.c"
#include "precomputed_ecmult.c"
#include "precomputed_ecmult_gen.c"
#pragma GCC diagnostic pop
