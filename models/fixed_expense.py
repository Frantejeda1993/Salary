from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional

@dataclass
class FixedExpense:
    nombre: str
    monto: float
    fecha_inicio: date
    bank_id: str
    account_id: str
    fecha_fin: Optional[date] = None
    es_propio: bool = False
    id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "nombre": self.nombre,
            "monto": self.monto,
            "fecha_inicio": datetime.combine(self.fecha_inicio, datetime.min.time()) if self.fecha_inicio else None,
            "fecha_fin": datetime.combine(self.fecha_fin, datetime.min.time()) if self.fecha_fin else None,
            "bank_id": self.bank_id,
            "account_id": self.account_id,
            "es_propio": self.es_propio,
            "created_at": self.created_at
        }

    @classmethod
    def from_dict(cls, doc_id: str, data: dict) -> 'FixedExpense':
        f_inicio = data.get('fecha_inicio')
        if f_inicio and isinstance(f_inicio, datetime):
            f_inicio = f_inicio.date()
            
        f_fin = data.get('fecha_fin')
        if f_fin and isinstance(f_fin, datetime):
            f_fin = f_fin.date()

        return cls(
            id=doc_id,
            nombre=data.get('nombre', ''),
            monto=data.get('monto', 0.0),
            fecha_inicio=f_inicio or date.today(),
            fecha_fin=f_fin,
            bank_id=data.get('bank_id', ''),
            account_id=data.get('account_id', ''),
            es_propio=data.get('es_propio', False),
            created_at=data.get('created_at', datetime.now())
        )

@dataclass
class FixedExpenseInstance:
    fixed_expense_id: str
    mes: str  # Format YYYY-MM
    estado: str  # "pagado" / "impagado"
    monto: Optional[float] = None
    id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "fixed_expense_id": self.fixed_expense_id,
            "mes": self.mes,
            "estado": self.estado,
            "monto": self.monto
        }

    @classmethod
    def from_dict(cls, doc_id: str, data: dict) -> 'FixedExpenseInstance':
        return cls(
            id=doc_id,
            fixed_expense_id=data.get('fixed_expense_id', ''),
            mes=data.get('mes', ''),
            estado=data.get('estado', 'impagado'),
            monto=data.get('monto')
        )
