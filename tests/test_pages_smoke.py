"""
Smoke test: every page renders against an in-memory fake Firestore, and the
credit card settle / undo flow works end to end. Catches UI breakage the
pure-engine tests can't see.
"""
import copy, os
import pytest
from datetime import datetime
from streamlit.testing.v1 import AppTest
import services.firestore_service as fs
from utils.date_utils import get_current_month
from services.finance_core import add_months

cur = get_current_month(); prev = add_months(cur, -1)
y, m = map(int, prev.split("-"))
SEED = {
 "accounts": [{"id": "main", "nombre": "Main", "is_main": True, "saldo_inicial": 0.0, "bank_id": "bk"},
              {"id": "sec", "nombre": "Sec", "is_main": False, "saldo_inicial": 0.0, "bank_id": "bk"}],
 "banks": [{"id": "bk", "nombre": "Banco"}],
 "categories": [{"id": "food", "nombre": "Food", "tipo": "normal"}],
 "salaries": [{"id": "s1", "nombre": "Job", "account_id": "main", "bank_id": "bk", "salario_bruto": 2000.0,
               "fecha_inicio": datetime(2026, 1, 1), "fecha_fin": None, "deductions": [],
               "revisiones": [{"desde": prev, "salario_bruto": 2200.0, "cobro_desde": cur}]}],
 "overtimes": [{"id": "ot1", "salary_id": "s1", "monto_bruto": 150.0, "mes_aplicacion": cur}],
 "fixed_expenses": [{"id": "rent", "nombre": "Alquiler", "account_id": "main", "bank_id": "bk",
                     "monto": 700.0, "fecha_inicio": datetime(2026, 1, 1), "fecha_fin": None,
                     "revisiones": [{"desde": cur, "monto": 750.0}]},
                    {"id": "old", "nombre": "Viejo", "account_id": "main", "bank_id": "bk", "monto": 10.0,
                     "fecha_inicio": datetime(2025, 1, 1), "fecha_fin": datetime(2025, 6, 30)}],
 "transfers": [{"id": "loan1", "cuenta_origen": "sec", "cuenta_destino": "main", "monto": 400.0,
                "fecha": datetime(2026, 1, 10), "is_loan": True, "status": "pending", "outstanding_amount": 250.0}],
 "fixed_expense_instances": [{"id": "i1", "fixed_expense_id": "rent", "mes": prev, "estado": "pagado", "monto": None}],
 "expenses": [{"id": "cc1", "nombre": "TV", "account_id": "main", "bank_id": "bk", "categoria_id": "food",
               "monto": 300.0, "fecha": datetime(y, m, 20), "metodo_pago": "credito",
               "mes_cargo": cur, "reservar_en": "compra"}],
}
DB: dict = {}


class Fake:
    def __init__(self, name): self.name = name
    def get_all(self): return copy.deepcopy(DB.get(self.name, []))
    def get_by_field(self, f, op, v): return [x for x in self.get_all() if x.get(f) == v]
    def get_by_fields(self, filters): return self.get_all()
    def get_by_id(self, i): return next((x for x in self.get_all() if x["id"] == i), None)
    def add(self, data):
        data = dict(data); data["id"] = f"{self.name}{len(DB.get(self.name, []))}"
        DB.setdefault(self.name, []).append(data); return data["id"]
    def update(self, i, data): [x.update(data) for x in DB.get(self.name, []) if x["id"] == i]
    def delete(self, i): DB[self.name] = [x for x in DB.get(self.name, []) if x["id"] != i]

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGES = ["monthly_view", "transactions", "dashboard", "salaries", "budgets",
         "fixed_expenses", "transfers", "accounts", "banks", "categories"]


@pytest.fixture(autouse=True)
def fake_firestore(monkeypatch):
    DB.clear(); DB.update(copy.deepcopy(SEED))
    import services.data_cache as dc
    monkeypatch.setattr(fs, "FirestoreService", Fake)
    monkeypatch.setattr(dc, "FirestoreService", Fake)  # bound at import time
    fs._clear_firestore_caches()
    yield
    fs._clear_firestore_caches()


def _run(page):
    at = AppTest.from_file(os.path.join(ROOT, "pages", f"{page}.py"), default_timeout=30)
    at.run()
    assert not at.exception, [e.message for e in at.exception]
    return at


@pytest.mark.parametrize("page", PAGES)
def test_page_renders(page):
    _run(page)


def test_settle_and_undo_card_debt():
    at = _run("monthly_view")
    assert any("tarjeta" in c.value for c in at.caption)
    next(b for b in at.button if b.label.startswith("Saldar")).click().run()
    assert not at.exception
    assert [(s["mes_cargo"], s["monto"]) for s in DB["credit_settlements"]] == [(cur, 300.0)]
    next(b for b in at.button if "Saldado" in b.label).click().run()
    assert not at.exception
    assert DB["credit_settlements"] == []


def test_fixed_expense_change_amount_and_safe_delete():
    # Note: AppTest can't click buttons *inside* st.dialog (fragment reruns), so we
    # check the dialogs open with the right options; the writes are trivial updates.
    at = _run("fixed_expenses")
    assert any("750,00" in m.value for m in at.markdown)          # current amount uses the revision
    next(b for b in at.button if b.label == "Cambiar importe/cuenta").click().run()
    assert not at.exception and any(b.label == "Aplicar" for b in at.button)
    at = _run("fixed_expenses")
    next(b for b in at.button if b.label == "Delete").click().run()
    assert not at.exception
    labels = [b.label for b in at.button]
    assert "Finalizar" in labels and "Borrar igualmente" in labels  # paid history -> offers end, not plain delete


def test_salaries_page_shows_raise_overtime_and_breakdown():
    at = _run("salaries")
    labels = [e.label for e in at.expander]
    assert "Horas extra (1)" in labels and "Historial salarial" in labels and "Detalle mensual" in labels
    assert any("2.200,00" in m.value for m in at.markdown)        # current gross reflects the raise
    next(b for b in at.button if b.label == "Subida salarial").click().run()
    assert not at.exception and any(b.label == "Aplicar subida" for b in at.button)
    at = _run("salaries")
    next(b for b in at.button if b.label == "Editar").click().run()
    assert not at.exception and any(b.label == "Guardar" for b in at.button)


def test_dashboard_sections_and_pending():
    at = _run("dashboard")
    subs = [h.value for h in at.subheader]
    assert any(x.startswith("Este mes") for x in subs) and "Pendiente este mes" in subs \
        and "Hacia dónde vas" in subs
    pending = at.dataframe[0].value
    assert set(pending["Tipo"]) == {"Gasto fijo", "Tarjeta", "Préstamo"}


def test_fixed_expenses_hides_finished_and_reaches_old_months():
    at = _run("fixed_expenses")
    names = " ".join(m.value for m in at.markdown)
    assert "Viejo" not in names                                    # finished -> hidden by default
    assert at.toggle[0].label == "Mostrar finalizados (1)"
    at.toggle[0].set_value(True).run()
    assert any("Viejo" in m.value for m in at.markdown)
    assert "2025-01" in next(sb for sb in at.selectbox if sb.label == "Select Month").options                    # history back to the oldest expense
    next(b for b in at.button if b.label == "Cambiar importe/cuenta").click().run()
    assert not at.exception
    assert any(sb.label == "Cuenta de cargo" for sb in at.selectbox)


def test_monthly_view_shows_projection_if_loans_settled():
    at = _run("monthly_view")
    line = next(m.value for m in at.markdown if "Si se saldan los préstamos" in m.value)
    assert "devuelves 250,00" in line
