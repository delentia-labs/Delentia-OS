"""
Round 69: held-out recall sets, written BEFORE any recall variant was run on them (criteria: research/round69_criteria.md section 2).

  H1  40 new English facts, a paraphrased question for each, 160 near-duplicate distractors
  H2  30 Thai facts + 10 Thai/English mixed facts, a paraphrased question for each (the question is in the other language for the mixed ones), 90 distractors
  H3  20 facts stored twice (an old value, then a newer one that says it changed) and 10 memories that are revoked afterwards
  SCALE  the Round 68 set (DEV) plus 1,000 extra distractors

A system "hits" a question when the ANSWER VALUE appears in any of its top-k results. Distractors are checked never to contain an answer value (whole-token match), so a hit cannot be an accident.
The sets are built once and their SHA-256 is printed by `python research/recall_dataset_r69.py --freeze` into research/recall_dataset_r69.sha256; a later run refuses to proceed if the data changed.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parent
FROZEN = ROOT / "recall_dataset_r69.sha256"

# (fact, paraphrased question, answer value)
H1: List[Tuple[str, str, str]] = [
    ("Employees accrue 1.5 vacation days per month of service.", "How quickly do staff build up paid time off?", "1.5 vacation days"),
    ("The printer on the third floor is named LaserJet-Orchid.", "What is the label of the copier two flights above the ground level?", "LaserJet-Orchid"),
    ("Visitors must sign in at the front desk and wear a green lanyard.", "What colour strap are guests given on arrival?", "green lanyard"),
    ("The CFO, Rattanaporn, approves any expense above 50,000 baht.", "Who has to authorise a large spend?", "Rattanaporn"),
    ("Our Kubernetes cluster is named harbor-prod and runs version 1.29.", "Which release of the container orchestrator do we operate?", "1.29"),
    ("Lunch is served in the canteen between 11:30 and 13:00.", "During which hours can employees eat their midday meal on site?", "11:30"),
    ("Passwords must be at least 14 characters long.", "What is the minimum length for a login secret?", "14 characters"),
    ("The annual audit is performed by Kasikorn Assurance in November.", "Which outside firm checks our books every year?", "Kasikorn Assurance"),
    ("Forklift certification expires every 24 months.", "How often must the lift-truck driver licence be renewed?", "24 months"),
    ("Customer complaints go to complaints@northwind.example and are answered within 2 business days.", "Where should an unhappy client send their grievance?", "complaints@northwind.example"),
    ("The conference room Sapphire seats 18 people.", "How many can fit in the meeting space named after a blue gem?", "18 people"),
    ("Shipping to Chiang Mai takes 3 days by the standard courier.", "How long does ordinary delivery to the northern city take?", "3 days"),
    ("The VPN gateway is vpn.northwind.example on port 4433.", "Which network port does the secure tunnel endpoint listen on?", "4433"),
    ("The janitorial contract is held by CleanWave and ends in June.", "Which company looks after cleaning?", "CleanWave"),
    ("Interns receive a monthly allowance of 9,000 baht.", "How much pocket money do trainees get each month?", "9,000"),
    ("The incident post-mortem must be written within 5 working days.", "By when must the review document after an outage be completed?", "5 working days"),
    ("The chief executive's assistant is Ladda, extension 2210.", "Which extension reaches the head boss's secretary?", "2210"),
    ("Source code is stored in the GitLab group northwind-core.", "Where do we keep our programs' repositories?", "northwind-core"),
    ("The loyalty programme gives 1 point per 25 baht spent.", "How many baht must a shopper spend to earn a reward unit?", "25 baht"),
    ("The cafeteria is closed on Mondays for deep cleaning.", "Which weekday can we not buy food at the staff restaurant?", "Mondays"),
    ("Fire drills happen on the first Thursday of every quarter.", "When do we rehearse building evacuations?", "first Thursday"),
    ("The default branch of the website repository is trunk.", "What is the main line called in the web project's version control?", "trunk"),
    ("Parking permits cost 600 baht per month and are issued by Security.", "What is the fee for a car space pass?", "600 baht"),
    ("CCTV footage is kept for 30 days.", "How long do we hold on to video from the surveillance cameras?", "30 days"),
    ("Dr. Siriwan is the company physician and is on site on Wednesdays.", "Which day can staff see the in-house doctor?", "Wednesdays"),
    ("The monthly newsletter goes out on the last Friday.", "When is the company bulletin sent to everyone?", "last Friday"),
    ("Laptops are replaced every 4 years.", "After how many years does a staff computer get swapped for a new one?", "4 years"),
    ("The emergency assembly point is the car park behind building C.", "Where do we gather if the premises must be evacuated?", "building C"),
    ("Translation work is outsourced to LinguaBridge.", "Which agency handles converting documents between languages?", "LinguaBridge"),
    ("The guest Wi-Fi network is Northwind-Visitors and its code changes weekly.", "What is the name of the wireless network for outside people?", "Northwind-Visitors"),
    ("Expense reports are due on the 5th of the following month.", "By what date must reimbursement claims be filed?", "5th"),
    ("The backup generator is tested every second Saturday.", "How often do we trial the standby power unit?", "second Saturday"),
    ("The cold room must stay between 2 and 4 degrees Celsius.", "What temperature range must the refrigerated storage hold?", "2 and 4 degrees"),
    ("Maternity leave is 98 days with full pay.", "How long can a new mother stay away from work while still paid?", "98 days"),
    ("Ticket priority P1 means the whole service is down.", "What does the most severe support category indicate?", "whole service is down"),
    ("The company anniversary is celebrated on 17 March.", "On which date does the firm hold its yearly birthday party?", "17 March"),
    ("The procurement portal is buy.northwind.example.", "Where do staff go online to request purchases?", "buy.northwind.example"),
    ("Security guards change shift at 06:00 and 18:00.", "When do the watchmen swap?", "06:00 and 18:00"),
    ("Customer data may only be exported by the Data Protection Officer, Arunee.", "Who alone is allowed to extract client records?", "Arunee"),
    ("The standard warranty on our products is 18 months.", "For how long do we repair goods free after sale?", "18 months"),
]

H2: List[Tuple[str, str, str]] = [
    ("ผู้จัดการฝ่ายบุคคลชื่อคุณสุดา และนั่งอยู่ชั้น 4", "ใครดูแลเรื่องพนักงานในบริษัท", "สุดา"),
    ("พนักงานใหม่ต้องผ่านการทดลองงาน 119 วัน", "ช่วงทดสอบความสามารถของคนที่เพิ่งเข้าทำงานนานเท่าไร", "119 วัน"),
    ("เงินเดือนออกทุกวันที่ 25 ของเดือน", "บริษัทโอนค่าจ้างให้พนักงานวันไหน", "วันที่ 25"),
    ("ลาป่วยเกิน 4 วันต้องมีใบรับรองแพทย์", "ต้องแนบเอกสารจากหมอเมื่อหยุดงานเพราะไม่สบายกี่วันขึ้นไป", "4 วัน"),
    ("ห้องประชุมใหญ่ชื่อราชพฤกษ์ จุคนได้ 40 ที่นั่ง", "สถานที่ที่ใช้ประชุมทั้งบริษัทรองรับคนได้กี่คน", "40 ที่นั่ง"),
    ("พัสดุที่ส่งต่างจังหวัดใช้บริการขนส่งของ Kerry", "ของที่ส่งออกนอกกรุงเทพฯ ใช้บริษัทไหนขนส่ง", "Kerry"),
    ("รหัสผ่านไวไฟของออฟฟิศคือ Banana2026", "ต้องกรอกอะไรเพื่อเชื่อมต่ออินเทอร์เน็ตไร้สายในสำนักงาน", "Banana2026"),
    ("ร้านอาหารประจำของทีมคือครัวคุณยาย ซอยทองหล่อ", "ทีมมักไปกินข้าวร้านไหนด้วยกัน", "ครัวคุณยาย"),
    ("ประกันสุขภาพของพนักงานวงเงิน 500,000 บาทต่อปี", "บริษัทคุ้มครองค่ารักษาพยาบาลให้สูงสุดเท่าไรต่อปี", "500,000"),
    ("คุณวิชัยดูแลระบบเครือข่ายและติดต่อได้ที่เบอร์ภายใน 3345", "โทรหาเรื่องอินเทอร์เน็ตล่มต้องกดต่อเบอร์ไหน", "3345"),
    ("บริษัทหยุดวันสงกรานต์ตั้งแต่ 13 ถึง 15 เมษายน", "เทศกาลปีใหม่ไทยออฟฟิศปิดช่วงไหน", "13 ถึง 15 เมษายน"),
    ("ที่จอดรถชั้นใต้ดินสำหรับผู้บริหารเท่านั้น", "ใครมีสิทธิ์จอดรถชั้นล่างสุดของตึก", "ผู้บริหาร"),
    ("เซิร์ฟเวอร์สำรองข้อมูลตั้งอยู่ที่ศูนย์ข้อมูลบางนา", "สำเนาของข้อมูลถูกเก็บไว้ที่ไหน", "บางนา"),
    ("การประชุมประจำสัปดาห์ของทีมขายคือทุกวันพฤหัสบดี 9 โมงเช้า", "ทีมขายนัดพบกันเมื่อไรเป็นประจำ", "วันพฤหัสบดี"),
    ("ค่าเดินทางไปต่างประเทศเบิกได้วันละ 2,500 บาท", "เบี้ยเลี้ยงสำหรับไปทำงานต่างแดนต่อวันเท่าไร", "2,500"),
    ("ลูกค้าคืนสินค้าได้ภายใน 7 วันพร้อมใบเสร็จ", "ผู้ซื้อต้องส่งของกลับภายในกี่วันถ้าไม่พอใจ", "7 วัน"),
    ("หัวหน้าฝ่ายไอทีชื่อคุณธนากร", "ใครเป็นนายใหญ่ของแผนกคอมพิวเตอร์", "ธนากร"),
    ("สัญญาทุกฉบับต้องผ่านทนายความชื่อคุณปรียาก่อนลงนาม", "ก่อนเซ็นสัญญาต้องให้ใครตรวจทางกฎหมาย", "ปรียา"),
    ("ตู้กดน้ำร้อนอยู่ที่ห้องครัวชั้น 2", "จะชงกาแฟต้องไปที่ไหนของตึก", "ห้องครัวชั้น 2"),
    ("ระบบบัญชีที่ใช้คือ FlowAccount", "บริษัทใช้โปรแกรมอะไรทำบัญชี", "FlowAccount"),
    ("งานเลี้ยงสิ้นปีจัดที่โรงแรมริเวอร์ไซด์", "ปาร์ตี้ปลายปีของบริษัทไปจัดที่ไหน", "ริเวอร์ไซด์"),
    ("ทุนการศึกษาพนักงานให้ปีละ 30,000 บาท", "พนักงานที่อยากเรียนต่อได้เงินสนับสนุนเท่าไรต่อปี", "30,000"),
    ("ลูกค้า VIP จะได้ส่วนลด 12 เปอร์เซ็นต์", "สมาชิกระดับสูงสุดได้ลดราคากี่เปอร์เซ็นต์", "12 เปอร์เซ็นต์"),
    ("ผู้ตรวจสอบภายในรายงานตรงต่อคณะกรรมการ", "ฝ่ายตรวจสอบภายในต้องส่งรายงานให้ใคร", "คณะกรรมการ"),
    ("รถตู้ของบริษัทออกจากสำนักงานเวลา 17:45 น.", "รถรับส่งพนักงานกลับบ้านออกกี่โมง", "17:45"),
    ("ใบอนุญาตประกอบกิจการหมดอายุเดือนธันวาคม", "ต้องต่อใบอนุญาตทำธุรกิจภายในเดือนใด", "ธันวาคม"),
    ("ห้องปฐมพยาบาลอยู่ติดกับลิฟต์ตัวที่ 2", "ถ้ามีคนบาดเจ็บไปขอยาที่ไหน", "ลิฟต์ตัวที่ 2"),
    ("ผู้ให้บริการอินเทอร์เน็ตคือ AIS Fibre และสัญญาหมดปีหน้า", "เราใช้เน็ตเจ้าไหน", "AIS Fibre"),
    ("ค่าล่วงเวลาคิดเป็น 1.5 เท่าของค่าจ้างปกติ", "ทำงานเกินเวลาได้เงินเพิ่มกี่เท่า", "1.5 เท่า"),
    ("แผนสำรองกรณีไฟดับคือใช้เครื่องปั่นไฟที่ดาดฟ้า", "ถ้าไฟฟ้าขัดข้องจะใช้อะไรแทน", "เครื่องปั่นไฟ"),
    # mixed: fact and question in different languages
    ("The Thai office manager is คุณมาลี and she covers visas.", "ใครดูแลเรื่องวีซ่าให้พนักงานต่างชาติ", "มาลี"),
    ("ระบบ ticketing ของเราคือ Jira และ project key คือ HRB", "What prefix do our issue numbers have?", "HRB"),
    ("Our bank is Kasikorn and the account manager is คุณอรทัย.", "ผู้จัดการบัญชีธนาคารของบริษัทชื่ออะไร", "อรทัย"),
    ("ประชุมใหญ่ประจำปีจัดที่เชียงใหม่ทุกเดือนกุมภาพันธ์", "Which month is the yearly general meeting?", "กุมภาพันธ์"),
    ("The sprint length is 2 weeks, สรุปงานทุกวันศุกร์เย็น", "How long is each development iteration?", "2 weeks"),
    ("บริษัทใช้ Slack ช่อง #ข่าวสาร สำหรับประกาศ", "Which channel carries official announcements?", "#ข่าวสาร"),
    ("The CTO คุณประสิทธิ์ signs off production deploys", "ใครอนุมัติการขึ้นระบบจริง", "ประสิทธิ์"),
    ("ค่าธรรมเนียมโอนเงินระหว่างประเทศคือ 350 baht ต่อรายการ", "How much do we pay per overseas transfer fee?", "350 baht"),
    ("The hotline คือ 1669-123 and is answered 24 hours", "เบอร์สายด่วนของบริษัทคืออะไร", "1669-123"),
    ("นโยบาย work from home คือ 2 วันต่อสัปดาห์", "How many days may we work remotely each week?", "2 วัน"),
]

# (older fact, newer fact, question asked "now", answer in the newer, answer in the older)
H3_UPDATES: List[Tuple[str, str, str, str, str]] = [
    ("The refund window is 14 days.", "The refund window was changed and is now 30 days.", "What is the current refund window?", "30 days", "14 days"),
    ("The support hotline is 02-111-2233.", "The support hotline has moved to 02-777-8899.", "Which number do we call for support today?", "02-777-8899", "02-111-2233"),
    ("The deploy day is Tuesday.", "Deploys now happen on Thursday instead.", "Which weekday do releases go out now?", "Thursday", "Tuesday"),
    ("Our cloud vendor is Cumulus.", "We switched our cloud vendor to Nimbify.", "Who hosts our servers at the moment?", "Nimbify", "Cumulus"),
    ("The office opens at 08:00.", "The office now opens at 09:30.", "At what time do the doors open currently?", "09:30", "08:00"),
    ("Parking costs 400 baht a month.", "Parking now costs 750 baht a month.", "What is the present price of a car-park pass?", "750 baht", "400 baht"),
    ("The team lead is Narin.", "The team lead is now Pattama, replacing Narin.", "Who leads the team at the moment?", "Pattama", "Narin"),
    ("Backups are kept for 20 days.", "Backups are now kept for 45 days.", "How long are copies retained these days?", "45 days", "20 days"),
    ("The staging server is stg-alpha.", "The staging server was renamed to stg-omega.", "What is the pre-release environment called now?", "stg-omega", "stg-alpha"),
    ("The weekly meeting is at 10:00.", "The weekly meeting moved to 15:30.", "When is the regular get-together held at present?", "15:30", "10:00"),
    ("Orders over 1,000 baht ship free.", "Orders over 2,500 baht ship free from now on.", "What is the current threshold for free delivery?", "2,500 baht", "1,000 baht"),
    ("The CEO's extension is 1100.", "The CEO's extension is now 1188.", "Which extension reaches the chief at present?", "1188", "1100"),
    ("Interviews are held in Room Pine.", "Interviews are now held in Room Cedar.", "Which room hosts candidate meetings now?", "Cedar", "Pine"),
    ("The sandbox password rotates every 60 days.", "The sandbox password now rotates every 30 days.", "How often is the test credential changed currently?", "every 30 days", "every 60 days"),
    ("The warranty is 12 months.", "The warranty has been extended to 24 months.", "How long is the guarantee at the moment?", "24 months", "12 months"),
    ("The payroll date is the 25th.", "Payroll moved to the 28th.", "On which day of the month is pay delivered now?", "28th", "25th"),
    ("Our courier is SwiftBox.", "We changed our courier to RoadRunner.", "Which delivery company do we use today?", "RoadRunner", "SwiftBox"),
    ("The API limit is 60 requests per minute.", "The API limit was raised to 300 requests per minute.", "How many calls per minute are allowed now?", "300 requests", "60 requests"),
    ("The data centre is in Rayong.", "The data centre moved to Chonburi.", "Where are the servers located at present?", "Chonburi", "Rayong"),
    ("Lunch break is 12:00 to 13:00.", "Lunch break is now 11:45 to 12:45.", "What are the midday break hours currently?", "11:45", "12:00 to 13:00"),
]

# memories that are revoked after being stored; asking about them must never bring them back
H3_REVOKED: List[Tuple[str, str, str]] = [
    ("The admin portal password is Quartz-7781-lamp.", "What is the admin portal password?", "Quartz-7781-lamp"),
    ("Khun Boonmee's personal phone is 081-555-0119.", "How do I reach Boonmee on a private number?", "081-555-0119"),
    ("The office alarm code is 482915.", "What code disarms the alarm system?", "482915"),
    ("The spare key is under the blue pot on the 5th floor terrace.", "Where is the backup door key hidden?", "blue pot"),
    ("Salary of the new hire Chanida is 92,000 baht.", "How much is Chanida paid?", "92,000 baht"),
    ("The wire transfer PIN is 6620.", "What PIN confirms bank transfers?", "6620"),
    ("The safe combination is 14-27-03.", "What is the vault combination?", "14-27-03"),
    ("The old contractor Yodsak was dismissed for fraud.", "Why did Yodsak leave?", "dismissed for fraud"),
    ("The test-user token is tok_live_zz91.", "Which credential does the test account use?", "tok_live_zz91"),
    ("The marketing budget draft is 3.2 million baht.", "How big is the advertising budget draft?", "3.2 million"),
]


def _boundary(value: str) -> "re.Pattern[str]":
    """Whole-token match for Latin text and numbers ("5th" is not inside "25th", "True" not inside "construe"), plain substring for Thai (it has no spaces between words)."""
    v = value.lower()
    first, last = v[0], v[-1]
    before = r"(?<![0-9.,])" if first.isdigit() else (r"(?<![a-z0-9_])" if first.isascii() and first.isalnum() else "")
    after = r"(?![0-9])" if last.isdigit() else (r"(?![a-z0-9_])" if last.isascii() and last.isalnum() else "")
    return re.compile(before + re.escape(v) + after)


EN_TEMPLATES = [
    "Our {role} is {name} and works from the {place} office.", "The {thing} closes at {time} on {day}.", "The {thing} for {what} is reviewed every {n} weeks.",
    "The main {supplier} vendor is {name}; the backup vendor is {name2}.", "The {env} service is called {svc}.", "The monthly {cost} budget is capped at {amount} baht.",
    "{name} gives access to the {area} section.", "The {job} runs nightly at {time} and is kept for {n} weeks.", "Orders over {amount} baht ship within {city}.",
    "The {tool} limit is {n} requests per hour.", "{name} is the contact for {topic}.", "The {team} meeting is held every {day} at {time}.",
    "Staff in the {team} team use the {tool} tool on {day}.", "The {thing} must be inspected every {n} weeks by {name}.", "{name} manages the {area} budget for the {team} team.",
]
EN_FILL = {
    "role": ["legal liaison", "finance contact", "security officer", "procurement lead", "facilities manager", "payroll clerk", "safety officer"],
    "name": ["Somsak", "Nattaya", "Kritsada", "Ploy", "Anan", "Wipa", "Surasak", "Mali", "Pichai", "Duangjai", "Chai", "Orasa", "Piya", "Rungnapha"],
    "name2": ["CartonCo", "WrapIt", "SafeBox", "ShipPack", "TapeWorks", "FoamLine", "PackRight"],
    "place": ["Rayong", "Phuket", "Korat", "Hat Yai", "Ayutthaya", "Khon Kaen"],
    "thing": ["loading dock", "back office", "parts store", "meeting room", "server room", "reception", "archive room"],
    "what": ["spare cables", "visitor badges", "office keys", "safety gear"],
    "day": ["Tuesday", "Friday", "Sunday", "Saturday", "Monday"],
    "time": ["06:45", "09:15", "13:10", "16:20", "21:00", "18:30"],
    "supplier": ["labelling", "cleaning", "catering", "printing", "security"],
    "env": ["demo", "training", "analytics", "archive", "reporting"],
    "svc": ["demo-db-5", "trn-db-2", "arch-db-9", "rep-db-4"],
    "cost": ["travel", "training", "printing", "cloud", "stationery"],
    "amount": ["1,350", "4,200", "40,300", "7,800", "12,400"],
    "area": ["dry goods", "chemical", "records", "spare parts", "packaging"],
    "job": ["backup", "report export", "log rotation", "index rebuild"],
    "city": ["Nonthaburi", "Pattaya", "Hua Hin", "Udon Thani"],
    "tool": ["upload", "billing", "search", "export", "messaging"],
    "topic": ["visa paperwork", "uniform sizes", "parking stickers", "locker keys", "badge photos"],
    "team": ["finance", "marketing", "support", "legal", "research", "logistics"],
    "n": ["3", "6", "8", "9", "11"],
}
TH_TEMPLATES = [
    "ผู้ดูแลเรื่อง{topic}คือคุณ{name}", "ห้อง{room}อยู่ที่ชั้น {n} ของอาคาร", "ฝ่าย{team}ประชุมกันทุกวัน{day}", "ค่า{cost}ของฝ่าย{team}ไม่เกิน {amount} บาทต่อเดือน",
    "คุณ{name}เป็นผู้ติดต่อเรื่อง{topic}", "ระบบ{tool}ให้บริการตลอดเวลา ยกเว้นวัน{day}", "ใบอนุญาต{topic}ต้องต่ออายุทุก {n} ปี", "ร้าน{shop}อยู่หน้าอาคารเปิดถึง {time} น.",
    "พนักงานฝ่าย{team}ต้องอบรมเรื่อง{topic}ปีละ {n} ครั้ง", "ห้อง{room}ใช้ได้เฉพาะฝ่าย{team}",
]
TH_FILL = {
    "topic": ["ยูนิฟอร์ม", "บัตรจอดรถ", "ลูกกุญแจ", "ความปลอดภัย", "ภาษีหัก ณ ที่จ่าย", "เครื่องเขียน"],
    "name": ["สมชาย", "นฤมล", "กิตติ", "พิมพ์ใจ", "อนันต์", "วิภา", "ประเสริฐ", "มณี", "พิชัย", "ดวงใจ"],
    "room": ["ประชุมเล็ก", "เก็บเอกสาร", "อบรม", "พักผ่อน", "ซ้อมดับเพลิง"],
    "n": ["2", "3", "5", "6", "8"],
    "team": ["การเงิน", "การตลาด", "บริการลูกค้า", "กฎหมาย", "วิจัย", "โลจิสติกส์"],
    "day": ["อังคาร", "ศุกร์", "เสาร์", "อาทิตย์", "จันทร์"],
    "cost": ["เดินทาง", "อบรม", "พิมพ์งาน", "เครื่องเขียน", "ซ่อมบำรุง"],
    "amount": ["1,200", "4,800", "8,500", "15,000", "22,000"],
    "tool": ["ใบแจ้งหนี้", "ค้นหาเอกสาร", "ส่งข้อความ", "รายงานยอดขาย"],
    "shop": ["กาแฟ", "ซักรีด", "ขนมปัง", "เครื่องเขียน"],
    "time": ["20:30", "19:00", "21:15", "18:45"],
}


def _fill(template: str, pools: Dict[str, List[str]], rng: random.Random) -> str:
    def pick(m: "re.Match[str]") -> str:
        return rng.choice(pools[m.group(1)])
    return re.sub(r"\{(\w+)\}", pick, template)


def _distractors(templates: List[str], pools: Dict[str, List[str]], count: int, answers: List[str], seed: int, avoid_texts: List[str]) -> List[str]:
    rng = random.Random(seed)
    bad = [_boundary(a) for a in answers]
    out: List[str] = []
    seen = set(avoid_texts)
    guard = 0
    while len(out) < count and guard < count * 200:
        guard += 1
        text = _fill(rng.choice(templates), pools, rng)
        if text in seen or any(b.search(text.lower()) for b in bad):
            continue
        seen.add(text)
        out.append(text)
    assert len(out) == count, (len(out), count)
    return out


def dataset() -> Dict[str, object]:
    h1_answers = [a for _f, _q, a in H1]
    h2_answers = [a for _f, _q, a in H2]
    h1 = {"facts": [{"id": f"h1-{i:02d}", "text": f, "question": q, "answer": a} for i, (f, q, a) in enumerate(H1)],
          "distractors": _distractors(EN_TEMPLATES, EN_FILL, 160, h1_answers, 6901, [f for f, _q, _a in H1])}
    h2 = {"facts": [{"id": f"h2-{i:02d}", "text": f, "question": q, "answer": a} for i, (f, q, a) in enumerate(H2)],
          "distractors": _distractors(TH_TEMPLATES, TH_FILL, 90, h2_answers, 6902, [f for f, _q, _a in H2])}
    h3 = {"updates": [{"id": f"h3-{i:02d}", "old": o, "new": n, "question": q, "answer_new": an, "answer_old": ao} for i, (o, n, q, an, ao) in enumerate(H3_UPDATES)],
          "revoked": [{"id": f"h3r-{i:02d}", "text": t, "question": q, "secret": s} for i, (t, q, s) in enumerate(H3_REVOKED)]}
    return {"h1": h1, "h2": h2, "h3": h3}


def scale_distractors(count: int = 1000) -> List[str]:
    """Extra distractors for the SCALE test: the English templates again, with a different seed, never containing an answer of DEV or H1."""
    sys.path.insert(0, str(ROOT))
    import recall_dataset_r68 as dev
    answers = [f["answer"] for f in dev.dataset()["facts"]] + [a for _f, _q, a in H1]
    return _distractors(EN_TEMPLATES, EN_FILL, count, answers, 6903, [f for f, _q, _a in H1])


def check() -> List[str]:
    """Problems found (empty list = fine)."""
    problems: List[str] = []
    d = dataset()
    for name in ("h1", "h2"):
        facts, distractors = d[name]["facts"], d[name]["distractors"]
        answers = [f["answer"] for f in facts]
        if len(set(a.lower() for a in answers)) != len(answers):
            problems.append(f"{name}: two facts share an answer value")
        for f in facts:
            if not _boundary(f["answer"]).search(f["text"].lower()):
                problems.append(f"{name}: the answer '{f['answer']}' is not in its fact")
            hits = [g["id"] for g in facts if g is not f and _boundary(f["answer"]).search(g["text"].lower())]
            if hits:
                problems.append(f"{name}: the answer '{f['answer']}' also appears in {hits}")
            if any(_boundary(f["answer"]).search(t.lower()) for t in distractors):
                problems.append(f"{name}: a distractor contains the answer '{f['answer']}'")
    for u in d["h3"]["updates"]:
        if not _boundary(u["answer_new"]).search(u["new"].lower()) or not _boundary(u["answer_old"]).search(u["old"].lower()):
            problems.append(f"h3 {u['id']}: an answer value is not in its fact")
    for r in d["h3"]["revoked"]:
        if not _boundary(r["secret"]).search(r["text"].lower()):
            problems.append(f"h3 {r['id']}: the secret is not in its text")
    return problems


def digest() -> Dict[str, str]:
    d = dataset()
    blob = json.dumps(d, sort_keys=True, ensure_ascii=False).encode("utf-8")
    scale = json.dumps(scale_distractors(), ensure_ascii=False).encode("utf-8")
    return {"dataset": hashlib.sha256(blob).hexdigest(), "scale": hashlib.sha256(scale).hexdigest()}


def verify_frozen() -> None:
    if not FROZEN.exists():
        raise SystemExit("the dataset has not been frozen yet: run `python research/recall_dataset_r69.py --freeze` first")
    recorded = json.loads(FROZEN.read_text(encoding="utf-8"))
    if recorded != digest():
        raise SystemExit("the Round 69 recall dataset changed after it was frozen: refusing to run (restore it, or write a new round)")


if __name__ == "__main__":
    problems = check()
    for p in problems:
        print("PROBLEM:", p)
    d = dataset()
    print(f"h1: {len(d['h1']['facts'])} facts + {len(d['h1']['distractors'])} distractors; h2: {len(d['h2']['facts'])} + {len(d['h2']['distractors'])}; h3: {len(d['h3']['updates'])} updates, {len(d['h3']['revoked'])} revoked")
    if "--freeze" in sys.argv:
        if problems:
            raise SystemExit("not freezing a dataset with problems")
        FROZEN.write_text(json.dumps(digest(), indent=2) + "\n", encoding="utf-8")
        print("frozen:", digest())
    raise SystemExit(1 if problems else 0)
