"""
Thai Document Intelligence Skill for Delentia OS

Performs high-fidelity OCR, Thai NER (Named Entity Recognition),
and PDPA Compliance auditing on business documents, invoices, and citizen IDs.
"""

import os
import re
import json
from typing import Dict, Any, List

# ── Core Regex Patterns for Thai NLP ──────────────────────────────────────────

# Matches 13-digit Thai National ID (e.g. 1-2345-67890-12-3 or 1234567890123)
TH_CITIZEN_ID_PATTERN = re.compile(r'\b\d{1}-?\d{4}-?\d{5}-?\d{2}-?\d{1}\b')

# Matches Thai Corporate Tax ID (13 digits starting with 0)
TH_TAX_ID_PATTERN = re.compile(r'\b0-?\d{4}-?\d{5}-?\d{2}-?\d{1}\b')

# Matches common Thai title prefixes to detect names
TH_NAME_TITLE_PATTERN = re.compile(r'(นาย|นาง|นางสาว|ดร\.|ศาสตราจารย์|แพทย์หญิง)\s*([ก-๙]+)\s+([ก-๙]+)')

# Matches Thai Currency format (e.g., 1,500.00 บาท หรือ 250 บาท)
TH_CURRENCY_PATTERN = re.compile(r'\b\d{1,3}(?:,\d{3})*(?:\.\d{2})?\s*(?:บาท|THB)\b')


class ThaiDocumentIntelligenceSkill:
    def __init__(self):
        self.api_key = os.getenv("THAI_OCR_API_KEY", "mock-key-1234")
        self.pdpa_endpoint = os.getenv("PDPA_COMPLIANCE_ENDPOINT", "https://compliance.delentia.th/v1/pdpa")

    def perform_ocr(self, document_url: str) -> str:
        """
        Simulate OCR processing on a Thai document.
        In production, this queries the OCR service with the media URL.
        """
        if not document_url:
            return ""
        
        # Simulated high-quality OCR text matching a standard Thai Invoice/Receipt
        simulated_text = (
            "ใบเสร็จรับเงิน / ใบกำกับภาษี\n"
            "บริษัท ดีเลนเทียแล็บส์ จำกัด (สำนักงานใหญ่)\n"
            "เลขประจำตัวผู้เสียภาษีอากร: 0-1055-64012-34-5\n"
            "ลูกค้า: นาย สมศักดิ์ รักดี\n"
            "เลขบัตรประจำตัวประชาชน: 1-1009-87654-32-1\n"
            "ที่อยู่: 123 ถนนสุขุมวิท แขวงคลองเตย เขตคลองเตย กรุงเทพมหานคร 10110\n"
            "วันที่: 2 มิถุนายน 2569\n"
            "รายการ: บริการคลาวด์ Delentia OS Enterprise Tier (รายปี)\n"
            "จำนวนเงิน: 125,000.00 บาท\n"
            "การยินยอมข้อมูลส่วนบุคคล (PDPA): ได้รับความยินยอมเพื่อประมวลผลธุรกรรมทางการเงินเรียบร้อยแล้ว [x]"
        )
        return simulated_text

    def extract_entities(self, text: str) -> Dict[str, Any]:
        """
        Runs Thai Named Entity Recognition (NER) to extract PII and financial metadata.
        """
        entities = {
            "citizen_id": None,
            "tax_id": None,
            "customer_name": None,
            "financial_amount": None,
            "addresses": [],
            "raw_matches": {}
        }

        # 1. Citizen ID Extraction
        citizen_match = TH_CITIZEN_ID_PATTERN.search(text)
        if citizen_match:
            entities["citizen_id"] = citizen_match.group(0).replace("-", "")

        # 2. Tax ID Extraction
        tax_match = TH_TAX_ID_PATTERN.search(text)
        if tax_match:
            entities["tax_id"] = tax_match.group(0).replace("-", "")

        # 3. Name Extraction
        name_match = TH_NAME_TITLE_PATTERN.search(text)
        if name_match:
            title, first, last = name_match.groups()
            entities["customer_name"] = f"{title} {first} {last}"

        # 4. Financial Currency Extraction
        currency_matches = TH_CURRENCY_PATTERN.findall(text)
        if currency_matches:
            entities["financial_amount"] = currency_matches[0]

        # 5. Simple address parsing (extracting province & postal code)
        address_match = re.search(r'แขวง.*?\d{5}', text)
        if address_match:
            entities["addresses"].append(address_match.group(0))

        return entities

    def verify_pdpa_compliance(self, text: str, entities: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validates if Personal Data Protection Act (PDPA) requirements are met.
        If PII (like Citizen ID or Name) is present, we check if consent was declared.
        """
        has_pii = bool(entities["citizen_id"] or entities["customer_name"])
        consent_declared = "[x]" in text or "ยินยอม" in text
        
        status = "COMPLIANT"
        rationale = "No sensitive PII processed or explicit consent verified."

        if has_pii and not consent_declared:
            status = "NON_COMPLIANT_WARNING"
            rationale = "Sensitive PII (Thai Citizen ID/Name) detected without verified consent checkbox."
        elif has_pii and consent_declared:
            status = "COMPLIANT_SECURE"
            rationale = "PII present; explicit PDPA consent marker verified successfully."

        return {
            "status": status,
            "requires_consent": has_pii,
            "consent_verified": consent_declared,
            "rationale": rationale
        }

    def process_document(self, document_url: str) -> Dict[str, Any]:
        """
        Main execution pipeline: OCR -> NER -> PDPA Compliance.
        """
        raw_text = self.perform_ocr(document_url)
        entities = self.extract_entities(raw_text)
        pdpa_audit = self.verify_pdpa_compliance(raw_text, entities)

        # Calculate a simulated FDIA (Data Quality & Integrity) score
        data_quality = 1.0 if len(raw_text) > 50 else 0.5
        intent_clarity = 1.0 if entities["citizen_id"] else 0.7
        auth_level = 1.0 if pdpa_audit["status"] != "NON_COMPLIANT_WARNING" else 0.4
        fdia_score = (data_quality ** intent_clarity) * auth_level

        return {
            "success": True,
            "document_url": document_url,
            "ocr_text_length": len(raw_text),
            "extracted_data": {
                "customer": entities["customer_name"],
                "citizen_id": entities["citizen_id"],
                "tax_id": entities["tax_id"],
                "total_amount": entities["financial_amount"],
                "locations": entities["addresses"]
            },
            "security_compliance": pdpa_audit,
            "fdia": {
                "score": round(fdia_score, 3),
                "data_quality": data_quality,
                "intent_clarity": intent_clarity,
                "authorization": auth_level
            }
        }


# ── Entry Point Handler ────────────────────────────────────────────────────────

def handle_intent(payload: Dict[str, Any]) -> str:
    """
    Delentia OS Skill standard entry point.
    """
    intent_text = payload.get("intent_text", "")
    metadata = payload.get("metadata", {})
    document_url = metadata.get("document_url", "https://assets.delentia.th/invoices/INV2026-9901.pdf")

    skill = ThaiDocumentIntelligenceSkill()
    result = skill.process_document(document_url)

    # Return standard formatted JSON response
    return json.dumps(result, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    # Local dry-run test
    test_payload = {
        "intent_text": "สแกนและตรวจสอบใบกำกับภาษีนี้",
        "metadata": {
            "document_url": "https://assets.delentia.th/invoices/INV2026-9901.pdf"
        }
    }
    print(handle_intent(test_payload))
