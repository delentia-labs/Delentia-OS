"""
Round 69 (part b): H5, a second Thai holdout, written after H2 had been measured and BEFORE any rule that depends on the language of the question was built (criteria: research/round69_criteria.md section 2c).

H2 is development data for the Thai weight (it was observed). H5 = 30 new Thai facts + 10 mixed Thai/English, other topics (warehouse, finance, safety, HR), a paraphrased question for each, 90 new Thai distractors.
The SHA-256 of the data is frozen in research/recall_dataset_r69b.sha256 (`--freeze`); `verify_frozen()` refuses to run on changed data.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import recall_dataset_r69 as base  # noqa: E402

FROZEN = ROOT / "recall_dataset_r69b.sha256"

H5: List[Tuple[str, str, str]] = [
    ("คลังสินค้าสาขาลำลูกกาเปิดรับสินค้าตั้งแต่ 7 โมงเช้า", "โกดังที่ปทุมธานีเริ่มรับของเข้ากี่โมง", "7 โมงเช้า"),
    ("ช่างซ่อมแอร์ประจำบริษัทคือคุณสมพงษ์", "ถ้าเครื่องปรับอากาศเสียต้องเรียกใคร", "สมพงษ์"),
    ("ค่าส่งพัสดุด่วนพิเศษคิดกิโลกรัมละ 45 บาท", "ส่งของแบบเร่งด่วนคิดเงินเท่าไรต่อน้ำหนักหนึ่งกิโล", "45 บาท"),
    ("ตู้เซฟเก็บเงินสดอยู่ในห้องบัญชีชั้น 3", "เงินสดของบริษัทถูกเก็บไว้ที่ไหน", "ห้องบัญชีชั้น 3"),
    ("นักเรียนฝึกงานต้องรายงานตัวกับคุณกัญญา", "เด็กที่มาฝึกงานต้องไปพบใครวันแรก", "กัญญา"),
    ("สัญญาเช่าสำนักงานครบกำหนดเดือนมิถุนายนปีหน้า", "ต้องย้ายหรือต่อสัญญาที่ทำงานเมื่อไร", "มิถุนายน"),
    ("เครื่องถ่ายเอกสารเสียให้โทรแจ้งเบอร์ 02-444-7788", "ถ้าก๊อปปี้เสียต้องติดต่อหมายเลขไหน", "02-444-7788"),
    ("รถขนส่งสินค้าสายเหนือออกทุกวันพุธตอนตี 4", "รถวิ่งไปภาคเหนือเดินทางวันไหน", "วันพุธ"),
    ("ค่าจอดรถลูกค้าฟรี 2 ชั่วโมงแรก", "ลูกค้าจอดรถโดยไม่เสียเงินได้นานเท่าไร", "2 ชั่วโมง"),
    ("ใบรับรองมาตรฐานคุณภาพของโรงงานคือ ISO 9001", "โรงงานได้รับการรับรองมาตรฐานอะไร", "ISO 9001"),
    ("หัวหน้าแม่บ้านชื่อป้าสมจิตร", "ใครคุมทีมทำความสะอาด", "สมจิตร"),
    ("โปรแกรมประชุมออนไลน์ที่ใช้ภายในคือ Zoom", "ประชุมทางไกลใช้แอปอะไร", "Zoom"),
    ("ต้องยื่นเอกสารประกันสังคมภายในวันที่ 15 มกราคม", "ต้องส่งเอกสารกองทุนประกันสังคมก่อนวันที่เท่าไร", "15 มกราคม"),
    ("ห้องสมุดของบริษัทให้ยืมหนังสือครั้งละไม่เกิน 3 เล่ม", "พนักงานยืมหนังสือได้สูงสุดกี่เล่มต่อครั้ง", "3 เล่ม"),
    ("ผู้ขายวัตถุดิบหลักคือบริษัทสยามฟู้ดส์", "ใครส่งของดิบให้โรงครัว", "สยามฟู้ดส์"),
    ("บัตรพนักงานหายต้องแจ้งฝ่ายรักษาความปลอดภัยภายใน 24 ชั่วโมง", "ทำบัตรประจำตัวสูญหายต้องรีบรายงานภายในเวลาเท่าไร", "24 ชั่วโมง"),
    ("ลิฟต์บรรทุกของจำกัดน้ำหนัก 800 กิโลกรัม", "ลิฟต์สำหรับขนสินค้ารับน้ำหนักได้สูงสุดเท่าไร", "800 กิโลกรัม"),
    ("ที่ปรึกษาด้านภาษีของบริษัทคือสำนักงานบัญชีธนชัย", "ใครช่วยดูเรื่องภาษีให้องค์กร", "ธนชัย"),
    ("การอบรมความปลอดภัยประจำปีจัดในเดือนตุลาคม", "คอร์สเซฟตี้ประจำปีมีเมื่อไร", "ตุลาคม"),
    ("พนักงานที่ทำงานครบ 5 ปีจะได้รับโบนัสพิเศษ 20,000 บาท", "อยู่ครบห้าปีได้เงินรางวัลเท่าไร", "20,000"),
    ("เครื่องชั่งน้ำหนักสินค้าถูกสอบเทียบทุก 6 เดือน", "ต้องตรวจเช็กความเที่ยงตรงของตาชั่งบ่อยแค่ไหน", "6 เดือน"),
    ("ช่องทางแจ้งเบาะแสทุจริตคืออีเมล ethics@northwind.example", "จะรายงานการโกงภายในองค์กรได้ทางไหน", "ethics@northwind.example"),
    ("โกดังเก็บสารเคมีต้องมีผู้ควบคุมชื่อคุณเอกชัย", "ใครรับผิดชอบพื้นที่เก็บของอันตราย", "เอกชัย"),
    ("ลูกค้าองค์กรชำระเงินภายใน 45 วันหลังออกใบแจ้งหนี้", "บริษัทลูกค้าต้องจ่ายหนี้ภายในกี่วัน", "45 วัน"),
    ("หน้าจอแสดงผลในห้องประชุมเชื่อมต่อผ่านสาย HDMI", "จะต่อโน้ตบุ๊กเข้ากับจอห้องประชุมใช้อะไร", "HDMI"),
    ("กล้องวงจรปิดบันทึกภาพทั้งวันทั้งคืนและเก็บไว้ 60 วัน", "ภาพจากกล้องรักษาความปลอดภัยถูกเก็บนานเท่าไร", "60 วัน"),
    ("ผู้ประสานงานโครงการก่อสร้างคือวิศวกรณรงค์", "ใครเป็นตัวกลางของงานก่อสร้าง", "ณรงค์"),
    ("รถรับส่งพนักงานรอบเช้าออกจากสถานีรถไฟฟ้า 07:15 น.", "บริการรับส่งตอนเช้าเริ่มจากสถานีกี่โมง", "07:15"),
    ("เครื่องดื่มในตู้แช่คิดราคาขวดละ 15 บาท", "น้ำดื่มในตู้เย็นของสำนักงานราคาเท่าไร", "15 บาท"),
    ("อุปกรณ์ดับเพลิงตรวจสอบทุกต้นเดือน", "ถังดับเพลิงถูกเช็กเมื่อไรของแต่ละเดือน", "ต้นเดือน"),
    # mixed
    ("The Bangkok depot manager is คุณวีรพงษ์", "ใครดูแลคลังที่กรุงเทพ", "วีรพงษ์"),
    ("ระบบ CRM ของเราคือ HubSpot", "Which customer database tool do we use?", "HubSpot"),
    ("The audit committee meets ทุกไตรมาส", "How often does the audit committee meet?", "ทุกไตรมาส"),
    ("ช่องทางสำหรับแจ้งปัญหาไอทีคือ #it-help", "Where do we report computer problems?", "#it-help"),
    ("Overtime must be approved by คุณสายฝน", "ใครต้องอนุมัติการทำงานล่วงเวลา", "สายฝน"),
    ("ราคาค่าบริการรายเดือนของ Premium plan คือ 1,990 บาท", "How much is the top subscription tier per month?", "1,990"),
    ("The warehouse code is WH-LKB", "รหัสของโกดังลำลูกกาคืออะไร", "WH-LKB"),
    ("ประกาศปิดบริษัทช่วงปีใหม่ 30 ธันวาคม ถึง 3 มกราคม", "When is the company closed over New Year?", "30 ธันวาคม"),
    ("Our payroll provider is คุณพิมพา at KBank", "ใครทำเงินเดือนให้พนักงาน", "พิมพา"),
    ("ความเร็วอินเทอร์เน็ตของออฟฟิศคือ 1 Gbps", "How fast is our office internet?", "1 Gbps"),
]


def dataset() -> Dict[str, object]:
    answers = [a for _f, _q, a in H5]
    return {"facts": [{"id": f"h5-{i:02d}", "text": f, "question": q, "answer": a} for i, (f, q, a) in enumerate(H5)],
            "distractors": base._distractors(base.TH_TEMPLATES, base.TH_FILL, 90, answers, 6905, [f for f, _q, _a in H5])}


def check() -> List[str]:
    d = dataset()
    facts, distractors = d["facts"], d["distractors"]
    problems: List[str] = []
    answers = [f["answer"] for f in facts]
    if len(set(a.lower() for a in answers)) != len(answers):
        problems.append("two facts share an answer value")
    for f in facts:
        if not base._boundary(f["answer"]).search(f["text"].lower()):
            problems.append(f"the answer '{f['id']}' is not in its fact")
        if [g["id"] for g in facts if g is not f and base._boundary(f["answer"]).search(g["text"].lower())]:
            problems.append(f"the answer of {f['id']} also appears in another fact")
        if any(base._boundary(f["answer"]).search(t.lower()) for t in distractors):
            problems.append(f"a distractor contains the answer of {f['id']}")
    return problems


def digest() -> str:
    return hashlib.sha256(json.dumps(dataset(), sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def verify_frozen() -> None:
    if not FROZEN.exists():
        raise SystemExit("H5 has not been frozen: run `python research/recall_dataset_r69b.py --freeze`")
    if json.loads(FROZEN.read_text(encoding="utf-8")) != {"dataset": digest()}:
        raise SystemExit("the H5 recall dataset changed after it was frozen: refusing to run")


if __name__ == "__main__":
    problems = check()
    for p in problems:
        print("PROBLEM:", p)
    print(f"h5: {len(dataset()['facts'])} facts + {len(dataset()['distractors'])} distractors")
    if "--freeze" in sys.argv and not problems:
        FROZEN.write_text(json.dumps({"dataset": digest()}) + "\n", encoding="utf-8")
        print("frozen", digest())
    raise SystemExit(1 if problems else 0)
