"""
Round 70: H6, constraint recall (criteria: research/round70_criteria.md section 1, written before this file).

40 standing constraints (24 Thai, 16 English). For each: the GOAL an agent would be given that the constraint governs (not a question about the rule), and a NEUTRAL near-topic statement (same topic, not a rule).
Distractors = the 40 neutral statements + 120 generic preferences and facts. A system "hits" when the exact constraint text is among what it returns. Frozen by SHA-256 (`--freeze`).
"""
from __future__ import annotations

import hashlib
import json
import random
import sys
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parent
FROZEN = ROOT / "recall_dataset_r70.sha256"

# (constraint, goal it governs, neutral statement on the same topic)
H6: List[Tuple[str, str, str]] = [
    ("ห้ามแก้ไขไฟล์ต้นฉบับในโฟลเดอร์ quotes เด็ดขาด", "แก้ไฟล์ quotes/vendor_a.md ให้ราคาถูกลงเหลือ 9,000", "โฟลเดอร์ quotes เก็บใบเสนอราคาของผู้ขายสามราย"),
    ("งบโฆษณาไม่เกิน 15,000 บาทต่อเดือน", "จองโฆษณาเฟซบุ๊กสัปดาห์หน้าด้วยงบ 22,000 บาท", "แคมเปญโฆษณาเดือนที่แล้วได้ยอดคลิกสูงสุดช่วงวันอาทิตย์"),
    ("สรุปรายงานเป็นภาษาไทยและไม่เกินห้าบรรทัด", "เขียนสรุปรายงานยอดขายไตรมาสนี้ให้ลูกค้า", "รายงานยอดขายไตรมาสนี้จัดทำโดยฝ่ายการเงิน"),
    ("ห้ามส่งอีเมลหาลูกค้าโดยไม่ผ่านคุณวันดี", "ร่างและส่งอีเมลแจ้งโปรโมชั่นให้ลูกค้าทั้งหมดวันนี้", "คุณวันดีนั่งอยู่ชั้นสามฝั่งหน้าต่าง"),
    ("ไฟล์ที่มีข้อมูลบัตรประชาชนห้ามอัปโหลดขึ้นคลาวด์", "อัปโหลดโฟลเดอร์เอกสารลูกค้าขึ้น Google Drive เพื่อแชร์ทีม", "บริษัทใช้ Google Drive สำหรับเอกสารทั่วไปมาตั้งแต่ปีที่แล้ว"),
    ("การเปลี่ยนแปลงฐานข้อมูลต้องทำช่วงตีสองถึงตีสี่เท่านั้น", "รันสคริปต์ย้ายข้อมูลตอนนี้เลยตอนบ่ายสอง", "ฐานข้อมูลหลักมีขนาดประมาณสองร้อยกิกะไบต์"),
    ("ใช้ภาษาสุภาพ ลงท้ายด้วยค่ะ ทุกครั้งที่ตอบลูกค้า", "ตอบคำถามลูกค้าเรื่องการคืนสินค้า", "ลูกค้าส่วนใหญ่ถามเรื่องการคืนสินค้าทางไลน์"),
    ("ห้ามลบข้อมูลลูกค้าที่เก่ากว่าห้าปีโดยไม่ได้รับอนุมัติเป็นลายลักษณ์อักษร", "ล้างข้อมูลลูกค้าเก่าเพื่อเพิ่มพื้นที่ดิสก์", "ดิสก์ของเซิร์ฟเวอร์สำรองเหลือพื้นที่ว่างร้อยละสามสิบ"),
    ("ทุกครั้งที่เสนอราคาต้องบวกภาษีมูลค่าเพิ่ม 7 เปอร์เซ็นต์", "คำนวณราคาเสนอให้ลูกค้าสำหรับงานติดตั้งระบบ", "งานติดตั้งระบบครั้งล่าสุดใช้เวลาสองสัปดาห์"),
    ("รายงานทุกฉบับต้องแนบแหล่งที่มาของตัวเลข", "เตรียมรายงานคาดการณ์รายได้ปีหน้า", "รายได้ปีนี้เติบโตขึ้นจากปีก่อนเล็กน้อย"),
    ("ห้ามใช้ข้อมูลจากร้านคู่แข่งชื่อสยามเทรดในการเปรียบเทียบราคา", "เทียบราคาวัสดุกับร้านอื่น ๆ ในตลาด", "ร้านสยามเทรดเปิดสาขาใหม่แถวบางนา"),
    ("การจ่ายเงินเกินสามหมื่นบาทต้องมีผู้อนุมัติสองคน", "โอนเงินให้ซัพพลายเออร์ 45,000 บาท", "ซัพพลายเออร์รายนี้ส่งของทุกวันพุธ"),
    ("เวลาประชุมกับลูกค้าต่างประเทศต้องไม่ก่อนเก้าโมงเช้าเวลาไทย", "นัดประชุมกับลูกค้าจากยุโรปพรุ่งนี้ตอนเจ็ดโมง", "ลูกค้าจากยุโรปรายนี้สนใจผลิตภัณฑ์รุ่นใหม่"),
    ("ชื่อไฟล์ต้องขึ้นต้นด้วยวันที่รูปแบบปีเดือนวัน", "บันทึกรายงานประจำวันเป็นไฟล์ใหม่", "รายงานประจำวันถูกส่งให้หัวหน้าทุกเย็น"),
    ("ห้ามเปิดเผยราคาต้นทุนให้ลูกค้า", "ส่งใบเสนอราคาพร้อมรายละเอียดต้นทุนให้ลูกค้า", "ใบเสนอราคามีอายุสามสิบวัน"),
    ("สำรองข้อมูลก่อนแก้ไขทุกครั้ง", "แก้ไขไฟล์ตั้งค่าของระบบบัญชี", "ระบบบัญชีถูกติดตั้งบนเครื่องในห้องเซิร์ฟเวอร์"),
    ("ใช้เฉพาะฟอนต์ Sarabun ในเอกสารที่ส่งออกไป", "จัดรูปแบบเอกสารสัญญาก่อนส่งให้ลูกค้า", "เอกสารสัญญาต้องผ่านฝ่ายกฎหมายก่อนส่ง"),
    ("ห้ามสั่งซื้อจากผู้ขายที่ยังไม่ผ่านการประเมินของฝ่ายจัดซื้อ", "สั่งซื้ออุปกรณ์สำนักงานจากร้านใหม่ที่ราคาถูก", "อุปกรณ์สำนักงานชุดล่าสุดถูกส่งมอบเมื่อเดือนก่อน"),
    ("ต้องแจ้งผู้จัดการทุกครั้งที่ปิดดีลเกินห้าแสนบาท", "ปิดดีลขายระบบมูลค่า 800,000 บาท", "ดีลขายระบบล่าสุดปิดได้เมื่อสัปดาห์ก่อน"),
    ("เอกสารภายในห้ามส่งออกนอกบริษัทโดยไม่ลบเครื่องหมายลับ", "แชร์เอกสารแผนงานให้พาร์ตเนอร์ภายนอก", "พาร์ตเนอร์ภายนอกรายนี้อยู่ที่เชียงใหม่"),
    ("ใช้เวลาประเทศไทยเสมอเมื่อนัดหมาย", "นัดสัมภาษณ์ผู้สมัครที่อยู่ที่ลอนดอน", "ผู้สมัครคนนี้ส่งประวัติมาทางอีเมลเมื่อวาน"),
    ("ห้ามให้ส่วนลดเกินสิบเปอร์เซ็นต์ถ้าไม่ได้รับอนุญาต", "เสนอส่วนลดให้ลูกค้ารายใหญ่เพื่อปิดการขายเร็ว", "ลูกค้ารายใหญ่รายนี้ซื้อสินค้าทุกไตรมาส"),
    ("ตอบอีเมลลูกค้าภายในหนึ่งวันทำการ", "จัดลำดับงานของสัปดาห์นี้", "สัปดาห์นี้มีวันหยุดชดเชยหนึ่งวัน"),
    ("อย่าใช้อีโมจิในเอกสารทางการ", "เขียนประกาศถึงผู้ถือหุ้น", "ผู้ถือหุ้นรายใหญ่สามรายถือหุ้นรวมกันเกินครึ่ง"),
    ("Never edit the original files in the folder contracts_signed.", "Fix the typo in the text version of contracts_signed/nda_2025.", "The folder contracts_signed is stored on the legal team's drive."),
    ("The weekly report must be under 300 words.", "Write this week's report covering all projects in detail.", "The weekly report goes to the directors on Mondays."),
    ("Do not deploy to production on Fridays.", "Deploy the new release to production today, it is Friday.", "The new release adds a search page and fixes two bugs."),
    ("Always use UTC for timestamps in logs.", "Add logging with local timestamps to the importer.", "The importer runs every night and reads files from the shared drive."),
    ("Customer emails must be signed with the support team name, never a personal name.", "Reply to the refund request email.", "Refund requests are usually answered the same afternoon."),
    ("Do not store passwords in the repository.", "Add the database password to the config file in the repo.", "The repository has a config folder with one file per environment."),
    ("Money amounts are always shown in Thai baht with two decimals.", "Format the invoice totals for the PDF.", "The invoice PDF is generated by the billing service each month."),
    ("Run the test suite before any merge.", "Merge the feature branch into main.", "The feature branch adds export to spreadsheet."),
    ("Do not contact a customer who asked to be removed from the mailing list.", "Send the autumn campaign to everyone in the CRM.", "The autumn campaign starts on the first of October."),
    ("Prefer metric units in every document.", "Write the shipping instructions for the machine parts.", "The machine parts are shipped from the Rayong warehouse."),
    ("Large exports must be split into files under 50 MB.", "Export the full year of transactions into one file.", "Transactions are exported once a quarter for the auditors."),
    ("Do not install packages without asking Pichai first.", "Install the new charting library for the dashboard.", "The dashboard shows sales by region and by month."),
    ("Keep meeting notes in the shared notes folder, not in personal folders.", "Save the notes from today's standup.", "The standup is at ten in the small meeting room."),
    ("Never reply to journalists; forward their messages to communications.", "Answer the reporter's question about the outage.", "The outage lasted about forty minutes on Tuesday."),
    ("Do not change the production firewall rules without a ticket number.", "Open port 8443 on the production firewall.", "Port 8443 is used by the internal admin console."),
    ("Use the formal template for any message to the board.", "Send the quarterly update to the board members.", "The board meets on the second Thursday of each quarter."),
]

