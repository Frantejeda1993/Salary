"""
Credit card purchases.

Key property: the projection of a month must NOT depend on which month is
"current". While the purchase month is open, the carry-over comes from its
projection (which reserved the purchase); once it closes, the carry-over is
cash (which didn't). The engine must charge the debt exactly once either way.
"""
import pytest
from services.finance_core import FinanceCore
from tests.fixtures import empty_data, d

MAIN = "main"
MIN = "2026-02"


def scenario(reservar_en="compra", settled_on=None, amount=300.0, budget=None, mes_cargo="2026-04"):
    data = empty_data()
    data["accounts"] = [{"id": MAIN, "nombre": "Main", "is_main": True, "saldo_inicial": 0.0}]
    data["categories"] = [{"id": "food", "nombre": "Food", "tipo": "normal"}]
    data["salaries"] = [{"id": "s1", "account_id": MAIN, "salario_bruto": 2000.0,
                         "fecha_inicio": d(2026, 3, 1), "fecha_fin": None, "deductions": []}]
    data["expenses"] = [{"id": "cc1", "account_id": MAIN, "categoria_id": "food", "monto": amount,
                         "fecha": d(2026, 3, 20), "metodo_pago": "credito",
                         "mes_cargo": mes_cargo, "reservar_en": reservar_en}]
    if budget:
        data["budgets"] = [{"id": "b", "categoria_id": "food", "account_id": MAIN, "monto": budget,
                            "fecha_inicio": d(2026, 3, 1), "fecha_fin": None}]
    if settled_on:
        data["credit_settlements"] = [{"id": "s", "account_id": MAIN, "mes_cargo": mes_cargo,
                                       "fecha": d(*settled_on), "monto": amount}]
    return data


def projected(data, current, month):
    core = FinanceCore(data, current, min_managed_month=MIN)
    carry = core.remaining_from_previous_month(month, MAIN)
    return core.month_projected_result(MAIN, month, carry)["resultado"]


def real_shown(data, current, month):
    core = FinanceCore(data, current, min_managed_month=MIN)
    return core.month_real_result(MAIN, month) + core.remaining_from_previous_month(month, MAIN)


# ------------------------------------------------------- reserved in purchase month

def test_purchase_hits_projected_not_real_in_purchase_month():
    data = scenario()
    assert projected(data, "2026-03", "2026-03") == 1700
    assert real_shown(data, "2026-03", "2026-03") == 2000


@pytest.mark.parametrize("settled_on", [None, (2026, 4, 5), (2026, 5, 3)])
@pytest.mark.parametrize("month", ["2026-04", "2026-05", "2026-06"])
def test_projection_is_identical_whatever_the_current_month(settled_on, month):
    """No double count, no lost debt, no matter when the month closes or when it's settled."""
    data = scenario(settled_on=settled_on)
    expected = 1700 + 2000 * (int(month[-2:]) - 3)
    for current in ["2026-03", "2026-04", "2026-05", "2026-06"]:
        if current > month:
            continue
        assert projected(data, current, month) == pytest.approx(expected), current


def test_real_only_moves_when_settled():
    pending = scenario()
    assert real_shown(pending, "2026-04", "2026-04") == 4000
    settled = scenario(settled_on=(2026, 4, 5))
    assert real_shown(settled, "2026-04", "2026-04") == 3700
    # Once settled, real and projected agree again
    assert projected(settled, "2026-04", "2026-04") == 3700


# --------------------------------------------- paid with next month's salary

def test_reserved_in_charge_month_leaves_purchase_month_untouched():
    data = scenario(reservar_en="cargo")
    assert projected(data, "2026-03", "2026-03") == 2000
    assert projected(data, "2026-03", "2026-04") == 3700
    assert projected(data, "2026-04", "2026-04") == 3700


def test_reserved_in_charge_month_counts_in_that_months_budget():
    data = scenario(reservar_en="cargo", amount=100.0, budget=250.0)
    core = FinanceCore(data, "2026-03", min_managed_month=MIN)
    assert core.raw_category_expenses("2026-03", MAIN).get("food", 0.0) == 0.0
    assert core.raw_category_expenses("2026-04", MAIN)["food"] == 100.0


def test_purchase_reserved_in_purchase_month_consumes_that_budget():
    data = scenario(amount=100.0, budget=250.0)
    core = FinanceCore(data, "2026-03", min_managed_month=MIN)
    assert core.raw_category_expenses("2026-03", MAIN)["food"] == 100.0
    # inside the budget -> projected only charges the budget
    assert core.month_projected_result(MAIN, "2026-03")["resultado"] == 2000 - 250


# ----------------------------------------------------------- balances & card

def test_balances_and_card_balance():
    data = scenario()
    core = FinanceCore(data, "2026-04", min_managed_month=MIN)
    assert core.real_balance(MAIN, "2026-03") == 2000                      # cash untouched
    assert core.projected_balance(MAIN, "2026-03")["resultado"] == 1700   # debt reserved
    assert core.credit_outstanding(MAIN, "2026-04", False) == 300          # card in negative
    settled = FinanceCore(scenario(settled_on=(2026, 4, 5)), "2026-04", min_managed_month=MIN)
    assert settled.real_balance(MAIN, "2026-04") == 3700
    assert settled.credit_outstanding(MAIN, "2026-04", False) == 0
    assert settled.projected_balance(MAIN, "2026-04")["resultado"] == 3700


def test_charge_month_defaults_to_next_month_and_groups_by_account_and_month():
    data = scenario(mes_cargo=None)
    data["expenses"].append({"id": "cc2", "account_id": MAIN, "categoria_id": "food", "monto": 50.0,
                             "fecha": d(2026, 3, 25), "metodo_pago": "credito"})
    groups = FinanceCore(data, "2026-03").credit_groups()
    assert len(groups) == 1
    assert groups[0]["mes_cargo"] == "2026-04" and groups[0]["total"] == 350


def test_custom_charge_month_for_billing_cycles():
    """Bought after the card's cut-off date -> charged two months later."""
    data = scenario(mes_cargo="2026-05")
    assert projected(data, "2026-05", "2026-05") == pytest.approx(1700 + 4000)
    assert real_shown(data, "2026-04", "2026-04") == 4000  # nothing charged in April
