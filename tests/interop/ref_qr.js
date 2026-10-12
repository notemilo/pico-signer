// ตัวแทน "ของจริง" ฝั่ง QR — ไลบรารี qrcode ตัวเดียวกับที่ wallet ใช้แสดง QR
//
// ⚠️ ค่าเริ่มต้นของไลบรารีนี้จะ "แบ่งข้อความเป็นหลายโหมด" ให้เล็กที่สุดเอง
//    (เช่น ABC123 -> [alphanumeric ABC][numeric 123]) ซึ่งเป็นคนละวิธีกับฝั่ง Pico
//    ที่ใช้โหมดเดียวทั้งก้อน · ถ้าส่ง mode มาด้วยจะบังคับให้ใช้ segment เดียว
//    เพื่อเทียบกันแบบตรงเงื่อนไข
const QR = require("qrcode");

const a = JSON.parse(process.argv[2]);
const input = a.mode ? [{ data: a.text, mode: a.mode }] : a.text;
const q = QR.create(input, { errorCorrectionLevel: a.ec || "M" });
const size = q.modules.size;
const d = q.modules.data;
const rows = [];
for (let r = 0; r < size; r++) {
  let s = "";
  for (let c = 0; c < size; c++) s += d[r * size + c] ? "1" : "0";
  rows.push(s);
}
process.stdout.write(JSON.stringify({
  version: q.version, mask: q.maskPattern, size: size, rows: rows,
}));
