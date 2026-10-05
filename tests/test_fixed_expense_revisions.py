"""A fixed expense that changes amount keeps its history: past months are untouched."""
from services.finance_core import FinanceCore, fixed_amount_for_month
from tests.fixtures import empty_data, d

MAIN = "main"


def data_with_rent(revisiones=None, paid=()):
    data = empty_data()
    data["accounts"] = [{"id": MAIN, "nombre": "Main", "is_main": True, "saldo_inicial": 0.0}]
    data["fixed_expenses"] = [{"id": "rent", "account_id": MAIN, "monto": 700.0,
                               "fecha_inicio": d(2026, 1, 1), "fecha_fin": None,
                               "revisiones": revisiones or []}]
    data["fixed_expense_instances"] = [{"fixed_expense_id": "rent", "mes": m, "estado": "pagado", "monto": None}
                                       for m in paid]
    return data


def test_amount_follows_revisions_in_order():
    fe = {"monto": 700.0, "revisiones": [{"desde": "2026-09", "monto": 760.0},
                                         {"desde": "2026-04", "monto": 730.0}]}
    assert [fixed_amount_for_month(fe, m) for m in ("2026-03", "2026-04", "2026-08", "2026-09", "2027-01")] \
        == [700, 730, 730, 760, 760]


def test_revision_changes_future_projection_but_not_the_past():
    data = data_with_rent([{"desde": "2026-05", "monto": 750.0}])
    core = FinanceCore(data, "2026-04")
    by_month = {m: core.fixed_expenses_for_month(m)[0]["monto"] for m in ("2026-04", "2026-05")}
    assert by_month == {"2026-04": 700.0, "2026-05": 750.0}
    assert core.month_projected_result(MAIN, "2026-05")["resultado"] == -750


def test_paid_months_without_explicit_amount_use_the_amount_of_that_month():
    data = data_with_rent([{"desde": "2026-03", "monto": 750.0}], paid=("2026-01", "2026-02", "2026-03"))
    core = FinanceCore(data, "2026-03")
    assert core.real_balance(MAIN, "2026-03") == -(700 + 700 + 750)


def test_no_revisions_behaves_exactly_as_before():
    core = FinanceCore(data_with_rent(), "2026-03")
    assert core.fixed_expenses_for_month("2026-03")[0]["monto"] == 700.0


# ------------------------------------------------------- debit account changes

def data_two_accounts(revisiones, paid=()):
    data = data_with_rent(revisiones, paid)
    data["accounts"].append({"id": "sec", "nombre": "Sec", "is_main": False, "saldo_inicial": 0.0})
    return data


def test_account_change_moves_the_expense_from_that_month_only():
    revs = [{"desde": "2026-05", "account_id": "sec", "bank_id": "b2"}]
    core = FinanceCore(data_two_accounts(revs), "2026-04")
    apr, may = core.fixed_expenses_for_month("2026-04")[0], core.fixed_expenses_for_month("2026-05")[0]
    assert (apr["account_id"], may["account_id"], may["bank_id"]) == (MAIN, "sec", "b2")
    assert may["monto"] == 700.0                                   # amount untouched
    assert core.month_projected_result(MAIN, "2026-05")["resultado"] == 0
    assert core.month_projected_result("sec", "2026-05")["resultado"] == -700


def test_paid_history_stays_on_the_account_it_was_debited_from():
    revs = [{"desde": "2026-03", "account_id": "sec"}]
    core = FinanceCore(data_two_accounts(revs, paid=("2026-01", "2026-02", "2026-03", "2026-04")), "2026-04")
    assert core.real_balance(MAIN, "2026-04") == -1400
    assert core.real_balance("sec", "2026-04") == -1400


def test_amount_and_account_revisions_combine_independently():
    revs = [{"desde": "2026-03", "monto": 750.0}, {"desde": "2026-06", "account_id": "sec"}]
    core = FinanceCore(data_two_accounts(revs), "2026-01")
    jun = core.fixed_expenses_for_month("2026-06")[0]
    assert (jun["monto"], jun["account_id"]) == (750.0, "sec")


def test_moving_a_propio_expense_to_main_stops_the_reimbursement():
    data = data_two_accounts([{"desde": "2026-05", "account_id": MAIN}])
    data["fixed_expenses"][0].update({"account_id": "sec", "es_propio": True})
    core = FinanceCore(data, "2026-04")
    assert core.propio_expenses_by_account("2026-04", MAIN) == {"sec": 700.0}
    assert core.propio_expenses_by_account("2026-05", MAIN) == {}
