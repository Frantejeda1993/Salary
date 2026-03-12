from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional

@dataclass
class Budget:
    categoria_id: str
    monto: float
    fecha_inicio: date
    bank_id: str
    account_id: str
    fecha_fin: Optional[date] = None
    id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "categoria_id": self.categoria_id,
            "monto": self.monto,
            "fecha_inicio": datetime.combine(self.fecha_inicio, datetime.min.time()) if self.fecha_inicio else None,
            "fecha_fin": datetime.combine(self.fecha_fin, datetime.min.time()) if self.fecha_fin else None,
            "bank_id": self.bank_id,
            "account_id": self.account_id,
            "created_at": self.created_at
        }

    @classmethod
    def from_dict(cls, doc_id: str, data: dict) -> 'Budget':
        f_inicio = data.get('fecha_inicio')
        if f_inicio and isinstance(f_inicio, datetime):
            f_inicio = f_inicio.date()
            
        f_fin = data.get('fecha_fin')
        if f_fin and isinstance(f_fin, datetime):
            f_fin = f_fin.date()

        return cls(
            id=doc_id,
            categoria_id=data.get('categoria_id', ''),
            monto=data.get('monto', 0.0),
            fecha_inicio=f_inicio or date.today(),
            fecha_fin=f_fin,
            bank_id=data.get('bank_id', ''),
            account_id=data.get('account_id', ''),
            created_at=data.get('created_at', datetime.now())
        )
