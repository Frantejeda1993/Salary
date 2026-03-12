from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

@dataclass
class Account:
    bank_id: str
    nombre: str
    saldo_inicial: float
    id: Optional[str] = None
    is_main: bool = False
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "bank_id": self.bank_id,
            "nombre": self.nombre,
            "saldo_inicial": self.saldo_inicial,
            "is_main": self.is_main,
            "created_at": self.created_at
        }

    @classmethod
    def from_dict(cls, doc_id: str, data: dict) -> 'Account':
        return cls(
            id=doc_id,
            bank_id=data.get('bank_id', ''),
            nombre=data.get('nombre', ''),
            saldo_inicial=data.get('saldo_inicial', 0.0),
            is_main=data.get('is_main', False),
            created_at=data.get('created_at', datetime.now())
        )
