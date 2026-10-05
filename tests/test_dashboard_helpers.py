from services.finance_core import FinanceCore
from tests.fixtures import empty_data, d


def test_budget_pace():
    assert FinanceCore.budget_pace(150, 300, 10, 30)["status"] == "por encima del ritmo"   # 450 forecast
    assert FinanceCore.budget_pace(90, 300, 10, 30)["status"] == "ok"
    assert FinanceCore.budget_pace(310, 300, 10, 30)["status"] == "excedido"
    assert FinanceCore.budget_pace(0, 300, 0, 30)["forecast"] == 0


def test_pending_obligations_collects_every_kind():
    data = empty_data()
    data["accounts"] = [{"id": "main", "is_main": True, "saldo_inicial": 0.0},
                        {"id": "sec", "is_main": False, "saldo_inicial": 0.0}]
    data["fixed_expenses"] = [
        {"id": "rent", "nombre": "Alquiler", "account_id": "main", "monto": 700.0,
         "fecha_inicio": d(2026, 1, 1), "fecha_fin": None},
        {"id": "gym", "nombre": "Gym", "account_id": "sec", "monto": 40.0, "es_propio": True,
         "fecha_inicio": d(2026, 1, 1), "fecha_fin": None},
    ]
    data["fixed_expense_instances"] = [{"fixed_expense_id": "gym", "mes": "2026-04", "estado": "pagado", "monto": None}]
    data["expenses"] = [{"id": "cc", "account_id": "main", "categoria_id": "x", "monto": 120.0,
                         "fecha": d(2026, 3, 9), "metodo_pago": "credito", "mes_cargo": "2026-04"}]
    data["transfers"] = [{"id": "l", "cuenta_origen": "sec", "cuenta_destino": "main", "monto": 200.0,
                          "fecha": d(2026, 2, 1), "is_loan": True, "status": "pending", "outstanding_amount": 150.0}]
    tipos = {(o["tipo"], o["monto"]) for o in FinanceCore(data, "2026-04").pending_obligations("2026-04")}
    assert tipos == {("Gasto fijo", 700.0), ("Tarjeta", 120.0), ("Préstamo", 150.0)}
    # gym is paid in April -> not pending, and its propio reimbursement only applies while unpaid


def test_pending_loans_impact_both_directions():
    data = empty_data()
    data["transfers"] = [
        {"id": "a", "cuenta_origen": "sec", "cuenta_destino": "main", "monto": 500.0, "fecha": d(2026, 2, 1),
         "is_loan": True, "status": "pending", "outstanding_amount": 300.0},
        {"id": "b", "cuenta_origen": "main", "cuenta_destino": "sec", "monto": 100.0, "fecha": d(2026, 3, 1),
         "is_loan": True, "status": "pending"},                                   # no outstanding -> full amount
        {"id": "c", "cuenta_origen": "sec", "cuenta_destino": "main", "monto": 900.0, "fecha": d(2026, 3, 1),
         "is_loan": True, "status": "paid", "outstanding_amount": 0.0},
        {"id": "d", "cuenta_origen": "sec", "cuenta_destino": "main", "monto": 50.0, "fecha": d(2026, 3, 1)},
    ]
    assert FinanceCore(data, "2026-04").pending_loans_impact("main") == {"debes": 300.0, "te_deben": 100.0, "neto": -200.0}