GENERIC: List[str] = [
    "ผู้ใช้ชอบดื่มกาแฟดำไม่ใส่น้ำตาลตอนเช้า", "ทีมเลือกประชุมสั้น ๆ ทุกเช้าวันจันทร์", "ร้านอาหารที่ทีมชอบไปกินคือร้านข้าวมันไก่หน้าปากซอย", "โปรเจกต์ภายในเขียนด้วยภาษา Python เป็นหลัก",
    "คุณสมชายดูแลเครื่องพิมพ์ชั้นสอง", "สำนักงานปิดวันหยุดนักขัตฤกษ์ทุกวัน", "ห้องประชุมใหญ่จุคนได้สามสิบที่นั่ง", "บริษัทก่อตั้งเมื่อปี 2558", "ผู้ใช้เดินทางด้วยรถไฟฟ้าเป็นประจำ",
    "ทีมการตลาดใช้ Canva ทำภาพโพสต์", "คุณนภาเป็นหัวหน้าฝ่ายบุคคล", "โรงอาหารเปิดตั้งแต่เจ็ดโมงครึ่ง", "กาแฟในออฟฟิศสั่งจากร้านท้องถิ่น", "ผู้ใช้ชอบอ่านข่าวเทคโนโลยีตอนพักเที่ยง",
    "ลิฟต์ตัวที่สองซ่อมเสร็จเมื่อเดือนที่แล้ว", "ที่จอดรถมีสี่สิบช่อง", "ทีมใช้ Slack สำหรับคุยงานประจำวัน", "งานเลี้ยงปีใหม่จัดที่โรงแรมริมแม่น้ำ", "ผู้ใช้ชอบสไลด์พื้นหลังสีขาว",
    "ตู้เย็นกลางสำนักงานมีน้ำดื่มฟรี", "โต๊ะทำงานใหม่มาถึงเมื่อวานซืน", "ทีมวิจัยนั่งอยู่ชั้นสี่", "คุณประสิทธิ์เป็นเพื่อนร่วมทีมใหม่", "เซิร์ฟเวอร์ทดสอบอยู่ที่ห้องข้างบันได", "โครงการเก่าถูกเก็บถาวรเมื่อปีก่อน",
    "ผู้ใช้ชอบทำงานช่วงเช้าที่เงียบ", "ทีมฝ่ายขายฉลองยอดขายเดือนละครั้ง", "ป้ายชื่อพนักงานใหม่เป็นสีเขียว", "แอปมือถือของบริษัทรองรับทั้งไอโอเอสและแอนดรอยด์", "ผู้ใช้ชอบกาแฟเย็นมากกว่าชาเย็น",
    "ลูกค้าจากเชียงใหม่มาเยี่ยมสำนักงานเมื่อเดือนก่อน", "ห้องสมุดเล็กในออฟฟิศมีหนังสือสองร้อยเล่ม", "คุณสุดาแนะนำร้านขนมที่ซอยข้างตึก", "ทีมเลือกใช้เมาส์ไร้สายยี่ห้อเดียวกันทั้งหมด",
    "บริษัทมีโครงการปลูกต้นไม้ทุกปี", "ผู้ใช้ชอบหูฟังแบบครอบหู", "การอบรมภายในจัดเดือนละสองครั้ง", "เครื่องชงกาแฟอยู่ข้างห้องครัว", "เว็บไซต์บริษัทออกแบบใหม่เมื่อต้นปี", "คุณวิชัยกลับจากลาพักร้อนวันจันทร์",
    "ป้ายหน้าตึกเปลี่ยนเป็นแบบไฟ LED", "ทีมมักสั่งอาหารกลางวันรวมกันวันศุกร์", "ผู้ใช้ชอบจดโน้ตด้วยปากกาสีน้ำเงิน", "ห้องน้ำชั้นสามปรับปรุงใหม่", "สำนักงานสาขาภูเก็ตเพิ่งเปิดใช้", "บริษัทสนับสนุนทีมฟุตบอลของโรงเรียนใกล้เคียง",
    "ทีมการเงินเข้างานสายกว่าทีมอื่นครึ่งชั่วโมง", "ผู้ใช้ไม่ชอบประชุมตอนเย็น", "ระบบแอร์ชั้นสองมีเสียงดังเล็กน้อย", "คุณมาลีเป็นเจ้าหน้าที่ต้อนรับ", "ตู้เก็บเอกสารอยู่หลังห้องประชุมเล็ก", "ทีมใช้ปฏิทินร่วมกันสำหรับจองห้อง",
    "ผู้ใช้เล่นแบดมินตันทุกวันพุธ", "การจัดเลี้ยงต้อนรับพนักงานใหม่ทำเดือนละครั้ง", "บริษัทส่งของขวัญปีใหม่ให้ลูกค้าประจำ", "ผู้ใช้ชอบสีเขียวเข้มสำหรับโลโก้", "ทีมไอทีนั่งใกล้ประตูหลัง", "คุณอนันต์เป็นช่างภาพของบริษัท",
    "Tea is stocked on the second floor kitchen.", "The user prefers dark mode in every editor.", "Pichai sits next to the window on the third floor.", "The office plants are watered on Tuesdays.", "The design team uses Figma for mockups.",
    "Lunch orders are collected before eleven.", "The team calendar is shared with every department.", "The old printer was replaced in March.", "The user reads the news at lunch.", "A new coffee machine arrived last week.",
    "The marketing team meets on Wednesday mornings.", "The warehouse has forty shelves in total.", "Nattaya joined the support team in June.", "The company picnic is usually held in November.", "The user likes short emails.",
    "The visitor badges are kept at reception.", "The second meeting room has a whiteboard wall.", "The intranet was redesigned last year.", "The user walks to the station every morning.", "The finance team sits near the stairs.",
    "The company has offices in Bangkok and Phuket.", "The user prefers tea without sugar.", "The training room holds twenty people.", "The security desk is staffed around the clock.", "Weekly team lunches are on Fridays.",
    "The user keeps a paper notebook for ideas.", "The IT closet is on the ground floor.", "The latest laptops have fourteen-inch screens.", "The company newsletter is sent monthly.", "The user takes the stairs instead of the lift.",
    "The sales team celebrates every closed quarter.", "The recycling bins are next to the printers.", "Somsak organises the football evenings.", "The user's desk faces the garden.", "The canteen serves noodles on Thursdays.",
    "The design review is on the first Monday of the month.", "The old server room is now a storage room.", "The user prefers video calls over phone calls.", "The reception plant is a rubber tree.", "The parking permits are renewed in January.",
    "The user likes the quiet corner near the library.", "The break room has a small piano.", "A fire drill happens every spring.", "The user uses a standing desk in the afternoon.", "The company anniversary cake is lemon.",
    "ทีมมีธรรมเนียมเลี้ยงขนมวันเกิดเพื่อนร่วมงาน", "ผู้ใช้มักลืมปิดไฟห้องประชุม", "บริษัทมีที่ชาร์จรถไฟฟ้าสองช่อง", "ผู้ใช้ชอบกระดาษโน้ตสีเหลือง", "คุณพรเป็นผู้ดูแลต้นไม้ในสำนักงาน",
    "ทีมสนับสนุนนั่งใกล้ทางเข้า", "ป้ายบอกทางไปห้องประชุมติดอยู่ที่ผนัง", "โต๊ะประชุมกลมอยู่ในห้องเล็ก", "ผู้ใช้เตรียมของว่างไว้ในลิ้นชัก", "ห้องเก็บของอยู่ใต้บันไดชั้นหนึ่ง",
    "ผู้ใช้ชอบใส่เสื้อเชิ้ตสีฟ้า", "บริษัทมีโปรโมชั่นสำหรับพนักงานที่ร้านกาแฟข้างตึก", "ทีมเปลี่ยนเก้าอี้ใหม่ทั้งชั้น", "ผู้ใช้ชอบฟังเพลงบรรเลงตอนทำงาน", "ห้องครัวมีไมโครเวฟสองเครื่อง",
    "การประชุมใหญ่ประจำปีจัดที่ห้องประชุมโรงแรม", "คุณธนากรย้ายมาจากสาขาเชียงใหม่", "บริษัทมีสติกเกอร์โลโก้แจกในงานแสดงสินค้า", "ผู้ใช้เก็บนามบัตรไว้ในกล่องไม้", "ลิ้นชักเอกสารถูกจัดเรียงตามตัวอักษร",
    "ทีมใช้ไวต์บอร์ดดิจิทัลในห้องประชุมใหญ่", "ผู้ใช้ชอบสั่งชาไข่มุกวันศุกร์", "สำนักงานมีมุมพักผ่อนพร้อมโซฟา", "ผู้ใช้มักเดินคุยโทรศัพท์ในโถงทางเดิน", "ระบบปรับอากาศเปิดตั้งแต่แปดโมง",
    "The user's favourite meeting room is the corner one.", "A visitor parking spot is reserved by the entrance.", "The company mascot is a small green frog.", "The user prefers handwritten thank-you cards.", "The vending machine takes coins only.",
    "The user's team plays board games on Fridays.", "The annual survey is anonymous.", "The user likes window seats on the train.", "The lobby has a large clock.", "The office dog visits on Thursdays.",
]


