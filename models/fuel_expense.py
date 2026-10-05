from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional
from models.expense import Expense

@dataclass
class FuelExpense(Expense):
    km_done: float = 0.0
    price_per_l: float = 0.0

    def to_dict(self) -> dict:
        base_dict = super().to_dict()
        base_dict.update({
            "km_done": self.km_done,
            "price_per_l": self.price_per_l,
            "fuel_expense": True
        })
        return base_dict

    @classmethod
    def from_dict(cls, doc_id: str, data: dict) -> 'FuelExpense':
        fecha = data.get('fecha')
        if fecha and isinstance(fecha, datetime):
            fecha = fecha.date()

        return cls(
            id=doc_id,
            nombre=data.get('nombre', ''),
            fecha=fecha or date.today(),
            monto=data.get('monto', 0.0),
            categoria_id=data.get('categoria_id', ''),
            bank_id=data.get('bank_id', ''),
            account_id=data.get('account_id', ''),
            created_at=data.get('created_at', datetime.now()),
            km_done=data.get('km_done', 0.0),
            price_per_l=data.get('price_per_l', 0.0)
        )
