# Subservice 1: Inventory & Stock Management
class InventoryManager:
    def __init__(self):
        self.stock = {'PROD-001': 50, 'PROD-002': 100, 'PROD-003': 10}
    def check_stock(self, sku: str, qty: int) -> bool:
        return self.stock.get(sku, 0) >= qty
    def deduct_stock(self, sku: str, qty: int) -> bool:
        if not self.check_stock(sku, qty):
            raise ValueError(f'Insufficient stock for SKU {sku}')
        self.stock[sku] -= qty
        return True
