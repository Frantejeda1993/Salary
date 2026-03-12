from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

@dataclass
class Overtime:
    salary_id: str
    monto_bruto: float
    mes_aplicacion: str  # Format YYYY-MM
    id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "salary_id": self.salary_id,
            "monto_bruto": self.monto_bruto,
            "mes_aplicacion": self.mes_aplicacion,
            "created_at": self.created_at
        }

    @classmethod
    def from_dict(cls, doc_id: str, data: dict) -> 'Overtime':
        return cls(
            id=doc_id,
            salary_id=data.get('salary_id', ''),
            monto_bruto=data.get('monto_bruto', 0.0),
            mes_aplicacion=data.get('mes_aplicacion', ''),
            created_at=data.get('created_at', datetime.now())
        )
