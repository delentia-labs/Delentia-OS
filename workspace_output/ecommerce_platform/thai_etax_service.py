# Subservice 3: Thai e-Tax Invoice & VAT 7% Generator
def generate_thai_tax_invoice(merchant_tax_id: str, customer_name: str, subtotal: float) -> dict:
    vat_rate = 0.07
    vat_amount = round(subtotal * vat_rate, 2)
    grand_total = round(subtotal + vat_amount, 2)
    return {
        'document_type': 'ใบกำกับภาษีเต็มรูป (e-Tax Invoice)',
        'merchant_tax_id': merchant_tax_id,
        'customer_name': customer_name,
        'subtotal_thb': subtotal,
        'vat_7_percent_thb': vat_amount,
        'grand_total_thb': grand_total,
        'status': 'AUTHORIZED_BY_DELENTIA_OS'
    }
