"""
Business rules of the finance engine, as readable scenarios.
If a change breaks one of these, either the change is wrong or the rule
changed on purpose -- in that case update the test in the same commit.
"""
import pytest
from services.finance_core import FinanceCore
from tests.fixtures import empty_data, d

MAIN = "main"


def base(salary=2000.0, deductions=None, start=(2026, 1)):
    data = empty_data()
    data["accounts"] = [
        {"id": MAIN, "nombre": "Main", "is_main": True, "saldo_inicial": 1000.0},
        {"id": "sec", "nombre": "Sec", "is_main": False, "saldo_inicial": 0.0},
    ]
    data["categories"] = [
        {"id": "food", "nombre": "Food", "tipo": "normal"},
        {"id": "fun", "nombre": "Fun", "tipo": "normal"},
        {"id": "gift", "nombre": "Gift", "tipo": "extra"},
    ]
    data["salaries"] = [{
        "id": "s1", "account_id": MAIN, "salario_bruto": salary,
        "fecha_inicio": d(*start, 1), "fecha_fin": None,
        "deductions": deductions if deductions is not None else [],
    }]
    return data


def expense(data, cat, amount, month, account=MAIN, day=10):
    data["expenses"].append({"id": f"e{len(data['expenses'])}", "account_id": account,
                             "categoria_id": cat, "monto": amount, "fecha": d(2026, month, day)})


def budget(data, cat, amount, account=MAIN):
    data["budgets"].append({"id": f"b{cat}", "categoria_id": cat, "account_id": account,
                            "monto": amount, "fecha_inicio": d(2026, 1, 1), "fecha_fin": None})


# --------------------------------------------------------------------- salary

def test_salary_net_applies_deductions_and_overtime_flag():
    data = base(2000.0, deductions=[
        {"name": "SS", "percentage": 0.05, "applies_to_extras": True},
        {"name": "IRPF", "percentage": 0.10, "applies_to_extras": False},
    ])
    data["overtimes"] = [{"salary_id": "s1", "mes_aplicacion": "2026-03", "monto_bruto": 200.0}]
    core = FinanceCore(data, "2026-03")
    # 2000 + 200 - (2200*0.05) - (2000*0.10)
    assert core.salary_net("s1", "2026-03") == pytest.approx(1890.0)
    assert core.salary_net("s1", "2026-04") == pytest.approx(2000 - 100 - 200)


def test_legacy_salary_without_deductions_key_is_migrated():
    data = base(2000.0)
    del data["salaries"][0]["deductions"]
    data["salaries"][0].update({"cont_comun": 4.7, "irpf": 10.0})
    core = FinanceCore(data, "2026-03")
    # Before the fix this returned 2000 (no deductions at all).
    # Unspecified legacy fields take their historical defaults (MEI/Formación/Desempleo 0.1 %).
    expected = 2000 * (1 - 0.047 - 0.001 - 0.001 - 0.001 - 0.10)
    assert core.salary_net("s1", "2026-03") == pytest.approx(expected)


def test_explicit_empty_deductions_are_respected_even_with_leftover_legacy_fields():
    data = base(2000.0, deductions=[])
    data["salaries"][0]["irpf"] = 15.0  # stale field left by a partial update()
    assert FinanceCore(data, "2026-03").salary_net("s1", "2026-03") == 2000.0


# ---------------------------------------------------------------- real result

def test_real_result_is_cash_basis():
    data = base(2000.0)
    expense(data, "food", 150.0, 3)
    data["fixed_expenses"] = [{"id": "rent", "account_id": MAIN, "monto": 700.0,
                               "fecha_inicio": d(2026, 1, 1), "fecha_fin": None}]
    core = FinanceCore(data, "2026-03")
    assert core.month_real_result(MAIN, "2026-03") == 2000 - 150  # rent not paid yet
    data["fixed_expense_instances"] = [{"fixed_expense_id": "rent", "mes": "2026-03",
                                        "estado": "pagado", "monto": 690.0}]
    core = FinanceCore(data, "2026-03")
    assert core.month_real_result(MAIN, "2026-03") == 2000 - 150 - 690  # paid amount wins


# ----------------------------------------------------------- projected result

def test_budget_charges_at_least_its_amount_and_overrun_when_exceeded():
    data = base(2000.0)
    budget(data, "food", 300.0)
    expense(data, "food", 120.0, 3)
    core = FinanceCore(data, "2026-03")
    assert core.month_projected_result(MAIN, "2026-03")["resultado"] == 2000 - 300
    expense(data, "food", 250.0, 3)  # total 370 > 300
    core = FinanceCore(data, "2026-03")
    assert core.month_projected_result(MAIN, "2026-03")["resultado"] == 2000 - 370


def test_non_budgeted_expenses_are_charged_in_full():
    data = base(2000.0)
    expense(data, "fun", 80.0, 3)
    assert FinanceCore(data, "2026-03").month_projected_result(MAIN, "2026-03")["resultado"] == 1920


def test_categorised_income_is_not_double_counted_in_projection():
    data = base(2000.0)
    budget(data, "food", 300.0)
    expense(data, "food", 100.0, 3)
    data["incomes"] = [{"id": "i1", "account_id": MAIN, "categoria_id": "food",
                        "monto": 40.0, "fecha": d(2026, 3, 12)}]
    core = FinanceCore(data, "2026-03")
    assert core.category_spending("2026-03", MAIN)["food"] == 60.0       # netted view
    assert core.month_projected_result(MAIN, "2026-03")["resultado"] == 2000 + 40 - 300


