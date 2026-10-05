"""Shared widgets for credit card purchases (used inside st.form, so no dynamic show/hide)."""
from datetime import date

import streamlit as st

from services.finance_core import add_months

CHARGE_OPTIONS = {1: "Mes siguiente a la compra", 2: "Dentro de 2 meses (compra tras el corte)"}
RESERVE_OPTIONS = {
    "compra": "Reservar en el mes de la compra",
    "cargo": "Pagar con el sueldo del mes de cargo",
}


def credit_inputs(key: str, existing: dict | None = None):
    """Renders the credit card inputs. Returns (is_credit, months_offset, reservar_en)."""
    existing = existing or {}
    is_credit_now = existing.get("metodo_pago") == "credito"
    offset_now = 1
    if is_credit_now and existing.get("mes_cargo") and existing.get("fecha"):
        purchase = str(existing["fecha"])[:7]
        offset_now = 2 if existing["mes_cargo"] >= add_months(purchase, 2) else 1

    is_credit = st.checkbox("💳 Pagado con tarjeta de crédito", value=is_credit_now, key=f"{key}_cc")
    c1, c2 = st.columns(2)
    offset = c1.selectbox(
        "Se cobra", list(CHARGE_OPTIONS), index=offset_now - 1,
        format_func=CHARGE_OPTIONS.get, key=f"{key}_cc_off",
        help="Si tu tarjeta liquida con fecha de corte, las compras posteriores al corte se cobran un mes más tarde.",
    )
    reserve_keys = list(RESERVE_OPTIONS)
    reservar_en = c2.radio(
        "Cómo se reserva", reserve_keys,
        index=reserve_keys.index(existing.get("reservar_en", "compra")) if is_credit_now else 0,
        format_func=RESERVE_OPTIONS.get, key=f"{key}_cc_res",
        help="Reservar en el mes de la compra: descuenta del Proyectado/Budget de este mes. "
             "Sueldo del mes de cargo: todo cuenta en el mes en que se cobra.",
    )
    st.caption("Las opciones de tarjeta solo se aplican si marcas la casilla.")
    return is_credit, offset, reservar_en


def credit_fields(fecha: date, is_credit: bool, offset: int, reservar_en: str) -> dict:
    """Firestore fields for an expense, clearing them when it is not a card purchase."""
    if not is_credit:
        return {"metodo_pago": "", "mes_cargo": None, "reservar_en": "compra"}
    return {
        "metodo_pago": "credito",
        "mes_cargo": add_months(fecha.strftime("%Y-%m"), offset),
        "reservar_en": reservar_en,
    }
