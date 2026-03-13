from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional


def _normalize_percentage_to_0_100(value: float) -> float:
    """Normalizes percentage values to 0-100 scale.

    Defensive migration: legacy values (0-1) are treated as fractions.
    """
    pct = float(value)
    if 0.0 <= pct <= 1.0:
        return pct * 100.0
    return pct

@dataclass
class Salary:
    nombre: str
    salario_bruto: float
    fecha_inicio: date
    bank_id: str
    account_id: str
    fecha_fin: Optional[date] = None
    deductions: list[dict] = field(default_factory=list)
    id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "nombre": self.nombre,
            "salario_bruto": self.salario_bruto,
            "deductions": self.deductions,
            "fecha_inicio": datetime.combine(self.fecha_inicio, datetime.min.time()) if self.fecha_inicio else None,
            "fecha_fin": datetime.combine(self.fecha_fin, datetime.min.time()) if self.fecha_fin else None,
            "bank_id": self.bank_id,
            "account_id": self.account_id,
            "created_at": self.created_at
        }

    @classmethod
    def from_dict(cls, doc_id: str, data: dict) -> 'Salary':
        f_inicio = data.get('fecha_inicio')
        if f_inicio and isinstance(f_inicio, datetime):
            f_inicio = f_inicio.date()
            
        f_fin = data.get('fecha_fin')
        if f_fin and isinstance(f_fin, datetime):
            f_fin = f_fin.date()

        deductions = data.get('deductions')
        if deductions is None:
            deductions = []
            old_mapping = [
                ("Cont. Común", "cont_comun", "cont_comun_aplica_extras", 15.0),
                ("MEI", "mei", "mei_aplica_extras", 0.1),
                ("Formación", "formacion", "formacion_aplica_extras", 0.1),
                ("Desempleo", "desempleo", "desempleo_aplica_extras", 0.1),
                ("IRPF", "irpf", "irpf_aplica_extras", 0.0),
            ]
            for name, val_key, extra_key, default_val in old_mapping:
                deductions.append({
                    "name": name,
                    "percentage": _normalize_percentage_to_0_100(float(data.get(val_key, default_val))),
                    "applies_to_extras": bool(data.get(extra_key, False))
                })
        else:
            deductions = [
                {
                    "name": d.get("name", ""),
                    "percentage": _normalize_percentage_to_0_100(d.get("percentage", 0.0)),
                    "applies_to_extras": bool(d.get("applies_to_extras", False))
                }
                for d in deductions
            ]

        return cls(
            id=doc_id,
            nombre=data.get('nombre', ''),
            salario_bruto=float(data.get('salario_bruto', 0.0)),
            deductions=deductions,
            fecha_inicio=f_inicio or date.today(),
            fecha_fin=f_fin,
            bank_id=data.get('bank_id', ''),
            account_id=data.get('account_id', ''),
            created_at=data.get('created_at', datetime.now())
        )