def test_deficit_is_absorbed_by_unspent_budgets_and_pre_value_is_kept():
    data = base(500.0)
    budget(data, "food", 300.0)
    budget(data, "fun", 100.0)
    expense(data, "food", 100.0, 3)       # food has 200 left, fun 100 left
    expense(data, "gift", 350.0, 3)       # non-budgeted
    proj = FinanceCore(data, "2026-03").month_projected_result(MAIN, "2026-03")
    # 500 - 300 - 100 - 350 = -250 ; available 300 -> fully absorbed
    assert proj["resultado_pre_absorcion"] == pytest.approx(-250)
    assert proj["resultado"] == pytest.approx(0)
    for bd in proj["budget_details"]:
        used = max(bd["real_spent"], 0.0)
        assert bd["presupuesto"] - used - bd["absorbed"] - bd["available"] == pytest.approx(0)
    shares = {bd["categoria_id"]: bd["absorbed"] for bd in proj["budget_details"]}
    assert shares["food"] == pytest.approx(250 * 200 / 300)   # proportional to room left


def test_absorption_is_capped_by_available_room():
    data = base(100.0)
    budget(data, "food", 50.0)
    expense(data, "gift", 300.0, 3)
    proj = FinanceCore(data, "2026-03").month_projected_result(MAIN, "2026-03")
    assert proj["resultado_pre_absorcion"] == pytest.approx(100 - 50 - 300)
    assert proj["resultado"] == pytest.approx(-200)


# ------------------------------------------------------------------ carry-over

def test_no_carry_at_or_before_min_managed_month():
    core = FinanceCore(base(), "2026-05", min_managed_month="2026-02")
    assert core.remaining_from_previous_month("2026-02", MAIN) == 0.0


def test_closed_months_carry_real_results_cumulatively():
    data = base(2000.0, start=(2026, 2))
    expense(data, "fun", 500.0, 2)
    expense(data, "fun", 300.0, 3)
    core = FinanceCore(data, "2026-04", min_managed_month="2026-02")
    assert core.remaining_from_previous_month("2026-03", MAIN) == 1500
    assert core.remaining_from_previous_month("2026-04", MAIN) == 1500 + 1700


def test_future_months_chain_projected_results():
    data = base(2000.0, start=(2026, 2))
    budget(data, "food", 400.0)
    core = FinanceCore(data, "2026-04", min_managed_month="2026-02")
    carry_april = core.remaining_from_previous_month("2026-04", MAIN)   # real, closed months
    assert core.remaining_from_previous_month("2026-05", MAIN) == pytest.approx(carry_april + 1600)
    assert core.remaining_from_previous_month("2026-07", MAIN) == pytest.approx(carry_april + 3 * 1600)


def test_future_chain_subtracts_pending_propio_fixed_expenses():
    data = base(2000.0, start=(2026, 2))
    data["fixed_expenses"] = [{"id": "gym", "account_id": "sec", "monto": 50.0, "es_propio": True,
                               "fecha_inicio": d(2026, 1, 1), "fecha_fin": None}]
    core = FinanceCore(data, "2026-04", min_managed_month="2026-02")
    carry_april = core.remaining_from_previous_month("2026-04", MAIN)
    assert core.remaining_from_previous_month("2026-05", MAIN) == pytest.approx(carry_april + 2000 - 50)


def test_auto_reimbursement_transfer_clears_propio():
    data = base(2000.0)
    data["fixed_expenses"] = [{"id": "gym", "account_id": "sec", "monto": 50.0, "es_propio": True,
                               "fecha_inicio": d(2026, 1, 1), "fecha_fin": None}]
    data["transfers"] = [{"id": "t1", "cuenta_origen": MAIN, "cuenta_destino": "sec", "monto": 50.0,
                          "fecha": d(2026, 4, 2), "descripcion": "Transferencia automatica gastos"}]
    core = FinanceCore(data, "2026-04")
    assert core.propio_expenses_by_account("2026-04", MAIN) == {}
    assert core.propio_expenses_by_account("2026-05", MAIN) == {"sec": 50.0}


# -------------------------------------------------------------------- balances

def test_real_balance_accumulates_from_initial_balance():
    data = base(2000.0)
    expense(data, "fun", 100.0, 1)
    expense(data, "fun", 100.0, 2)
    core = FinanceCore(data, "2026-02")
    assert core.real_balance(MAIN, "2026-01") == 1000 + 2000 - 100
    assert core.real_balance(MAIN, "2026-02") == 1000 + 4000 - 200


def test_projected_balance_identity_without_absorption():
    """projected_balance(m) == month_projected_result(m, carry=0) + real_balance(m-1)."""
    data = base(2000.0)
    budget(data, "food", 300.0)
    expense(data, "food", 120.0, 3)
    expense(data, "fun", 60.0, 3)
    data["fixed_expenses"] = [{"id": "rent", "account_id": MAIN, "monto": 700.0,
                               "fecha_inicio": d(2026, 1, 1), "fecha_fin": None}]
    data["fixed_expense_instances"] = [{"fixed_expense_id": "rent", "mes": m, "estado": "pagado", "monto": None}
                                       for m in ("2026-01", "2026-02")]
    core = FinanceCore(data, "2026-03")
    lhs = core.projected_balance(MAIN, "2026-03")["resultado"]
    rhs = core.month_projected_result(MAIN, "2026-03")["resultado"] + core.real_balance(MAIN, "2026-02")
    assert lhs == pytest.approx(rhs)
