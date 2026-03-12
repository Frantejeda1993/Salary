from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional

@dataclass
class Transfer:
    fecha: date
    cuenta_origen: str
    cuenta_destino: str
    monto: float
    id: Optional[str] = None
    is_loan: bool = False
    status: str = 'pending' # 'pending' or 'paid'
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "fecha": datetime.combine(self.fecha, datetime.min.time()) if self.fecha else None,
            "cuenta_origen": self.cuenta_origen,
            "cuenta_destino": self.cuenta_destino,
            "monto": self.monto,
            "is_loan": self.is_loan,
            "status": self.status,
            "created_at": self.created_at
        }

    @classmethod
    def from_dict(cls, doc_id: str, data: dict) -> 'Transfer':
        fecha = data.get('fecha')
        if fecha and isinstance(fecha, datetime):
            fecha = fecha.date()

        return cls(
            id=doc_id,
            fecha=fecha or date.today(),
            cuenta_origen=data.get('cuenta_origen', ''),
            cuenta_destino=data.get('cuenta_destino', ''),
            monto=data.get('monto', 0.0),
            is_loan=data.get('is_loan', False),
            status=data.get('status', 'pending'),
            created_at=data.get('created_at', datetime.now())
        )
