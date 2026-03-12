from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional

@dataclass
class Income:
    nombre: str
    fecha: date
    monto: float
    categoria_id: str
    bank_id: str
    account_id: str
    id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "nombre": self.nombre,
            "fecha": datetime.combine(self.fecha, datetime.min.time()) if self.fecha else None,
            "monto": self.monto,
            "categoria_id": self.categoria_id,
            "bank_id": self.bank_id,
            "account_id": self.account_id,
            "created_at": self.created_at
        }

    @classmethod
    def from_dict(cls, doc_id: str, data: dict) -> 'Income':
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
            created_at=data.get('created_at', datetime.now())
        )
