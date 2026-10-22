# บันทึกเดโมภาษาไทยโดยรักษาข้อความต้นทาง

วิดีโอชุดแรกของ Codex วันที่ 22 ตุลาคม 2026 มีข้อบกพร่องของตัวจับ/renderer ไม่ควรใช้โพสต์ต่อ. Transcript กับผลในไฟล์ต้องเป็นหลักฐานต้นทาง ไม่ใช้ภาพที่อักษรขาดตัดสินว่าราคา/ผลรันถูกต้อง.

## สาเหตุที่ทำซ้ำได้

1. การเรียก `bytes.decode('utf-8', 'replace')` แยกแต่ละก้อนจาก PTY: OS แบ่งกลางอักษรสามไบต์ได้ จึงเกิด `�`. ใช้ incremental strict decoder และ flush ที่ EOF; เก็บ rawbytes คู่ transcript เพื่อเทียบ.
2. `pyte.Screen.draw` รุ่นที่ติดตั้งหยุดข้อความทั้งก้อนเมื่อเจอ mark ความกว้างศูนย์ที่ `unicodedata.combining` เป็น 0 เช่นสระไทย U+0E31/U+0E35. การตรวจหมวด Unicode M และต่อ mark เข้าตัวก่อนหน้าแก้การหายของข้อความถัดมาโดยไม่เปลี่ยน output ของโปรแกรม.
3. วาดอักษรทีละ tile11×23 แล้ว crop: สระ/วรรณยุกต์ถูกตัดและไม่ shape ร่วมกัน. Renderer ใหม่ใช้ Noto Sans Thai+Pillow/libraqm วาด Thai run บน canvas เต็ม พร้อม lineheight เผื่อ mark. ไม่แก้ด้วย NFKC เพราะเปลี่ยนรูป SARA AM; exact-text criteria ใช้ NFC สำหรับ canonical equivalence.

`tests/test_demo_recording.py` ตรวจ UTF-8 ทุกตำแหน่งที่แบ่งไบต์, อักษรไทย/สระ/วรรณยุกต์และข้อความตัวเลขที่ตามมา. ต้องตรวจภาพที่มีไทยจริงด้วย ไม่ใช่ดูเฉพาะเฟรม JSON อังกฤษท้ายคลิป.

## คำสั่งทำซ้ำ

เครื่อง Linux ต้องมี Pillow ที่รองรับ libraqm, pyte, ffmpeg และ fontpaths ใน script (DejaVu Sans Mono/Noto Sans Thai). เป็น optional recording tools ไม่ใช่ dependency ของ runtime หลัก. บน cloud เครื่องรอบนี้มีครบแล้ว. ใช้ venv ที่ติดตั้งโครงการจาก source และ dependencies สำหรับ demo ไว้.

```bash
python scripts/demo_recording.py record --output /tmp/recording-new \
  -- python -u scripts/demo_intent_contract.py --dir /tmp/demo-new --pause 3
python scripts/demo_recording.py render /tmp/recording-new/session.cast /tmp/demo-thai.mp4
```

ทุก path ต้องใหม่เพื่อเก็บ attempt เดิม. ใช้ source checkout เพราะ scripted model helper อยู่ใน tests. ไม่เรียก paid API. `session.cast` เก็บ timestamps จริง; วิดีโอเป็น monochrome Unicode-shaped terminal replay ที่เวลาเดิม ไม่ใช่ desktop recording และไม่อ้าง pixel-perfect terminal emulation. Fontfallback/emoji/CJK นอก scope ต้องตรวจเพิ่มเติมก่อนใช้.

## แปลผลให้ถูก

- ใน contractdemo ภาษาอังกฤษครั้งแรกผิดเกณฑ์ไทยโดยตั้งใจ; `waiting_for_clarification`/exit1 คือ expected refusal. คำตอบว่างก็ต้องถูกปฏิเสธ. หลังคำยืนยันจริงจึงแสดงแผนและทำต่อ.
- `criteria_satisfied`แปลว่าผ่าน predicates ที่ประกาศ ไม่ใช่ความจริงทุกข้อ/ครบ RCT7. ดู`acceptance_verification`แยกจาก`intent_verification`.
- `similarity_score=0`กับ`aligned_with_intent=true`เกิดได้: matcher เทียบถ้อยคำ แต่ grounding อาจพบคำตอบสั้นที่มีหลักฐานรองรับ. `lexical_threshold_met`แสดงผล threshold แยก; `scope_note`บอกขอบเขต. ไม่เปลี่ยน 0 ให้เป็น 1 เพื่อให้ดูสวย.
- `null`/`None`คือไม่มีค่าที่วัดหรือไม่ใช้ path นั้น เช่นราคา USD ของ scriptedprovider, hallucination probability, belief confidence. ไม่ใช่ 0USD หรืออัตราภาพหลอน 0%. `algorithms_ok=0`เมื่อปิด optionalpipeline ไม่ใช่ 41 อัลกอริทึมรันล้มเหลว.
- Demo ใบเสนอราคาตั้งต้น: สยามแอร์ 12,500, ไทยคูลลิ่ง 16,800, บางกอกเทคนิค 9,900 บาท; งบ 15,000 ทำให้ A/C อยู่ในงบ. เคส edit เปลี่ยน A เป็น 14,000 หลังลายเซ็น จึงต้องแยกก่อน/หลังและไม่เทียบรูปคนละ episode เป็นราคาเดียวกัน.

ก่อนแชร์ต้องเทียบ UTF-8 transcript, oracle/resultJSON และ hash ก่อน/หลัง; ใส่ SCRIPTED label และ exactcommit. เก็บคลิปเดิมเพื่อ provenance แต่ระบุ superseded. ห้ามรวม keys, private runtime data, databases หรือ keys-included backup ใน publicbundle.
