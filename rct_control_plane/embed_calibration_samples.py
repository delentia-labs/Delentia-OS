"""
Round 69: a small neutral sample for `delentia memory calibrate` (memory_embeddings.calibrate). Question / answer-sentence pairs on everyday topics, in English and Thai, written for this purpose only
(none of it is in the benchmark sets of research/recall_dataset_r6*.py).

The pairs are PARAPHRASES on purpose: the question says the same thing in other words than the sentence that answers it, which is how people ask. The first version of this sample shared most of its words
between question and answer; it put the related cosines of bge-m3 at 0.76 instead of the 0.61-0.70 the benchmark sets show, so the floor and span it produced hid real matches from the agent (28 of 40 shown
against 39 in the top five). A cosine scale has to be measured on the kind of pair it will be asked about.
"""
from __future__ import annotations

from typing import List, Tuple

EN: List[Tuple[str, str]] = [
    ("When can I borrow books on the weekend?", "The public library lends out volumes from ten in the morning on Saturdays and Sundays."),
    ("Who fixes the lifts in our building?", "Elevator upkeep is handled by LiftCare once every quarter."),
    ("What does a monthly transit ticket cost?", "A 30-day bus pass is priced at 1,200 baht for grown-ups."),
    ("How many people can the assembly room hold?", "The meeting hall fits roughly eighty attendees."),
    ("Which carrier do staff usually fly?", "Business trips are booked on Thai Airways whenever possible."),
    ("What is the school's emblem animal called?", "The school mascot is a green dragon named Draco."),
    ("Where are the extra work clothes kept?", "Spare uniforms sit in locker twelve along the staff corridor."),
    ("How long is the trial period for new hires?", "Newly employed people serve ninety days on probation."),
    ("When does the evening bazaar shut?", "The night market closes at midnight, except on Mondays."),
    ("Who looks after the plants outside?", "The garden is tended by Mr. Prasit and two volunteers."),
    ("Which machine prints big banners?", "Large posters come off the wide-format press on the second floor."),
    ("In what language are lessons given?", "The course is delivered in English with Thai subtitles."),
    ("How frequently is the swimming facility sanitised?", "The pool is cleaned and tested each Wednesday morning."),
    ("What comes with a fitness club subscription?", "A membership covers the gym, the sauna and two classes weekly."),
    ("Where can guests stash their luggage?", "Visitors may leave bags at the cloakroom beside the main entrance."),
    ("How do I change a forgotten login secret?", "Passwords are reset from the profile page via the link emailed to you."),
    ("What is the largest allowed upload?", "Files may not exceed twenty megabytes each."),
    ("Which room is for silent studying?", "Room 4B is set aside for quiet study and bans phones."),
    ("When is the next planned downtime?", "The upcoming maintenance window falls on the first Sunday of next month."),
    ("Who signs off on time-off requests?", "Leave applications are approved by the line manager within two days."),
    ("What colour are the fire-escape signs?", "Emergency exit signs are green and lit all day and night."),
    ("How many passengers fit in the company van?", "The staff minibus has fourteen seats including the driver's."),
    ("What do I pay if I cancel a reservation late?", "Cancelling within two days of the date costs half the booking price."),
    ("Where is the backup beamer stored?", "The spare projector is in the cupboard behind the reception desk."),
]
TH: List[Tuple[str, str]] = [
    ("วันเสาร์ยืมหนังสือได้ตั้งแต่กี่โมง", "ห้องสมุดประชาชนเปิดให้บริการวันเสาร์ตั้งแต่เก้าโมงเช้าจนถึงห้าโมงเย็น"),
    ("ช่างคนไหนซ่อมท่อน้ำในหมู่บ้าน", "งานระบบน้ำประปาของหมู่บ้านอยู่ในความดูแลของช่างสมศักดิ์"),
    ("ค่าตั๋วโดยสารรถไฟฟ้ารายเดือนเท่าไร", "บัตรเดินทางรถไฟฟ้าแบบเหมาจ่ายต่อเดือนราคา 1,100 บาทสำหรับผู้ใหญ่"),
    ("ทำความสะอาดสระน้ำวันไหน", "ทีมงานล้างและตรวจคุณภาพน้ำในสระทุกเช้าวันพุธ"),
    ("จอดจักรยานได้ที่ไหน", "ลานสำหรับวางรถปั่นอยู่หลังตึกเรียนหลังที่สอง"),
    ("ใครสอนนักเรียนชั้นปีหนึ่ง", "อาจารย์ประจำห้องของปีหนึ่งคือครูวรรณา"),
    ("ต้องบอกล่วงหน้ากี่วันถ้าจะหยุดงาน", "การขอลาต้องยื่นก่อนอย่างน้อยสามวัน"),
    ("โรงอาหารชั้นล่างเลิกขายกี่โมง", "ร้านอาหารที่ชั้นหนึ่งหยุดรับลูกค้าตอนสองทุ่มครึ่ง"),
    ("เลขลับเปิดห้องประชุมคืออะไร", "ประตูห้องประชุมใหญ่ใช้รหัส 4821 และเปลี่ยนใหม่ทุกเดือน"),
    ("เครื่องปริ้นท์ตัวไหนพิมพ์ภาพสีได้", "เครื่องถ่ายเอกสารบนชั้นสามรองรับงานพิมพ์สี"),
    ("รถของบริษัทพาพนักงานกลับตอนไหน", "รถรับส่งออกจากหน้าอาคารเวลาหกโมงเย็น"),
    ("ใครบริหารสาขาทางภาคเหนือ", "ผู้จัดการประจำสาขาเชียงใหม่คือคุณชลธิชา"),
    ("ค่าเข้าฟิตเนสรายเดือนราคาเท่าไร", "สมาชิกฟิตเนสจ่ายเดือนละ 900 บาท และเรียนโยคะได้ฟรี"),
    ("ของใช้สำรองเก็บอยู่ตรงไหน", "พัสดุสำรองถูกเก็บในตู้เหล็กหน้าห้องพัสดุ"),
    ("เน็ตที่ออฟฟิศมาจากผู้ให้บริการรายใด", "สำนักงานใช้อินเทอร์เน็ตไฟเบอร์ความเร็วสูงของเอไอเอส"),
    ("กำหนดส่งรายงานรายเดือนคือเมื่อไร", "รายงานประจำเดือนต้องถึงมือภายในวันที่ห้าของเดือนถัดไป"),
]
