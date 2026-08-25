"""
PromptPay Dynamic QR Billing & Intent Quota Generator (EMVCo Standard)
Delentia OS Cognitive Kernel (Unified v2.2.6)

Generates standardized EMVCo PromptPay Dynamic QR payloads with exact THB amounts,
CRC16 checksums, and cryptographic invoice tracking.
"""

from typing import Dict, Any


def calculate_crc16(payload: str) -> str:
    """Calculates CRC-CCITT (0xFFFF) checksum for EMVCo standard."""
    crc = 0xFFFF
    for char in payload:
        crc ^= ord(char) << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return f"{crc:04X}"


def generate_promptpay_qr_payload(phone_or_taxid: str, amount_thb: float, invoice_id: str) -> Dict[str, Any]:
    """
    Generates an official PromptPay EMVCo Payload for QR Code renderers.
    """
    clean_id = phone_or_taxid.replace("-", "").strip()
    if clean_id.startswith("0"):
        # Format mobile phone: 0066 + 9 digits
        target = f"0066{clean_id[1:]}"
    else:
        target = clean_id

    # 1. Payload Format Indicator
    tag_00 = "000201"
    # 2. Point of Initiation Method (12 = Dynamic QR)
    tag_01 = "010212"
    # 3. Merchant Account Information (PromptPay ID 29)
    sub_00 = "0016A000000677010111"
    sub_01 = f"01{len(target):02d}{target}"
    merchant_data = f"{sub_00}{sub_01}"
    tag_29 = f"29{len(merchant_data):02d}{merchant_data}"
    # 4. Currency: 764 (THB)
    tag_53 = "5303764"
    # 5. Amount
    amount_str = f"{amount_thb:.2f}"
    tag_54 = f"54{len(amount_str):02d}{amount_str}"
    # 6. Country Code: TH
    tag_58 = "5802TH"
    # 7. Additional Data (Invoice ID)
    inv_data = f"05{len(invoice_id):02d}{invoice_id}"
    tag_62 = f"62{len(inv_data):02d}{inv_data}"

    # Build preliminary payload
    raw_payload = f"{tag_00}{tag_01}{tag_29}{tag_53}{tag_54}{tag_58}{tag_62}6304"
    crc = calculate_crc16(raw_payload)
    final_payload = f"{raw_payload}{crc}"

    return {
        "invoice_id": invoice_id,
        "amount_thb": amount_thb,
        "promptpay_target": target,
        "emvco_payload": final_payload,
        "crc16": crc,
        "status": "AWAITING_PAYMENT"
    }
