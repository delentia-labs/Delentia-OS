# Subservice 2: Order Checkout & Atomic Processing (Self-Healed)
# Enforced by: INVARIANT_ATOMIC_STOCK_DEDUCTION
class OrderProcessor:
    def __init__(self, inventory):
        self.inventory = inventory
        self.orders = []
    def process_order(self, order_id: str, sku: str, qty: int, unit_price: float):
        self.inventory.deduct_stock(sku, qty)  # Atomic deduction enforced!
        total = round(qty * unit_price, 2)
        self.orders.append({'order_id': order_id, 'sku': sku, 'qty': qty, 'total': total})
        return {'order_id': order_id, 'status': 'PAID_AND_DEDUCTED', 'total': total}
