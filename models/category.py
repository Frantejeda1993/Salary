from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

@dataclass
class Category:
    nombre: str
    tipo: str  # "normal" or "extra"
    id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "nombre": self.nombre,
            "tipo": self.tipo,
            "created_at": self.created_at
        }

    @classmethod
    def from_dict(cls, doc_id: str, data: dict) -> 'Category':
        return cls(
            id=doc_id,
            nombre=data.get('nombre', ''),
            tipo=data.get('tipo', 'normal'),
            created_at=data.get('created_at', datetime.now())
        )
