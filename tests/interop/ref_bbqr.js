// ⚠️ คัดลอกมาจาก the watch-only wallet ตรง ๆ ห้ามแก้ — นี่คือ 'ของจริง' ที่เราต้องเข้ากันได้
function base32Encode(bytes) {
  const ALPHA = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = 0, value = 0, out = "";
  for (const b of bytes) {
    value = (value << 8) | b;
    bits += 8;
    while (bits >= 5) {
      bits -= 5;
      out += ALPHA[(value >> bits) & 31];
    }
  }
  if (bits > 0) out += ALPHA[(value << (5 - bits)) & 31];
  return out;
}

// chunk 600: QR ~version 14-16 (73-81 modules) — เบาบาง Q กล้องอ่านง่าย
// (เคยใช้ 1000 → Q scan ไม่ออก. ยอม parts เยอะขึ้นแต่ scan ได้ชัวร์)
function bbqrEncode(bytes, type = "P", maxChunk = 600) {
  // ใช้ Base32 encoding ('2') — ตรงกับที่ Coldcard ส่งออกมา + QR เล็กกว่า HEX ~37%
  const payload = base32Encode(bytes);
  const HEADER = 8;
  const chunkLen = maxChunk - HEADER;
  const total = Math.max(1, Math.ceil(payload.length / chunkLen));
  if (total > 1295) throw new Error("ข้อมูลใหญ่เกิน BBQr"); // 36^2 - 1
  const parts = [];
  for (let i = 0; i < total; i++) {
    const totStr = total.toString(36).padStart(2,"0").toUpperCase();
    const idxStr = i.toString(36).padStart(2,"0").toUpperCase();
    parts.push(`B$2${type}${totStr}${idxStr}${payload.slice(i*chunkLen, (i+1)*chunkLen)}`);
  }
  return parts;
}

// Base32 decode (RFC 4648, no padding) — Coldcard ใช้ '2' encoding
const _B32_ALPHA = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
function base32Decode(str) {
  str = str.toUpperCase().replace(/=+$/, "");
  if (!/^[A-Z2-7]*$/.test(str)) return null;
  const out = [];
  let bits = 0, value = 0;
  for (const ch of str) {
    const v = _B32_ALPHA.indexOf(ch);
    if (v < 0) return null;
    value = (value << 5) | v;
    bits += 5;
    if (bits >= 8) {
      bits -= 8;
      out.push((value >> bits) & 0xff);
    }
  }
  return new Uint8Array(out);
}

function bbqrDecode(parts) {
  if (parts.length === 0) return null;
  const buf = {};
  let total = null, type = null, encoding = null;
  const MAX_CHUNK_CHARS = 4000;
  const MAX_TOTAL_PARTS = 1295; // 36^2 - 1 per spec
  for (const p of parts) {
    if (typeof p !== "string" || !p.startsWith("B$")) return null;
    if (p.length < 9 || p.length > MAX_CHUNK_CHARS) return null;
    const enc = p[2], typ = p[3];
    // รองรับ H (hex), 2 (base32), Z (zlib+base32 — Coldcard ไม่ใช้)
    if (enc !== "H" && enc !== "2" && enc !== "Z") return null;
    const tot = parseInt(p.slice(4,6), 36);
    const idx = parseInt(p.slice(6,8), 36);
    if (!Number.isInteger(tot) || tot < 1 || tot > MAX_TOTAL_PARTS) return null;
    if (!Number.isInteger(idx) || idx < 0 || idx >= tot) return null;
    // ⚠️ Lock total/type/encoding ตอน part แรก — reject ถ้า part อื่นเปลี่ยน
    if (total === null) { total = tot; type = typ; encoding = enc; }
    else if (tot !== total || typ !== type || enc !== encoding) return null;
    buf[idx] = p.slice(8);
  }
  if (Object.keys(buf).length < total) return { partial: true, have: Object.keys(buf).length, total };
  let payload = "";
  for (let i = 0; i < total; i++) {
    if (!buf[i]) return null;
    payload += buf[i];
  }
  if (payload.length > 2_000_000) return null; // ~1MB cap
  let bytes;
  if (encoding === "2") {
    // Base32 decode
    const decoded = base32Decode(payload);
    if (!decoded) return null;
    bytes = decoded;
  } else if (encoding === "Z") {
    // zlib + base32 — ยังไม่ implement (Coldcard wallet export ไม่ใช้)
    return null;
  } else {
    // HEX encoding
    const hex = payload;
    if (hex.length === 0 || hex.length % 2 !== 0 || !/^[0-9A-Fa-f]+$/.test(hex)) return null;
    bytes = new Uint8Array(hex.length / 2);
    for (let i = 0; i < hex.length; i += 2) bytes[i/2] = parseInt(hex.slice(i, i+2), 16);
  }
  return { bytes, type, total };
}


module.exports = { bbqrEncode, bbqrDecode, base32Encode, base32Decode };