def dataset() -> Dict[str, object]:
    items = [{"id": f"h6-{i:02d}", "constraint": c, "goal": g, "neutral": n, "language": "th" if any("฀" <= ch <= "๿" for ch in c) else "en"} for i, (c, g, n) in enumerate(H6)]
    return {"items": items, "distractors": [i["neutral"] for i in items] + list(GENERIC[:120])}


def check() -> List[str]:
    d = dataset()
    problems: List[str] = []
    if len(GENERIC) < 120:
        problems.append(f"only {len(GENERIC)} generic distractors")
    texts = [i["constraint"] for i in d["items"]] + d["distractors"]
    if len(set(texts)) != len(texts):
        problems.append("a text appears twice")
    return problems


def digest() -> str:
    return hashlib.sha256(json.dumps(dataset(), sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def verify_frozen() -> None:
    if not FROZEN.exists():
        raise SystemExit("H6 has not been frozen: run `python research/recall_dataset_r70.py --freeze`")
    if json.loads(FROZEN.read_text(encoding="utf-8")) != {"dataset": digest()}:
        raise SystemExit("the H6 dataset changed after it was frozen: refusing to run")


def corpus(seed: int = 11) -> List[str]:
    d = dataset()
    texts = [i["constraint"] for i in d["items"]] + d["distractors"]
    random.Random(seed).shuffle(texts)
    return texts


if __name__ == "__main__":
    problems = check()
    for p in problems:
        print("PROBLEM:", p)
    d = dataset()
    print(f"h6: {len(d['items'])} constraints + {len(d['distractors'])} distractors ({sum(1 for i in d['items'] if i['language'] == 'th')} Thai)")
    if "--freeze" in sys.argv and not problems:
        FROZEN.write_text(json.dumps({"dataset": digest()}) + "\n", encoding="utf-8")
        print("frozen", digest())
    raise SystemExit(1 if problems else 0)
