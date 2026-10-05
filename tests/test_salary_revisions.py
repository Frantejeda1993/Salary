"""Salary raises, including retroactive ones paid later with arrears."""
import pytest
from services.finance_core import FinanceCore
from tests.fixtures import empty_data, d

MAIN = "main"


def data(revisiones=(), deductions=()):
    data = empty_data()
    data["accounts"] = [{"id": MAIN, "nombre": "Main", "is_main": True, "saldo_inicial": 0.0}]
    data["salaries"] = [{"id": "s1", "account_id": MAIN, "salario_bruto": 2000.0,
                         "fecha_inicio": d(2026, 1, 1), "fecha_fin": None,
                         "deductions": list(deductions), "revisiones": list(revisiones)}]
    return data


def gross_series(core, months):
    return [core.salary_breakdown("s1", m)["base"] + core.salary_breakdown("s1", m)["atrasos"] for m in months]


def test_plain_raise_from_a_month():
    core = FinanceCore(data([{"desde": "2026-06", "salario_bruto": 2200.0}]), "2026-03")
    assert gross_series(core, ["2026-05", "2026-06", "2026-07"]) == [2000, 2200, 2200]


def test_retroactive_raise_pays_arrears_in_the_payment_month():
    revs = [{"desde": "2026-04", "salario_bruto": 2200.0, "cobro_desde": "2026-06"}]
    core = FinanceCore(data(revs), "2026-03")
    assert gross_series(core, ["2026-03", "2026-04", "2026-05", "2026-06", "2026-07"]) \
        == [2000, 2000, 2000, 2600, 2200]           # June: 2200 + 2 months x 200 arrears
    june = core.salary_breakdown("s1", "2026-06")
    assert (june["base"], june["atrasos"]) == (2200, 400)


def test_total_paid_equals_total_owed_once_known():
    revs = [{"desde": "2026-04", "salario_bruto": 2200.0, "cobro_desde": "2026-06"}]
    core = FinanceCore(data(revs), "2026-08")
    assert sum(gross_series(core, [f"2026-{m:02d}" for m in range(1, 9)])) == 3 * 2000 + 5 * 2200


def test_two_raises_one_retroactive_overlapping():
    revs = [{"desde": "2026-03", "salario_bruto": 2100.0, "cobro_desde": "2026-05"},
            {"desde": "2026-05", "salario_bruto": 2300.0}]
    core = FinanceCore(data(revs), "2026-01")
    # Mar-Apr owed 2100 but paid 2000; May: 2300 + 2x100 arrears
    assert gross_series(core, ["2026-03", "2026-04", "2026-05", "2026-06"]) == [2000, 2000, 2500, 2300]


def test_deductions_apply_to_arrears():
    revs = [{"desde": "2026-04", "salario_bruto": 2200.0, "cobro_desde": "2026-06"}]
    core = FinanceCore(data(revs, [{"name": "IRPF", "percentage": 0.10, "applies_to_extras": False}]), "2026-03")
    assert core.salary_net("s1", "2026-06") == pytest.approx(2600 * 0.9)


def test_raise_flows_into_real_balance_and_projection():
    revs = [{"desde": "2026-04", "salario_bruto": 2200.0, "cobro_desde": "2026-06"}]
    core = FinanceCore(data(revs), "2026-06")
    assert core.real_balance(MAIN, "2026-06") == 5 * 2000 + 2600
    assert core.month_projected_result(MAIN, "2026-06")["resultado"] == 2600


def test_without_revisions_net_is_unchanged():
    core = FinanceCore(data(), "2026-03")
    assert core.salary_net("s1", "2026-03") == 2000
