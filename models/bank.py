from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

@dataclass
class Bank:
    nombre: str
    duenio: str
    id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "nombre": self.nombre,
            "duenio": self.duenio,
            "created_at": self.created_at
        }

    @classmethod
    def from_dict(cls, doc_id: str, data: dict) -> 'Bank':
        return cls(
            id=doc_id,
            nombre=data.get('nombre', ''),
            duenio=data.get('duenio', ''),
            created_at=data.get('created_at', datetime.now())
        )
