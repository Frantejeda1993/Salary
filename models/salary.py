from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional

# Legacy schema (before configurable deductions): one numeric field per
# deduction, stored as a percentage (15.0 == 15 %), plus an "_aplica_extras" flag.
LEGACY_DEDUCTION_FIELDS = [
    # (display name, value key, applies-to-extras key, default %)
    ("Cont. Común", "cont_comun", "cont_comun_aplica_extras", 15.0),
    ("MEI", "mei", "mei_aplica_extras", 0.1),
    ("Formación", "formacion", "formacion_aplica_extras", 0.1),
    ("Desempleo", "desempleo", "desempleo_aplica_extras", 0.1),
    ("IRPF", "irpf", "irpf_aplica_extras", 0.0),
]


def normalize_deductions(data: dict) -> list[dict]:
    """
    Single source of truth for a salary's deductions.

    New schema: data["deductions"] = [{"name", "percentage" (0-1), "applies_to_extras"}].
    Legacy schema (no "deductions" key at all): built from the old per-field values.
    An explicit empty list means "no deductions" and is respected, even if old
    legacy fields are still present in the document (Firestore update() is partial).
    Used by the model, the finance engine and the Salaries page, so what is shown
    is exactly what is calculated.
    """
    deductions = data.get("deductions")
    if deductions is not None:
        return list(deductions)
    if not any(key in data for _, key, _, _ in LEGACY_DEDUCTION_FIELDS):
        # Neither schema present: genuinely no deductions configured.
        return []
    return [
        {
            "name": name,
            "percentage": float(data.get(val_key, default_val)) / 100.0,
            "applies_to_extras": bool(data.get(extra_key, True)),
        }
        for name, val_key, extra_key, default_val in LEGACY_DEDUCTION_FIELDS
    ]


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

        deductions = normalize_deductions(data)

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
