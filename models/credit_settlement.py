from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional


@dataclass
class CreditSettlement:
    """The bank charged the card debt of `account_id` for `mes_cargo` (one per account/month)."""
    account_id: str
    mes_cargo: str          # "YYYY-MM": groups the purchases being paid
    fecha: date             # when it was actually charged -> month that hits Real
    monto: float
    id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "account_id": self.account_id,
            "mes_cargo": self.mes_cargo,
            "fecha": datetime.combine(self.fecha, datetime.min.time()),
            "monto": self.monto,
            "created_at": self.created_at,
        }
