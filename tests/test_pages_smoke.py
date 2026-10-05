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
 "accounts": [{"id": "main", "nombre": "Main", "is_main": True, "saldo_inicial": 0.0, "bank_id": "bk"}],
 "banks": [{"id": "bk", "nombre": "Banco"}],
 "categories": [{"id": "food", "nombre": "Food", "tipo": "normal"}],
 "salaries": [{"id": "s1", "nombre": "Job", "account_id": "main", "bank_id": "bk", "salario_bruto": 2000.0,
               "fecha_inicio": datetime(2026, 1, 1), "fecha_fin": None, "deductions": []}],
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
