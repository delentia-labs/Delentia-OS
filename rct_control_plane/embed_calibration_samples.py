"""
Round 69: a small neutral sample for `delentia memory calibrate` (memory_embeddings.calibrate). Question/answer-sentence pairs on everyday topics, in English and Thai, written for this purpose only
(none of it is in the benchmark sets of research/recall_dataset_r6*.py). An embedding model's cosine scale differs from model to model; the sample measures where THIS model puts a question and the
sentence that answers it (related) and a question and an unrelated sentence (unrelated).
"""
from __future__ import annotations

from typing import List, Tuple

EN: List[Tuple[str, str]] = [
    ("When does the library open on weekends?", "The public library opens at ten o'clock on Saturdays and Sundays."),
    ("Who repairs our elevators?", "Elevator maintenance is handled by LiftCare every quarter."),
    ("How much is a monthly bus pass?", "A monthly bus pass costs 1,200 baht for adults."),
    ("What size is the meeting hall?", "The meeting hall holds around eighty people."),
    ("Which airline does the team usually fly with?", "Business travel is booked with Thai Airways whenever possible."),
    ("What is the name of the school mascot?", "The school mascot is a green dragon called Draco."),
    ("Where do we store the spare uniforms?", "Spare uniforms are kept in locker twelve in the staff corridor."),
    ("How long is the probation period?", "New employees serve a probation period of ninety days."),
    ("What time does the night market close?", "The night market closes at midnight, except on Mondays."),
    ("Who is in charge of the garden?", "The garden is looked after by Mr. Prasit and two volunteers."),
    ("Which printer handles large posters?", "Large posters are printed on the wide-format machine on the second floor."),
    ("What language is the course taught in?", "The course is taught in English with Thai subtitles."),
    ("How often is the pool cleaned?", "The swimming pool is cleaned and tested every Wednesday morning."),
    ("What does the gym membership include?", "Membership includes the gym, the sauna and two classes a week."),
    ("Where can visitors leave their bags?", "Visitors can leave bags at the cloakroom next to the main entrance."),
    ("How do I reset my account password?", "Passwords are reset from the profile page using the link sent by email."),
    ("What is the maximum file size for uploads?", "Uploads are limited to twenty megabytes per file."),
    ("Which room is used for quiet study?", "Room 4B is reserved for quiet study and has no phones allowed."),
    ("When is the next maintenance window?", "The next maintenance window is on the first Sunday of next month."),
    ("Who approves holiday requests?", "Holiday requests are approved by the line manager within two days."),
    ("What colour is the emergency exit sign?", "Emergency exit signs are green and lit around the clock."),
    ("How many seats does the minibus have?", "The company minibus has fourteen seats including the driver."),
    ("What is the cancellation fee for a booking?", "Cancelling within two days of the date costs half of the booking price."),
    ("Where is the spare projector kept?", "The spare projector is in the cupboard behind the reception desk."),
]
TH: List[Tuple[str, str]] = [
    ("ห้องสมุดเปิดวันเสาร์กี่โมง", "ห้องสมุดประชาชนเปิดวันเสาร์ตั้งแต่เก้าโมงเช้าจนถึงห้าโมงเย็น"),
    ("ใครดูแลระบบน้ำประปาของหมู่บ้าน", "ระบบน้ำประปาของหมู่บ้านดูแลโดยช่างสมศักดิ์"),
    ("ตั๋วรถไฟฟ้ารายเดือนราคาเท่าไร", "ตั๋วรถไฟฟ้ารายเดือนราคา 1,100 บาทสำหรับผู้ใหญ่"),
    ("สระว่ายน้ำทำความสะอาดเมื่อไร", "สระว่ายน้ำทำความสะอาดทุกวันพุธตอนเช้า"),
    ("ที่จอดจักรยานอยู่ตรงไหน", "ที่จอดจักรยานอยู่ด้านหลังอาคารเรียนหลังที่สอง"),
    ("ครูประจำชั้นปีหนึ่งคือใคร", "ครูประจำชั้นปีหนึ่งคือครูวรรณา"),
    ("ต้องแจ้งลาล่วงหน้ากี่วัน", "พนักงานต้องแจ้งลาล่วงหน้าอย่างน้อยสามวัน"),
    ("ร้านอาหารในตึกปิดกี่โมง", "ร้านอาหารชั้นล่างปิดเวลาสองทุ่มครึ่ง"),
    ("รหัสเข้าห้องประชุมคืออะไร", "รหัสเข้าห้องประชุมใหญ่คือ 4821 และเปลี่ยนทุกเดือน"),
    ("เครื่องถ่ายเอกสารตัวไหนพิมพ์สีได้", "เครื่องถ่ายเอกสารที่ชั้นสามพิมพ์สีได้"),
    ("รถรับส่งพนักงานออกกี่โมง", "รถรับส่งพนักงานออกจากหน้าตึกเวลาหกโมงเย็น"),
    ("ใครเป็นผู้จัดการสาขาเชียงใหม่", "ผู้จัดการสาขาเชียงใหม่คือคุณชลธิชา"),
    ("ค่าสมาชิกฟิตเนสเดือนละเท่าไร", "ค่าสมาชิกฟิตเนสเดือนละ 900 บาท รวมคลาสโยคะ"),
    ("ที่เก็บอุปกรณ์สำรองอยู่ที่ไหน", "อุปกรณ์สำรองเก็บไว้ในตู้เหล็กหน้าห้องพัสดุ"),
    ("อินเทอร์เน็ตของออฟฟิศใช้เจ้าไหน", "ออฟฟิศใช้บริการอินเทอร์เน็ตความเร็วสูงจากเอไอเอส"),
    ("ต้องส่งรายงานภายในวันไหน", "ต้องส่งรายงานประจำเดือนภายในวันที่ห้าของเดือนถัดไป"),
]
