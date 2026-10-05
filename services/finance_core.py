"""
Pure finance calculations.

No Streamlit, no Firestore, no clock: everything the calculations depend on is
passed in explicitly (`data` = the dict produced by load_all_data(), and
`current_month` = "YYYY-MM"). That makes every rule testable with plain
fixtures (see tests/).

`services.finance_engine` is a thin cached wrapper around this module and keeps
the public API used by the pages.
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime
from functools import wraps

from dateutil.relativedelta import relativedelta

from models.salary import normalize_deductions
from utils.date_utils import is_active_in_month, parse_month

# The earliest month for which carry-over from previous month is computed.
# Months at or before this value receive 0 as remaining_from_previous_month.
MIN_MANAGED_MONTH: str = "2026-02"

AUTO_TRANSFER_DESCRIPTION = "Transferencia automatica gastos"


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def as_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()


def month_of(value) -> str:
    return as_date(value).strftime("%Y-%m")


def add_months(month: str, n: int) -> str:
    return (parse_month(month) + relativedelta(months=n)).strftime("%Y-%m")


# ----- credit card purchases ---------------------------------------------
# An expense with metodo_pago == "credito" is a card purchase:
#   - mes_cargo   : month the bank charges it (default: purchase month + 1)
#   - reservar_en : "compra" -> reserved in the purchase month's projection/budgets
#                   "cargo"  -> paid with the charge month's salary: belongs to that
#                               month for projection and budgets
# Cash (Real) is only affected when the debt is settled: one credit_settlements
# document per (account_id, mes_cargo), dated when the bank actually charged it.

def is_credit(exp: dict) -> bool:
    return exp.get("metodo_pago") == "credito"


def charge_month(exp: dict) -> str:
    return exp.get("mes_cargo") or add_months(month_of(exp["fecha"]), 1)


def reserve_month(exp: dict) -> str:
    return charge_month(exp) if exp.get("reservar_en") == "cargo" else month_of(exp["fecha"])


def accrual_month(exp: dict) -> str:
    """Month an expense counts for projections and budgets."""
    return reserve_month(exp) if is_credit(exp) else month_of(exp["fecha"])


def _active(item: dict, month: str) -> bool:
    start = as_date(item["fecha_inicio"])
    end = as_date(item["fecha_fin"]) if item.get("fecha_fin") else None
    return is_active_in_month(start, end, month)


def _memo(method):
    """Per-instance memoization (the carry-over chain is recursive)."""
    @wraps(method)
    def wrapper(self, *args):
        key = (method.__name__, args)
        if key not in self._cache:
            self._cache[key] = method(self, *args)
        return self._cache[key]
    return wrapper


def _absorb_deficit(resultado: float, budget_details: list[dict], track_absorbed: bool) -> float:
    """
    If `resultado` is negative, absorb the deficit proportionally from budgets
    that still have available room. Mutates budget_details. Returns the new result.
    """
    if resultado >= 0:
        return resultado
    positive = [bd for bd in budget_details if bd["available"] > 0]
    total_available = sum(bd["available"] for bd in positive)
    if total_available <= 0:
        return resultado
    absorption = min(abs(resultado), total_available)
    remaining = absorption
    for i, bd in enumerate(positive):
        if i == len(positive) - 1:
            share = remaining  # ensures shares sum exactly to absorption
        else:
            share = absorption * (bd["available"] / total_available)
            remaining -= share
        if track_absorbed:
            bd["absorbed"] = share
        bd["available"] -= share
    return resultado + absorption


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

class FinanceCore:
    def __init__(self, data: dict, current_month: str, min_managed_month: str = MIN_MANAGED_MONTH):
        self.data = data
        self.current_month = current_month
        self.min_managed_month = min_managed_month
        self._cache: dict = {}

    # ----- lookups ---------------------------------------------------------

    @property
    def _settlements(self) -> dict:
        if "_settlements" not in self._cache:
            self._cache["_settlements"] = {
                (st_["account_id"], st_["mes_cargo"]): st_
                for st_ in self.data.get("credit_settlements", [])
            }
        return self._cache["_settlements"]

    def settled_month(self, exp: dict) -> str | None:
        """Month in which the card debt containing `exp` was settled (None = pending)."""
        st_ = self._settlements.get((exp.get("account_id"), charge_month(exp)))
        return month_of(st_["fecha"]) if st_ else None

    def _credit_expenses(self, account_id: str) -> list:
        return [e for e in self.data["expenses"] if is_credit(e) and e.get("account_id") == account_id]

    def _cash_expenses(self) -> list:
        return [e for e in self.data["expenses"] if not is_credit(e)]

    @_memo
    def credit_debt_carried_into(self, account_id: str, month: str) -> float:
        """
        Card debt reserved in an earlier month that the projection of `month` must
        still charge. Only for months <= current: their carry-over is cash (Real of
        closed months), which never saw these purchases. Future months chain the
        projection itself, which already reserved them -> nothing to add (no double count).
        """
        if month > self.current_month:
            return 0.0
        total = 0.0
        for e in self._credit_expenses(account_id):
            if reserve_month(e) >= month:
                continue
            settled = self.settled_month(e)
            if settled is None or settled >= month:
                total += e.get("monto", 0.0)
        return total

    @_memo
    def credit_outstanding(self, account_id: str, month: str, reserved_only: bool = True) -> float:
        """
        Unsettled card debt at the end of `month`.
        reserved_only=True : only purchases already reserved (reserve month <= month),
                             used by the projected balance.
        reserved_only=False: everything bought up to `month` -> the card's balance.
        """
        total = 0.0
        for e in self._credit_expenses(account_id):
            ref = reserve_month(e) if reserved_only else month_of(e["fecha"])
            if ref > month:
                continue
            settled = self.settled_month(e)
            if settled is None or settled > month:
                total += e.get("monto", 0.0)
        return total

    def credit_groups(self) -> list[dict]:
        """Card debts grouped by (account, charge month), with settlement status."""
        groups: dict = {}
        for e in self.data["expenses"]:
            if not is_credit(e):
                continue
            key = (e.get("account_id"), charge_month(e))
            g = groups.setdefault(key, {"account_id": key[0], "mes_cargo": key[1],
                                        "total": 0.0, "items": [],
                                        "settlement": self._settlements.get(key)})
            g["total"] += e.get("monto", 0.0)
            g["items"].append(e)
        return sorted(groups.values(), key=lambda g: (g["mes_cargo"], g["account_id"] or ""))

    def _settlements_in(self, account_id: str, month: str) -> float:
        return sum(
            st_.get("monto", 0.0)
            for st_ in self.data.get("credit_settlements", [])
            if st_.get("account_id") == account_id and month_of(st_["fecha"]) == month
        )

    def _salaries_for(self, account_id: str, month: str) -> float:
        return sum(
            self.salary_net(s["id"], month)
            for s in self.data["salaries"]
            if s.get("account_id") == account_id and _active(s, month)
        )

    def _sum_in_month(self, collection: str, field: str, account_id: str, month: str) -> float:
        return sum(
            x["monto"]
            for x in self.data[collection]
            if x.get(field) == account_id and month_of(x["fecha"]) == month
        )

    # ----- salaries --------------------------------------------------------

    @_memo
    def salary_net(self, salary_id: str, month: str) -> float:
        """Net salary for the month: gross + overtime - deductions."""
        salary = next((s for s in self.data["salaries"] if s.get("id") == salary_id), None)
        if not salary:
            return 0.0
        bruto = salary.get("salario_bruto", 0.0)
        overtime = sum(
            ot.get("monto_bruto", 0.0)
            for ot in self.data["overtimes"]
            if ot.get("salary_id") == salary_id and ot.get("mes_aplicacion") == month
        )
        total_deductions = sum(
            (bruto + (overtime if d.get("applies_to_extras", False) else 0.0))
            * float(d.get("percentage", 0.0))
            for d in normalize_deductions(salary)
            if d.get("name")
        )
        return bruto + overtime - total_deductions

    # ----- month building blocks -------------------------------------------

    @_memo
    def active_budgets(self, month: str) -> list:
        return [b for b in self.data["budgets"] if _active(b, month)]

    @_memo
    def fixed_expenses_for_month(self, month: str) -> list:
        """Fixed expenses active in the month, with payment status for that month."""
        instances_by_fe: dict = {}
        for inst in self.data["fixed_expense_instances"]:
            fe_id = inst.get("fixed_expense_id")
            if fe_id:
                instances_by_fe.setdefault(fe_id, []).append(inst)
        result = []
        for fe in self.data["fixed_expenses"]:
            if not _active(fe, month):
                continue
            inst = next((i for i in instances_by_fe.get(fe["id"], []) if i.get("mes") == month), None)
            res = dict(fe)
            res["estado"] = inst.get("estado") if inst else "impagado"
            res["monto_pagado"] = inst.get("monto") if inst else None
            result.append(res)
        return result

    @_memo
    def category_spending(self, month: str, account_id: str | None = None) -> dict:
        """Spending per category, netted by extra incomes tagged with a non-'extra' category."""
        expenses = self.data["expenses"]
        incomes = self.data["incomes"]
        if account_id:
            expenses = [e for e in expenses if e.get("account_id") == account_id]
            incomes = [i for i in incomes if i.get("account_id") == account_id]
        spending: dict = {}
        for exp in expenses:
            if accrual_month(exp) == month:
                cat_id = exp["categoria_id"]
                spending[cat_id] = spending.get(cat_id, 0.0) + exp.get("monto", 0.0)
        categories = {c.get("id"): c for c in self.data["categories"]}
        for inc in incomes:
            cat_id = inc.get("categoria_id")
            if month_of(inc["fecha"]) == month and cat_id:
                cat = categories.get(cat_id)
                if cat and cat.get("tipo", "normal") != "extra":
                    spending[cat_id] = spending.get(cat_id, 0.0) - inc.get("monto", 0.0)
        return spending

    @_memo
    def raw_category_expenses(self, month: str, account_id: str | None = None) -> dict:
        """Raw (non-netted) expense totals per category."""
        raw: dict = {}
        for exp in self.data["expenses"]:
            if account_id and exp.get("account_id") != account_id:
                continue
            if accrual_month(exp) == month:
                cat_id = exp.get("categoria_id", "")
                raw[cat_id] = raw.get(cat_id, 0.0) + exp.get("monto", 0.0)
        return raw

    @_memo
    def pending_loans_for_account(self, account_id: str, month: str | None = None) -> list:
        pending = [
            t for t in self.data["transfers"]
            if t.get("cuenta_destino") == account_id
            and t.get("is_loan", False)
            and t.get("status", "pending") == "pending"
            and t.get("outstanding_amount", t.get("monto", 0.0)) > 0
        ]
        if month:
            pending = [t for t in pending if month_of(t["fecha"]) == month]
        return pending

    @_memo
    def propio_expenses_by_account(self, month: str, main_account_id: str) -> dict:
        """
        Pending (impagado) 'propio' fixed expenses of non-main accounts, minus the
        automatic reimbursement transfers already sent from the main account this month.
        """
        result: dict = {}
        for fe in self.fixed_expenses_for_month(month):
            if not fe.get("es_propio", False) or fe.get("estado", "impagado") != "impagado":
                continue
            acc_id = fe.get("account_id")
            if acc_id and acc_id != main_account_id:
                result[acc_id] = result.get(acc_id, 0.0) + fe.get("monto", 0.0)
        for trf in self.data["transfers"]:
            if (
                trf.get("cuenta_origen") != main_account_id
                or trf.get("descripcion") != AUTO_TRANSFER_DESCRIPTION
                or month_of(trf["fecha"]) != month
            ):
                continue
            acc_id = trf.get("cuenta_destino")
            if acc_id and acc_id in result:
                result[acc_id] = max(0.0, result[acc_id] - trf.get("monto", 0.0))
        return {acc_id: amt for acc_id, amt in result.items() if amt > 0}

    # ----- month results ---------------------------------------------------

    @_memo
    def month_real_result(self, account_id: str, month: str) -> float:
        """Cash-basis result of one account in one month (no carry-over).
        Card purchases don't count; their settlement does, in the month it's paid."""
        income = (
            self._salaries_for(account_id, month)
            + self._sum_in_month("incomes", "account_id", account_id, month)
            + self._sum_in_month("transfers", "cuenta_destino", account_id, month)
        )
        fixed_paid = sum(
            fe["monto_pagado"] if fe.get("monto_pagado") is not None else fe["monto"]
            for fe in self.fixed_expenses_for_month(month)
            if fe.get("account_id") == account_id and fe["estado"] == "pagado"
        )
        cash_expenses = sum(
            e["monto"] for e in self._cash_expenses()
            if e.get("account_id") == account_id and month_of(e["fecha"]) == month
        )
        expense = (
            cash_expenses
            + self._settlements_in(account_id, month)
            + fixed_paid
            + self._sum_in_month("transfers", "cuenta_origen", account_id, month)
        )
        return income - expense

    @_memo
    def month_projected_result(self, account_id: str, month: str, remaining_from_previous_month: float = 0.0) -> dict:
        """
        Projected result of one account in one month:
            + net salaries + extra incomes + transfers in + carry-over
            - fixed expenses (paid + pending)
            - active budgets (max(budget, raw spent))
            - non-budgeted raw expenses
            - transfers out
            - card debt reserved in a closed month and still relevant this month
              (see credit_debt_carried_into)
        then a negative result is absorbed by budgets with room left.
        """
        income = (
            self._salaries_for(account_id, month)
            + self._sum_in_month("incomes", "account_id", account_id, month)
            + self._sum_in_month("transfers", "cuenta_destino", account_id, month)
        )
        transfers_out = self._sum_in_month("transfers", "cuenta_origen", account_id, month)
        fixed_total = sum(
            fe["monto_pagado"] if fe.get("monto_pagado") is not None else fe["monto"]
            for fe in self.fixed_expenses_for_month(month)
            if fe.get("account_id") == account_id
        )
        budgets = [b for b in self.active_budgets(month) if b.get("account_id") == account_id]
        raw = self.raw_category_expenses(month, account_id)

        budget_impact = 0.0
        details = []
        for b in budgets:
            spent = raw.get(b["categoria_id"], 0.0)
            budget_impact += max(b["monto"], max(spent, 0.0))
            details.append({
                "budget_id": b["id"],
                "categoria_id": b["categoria_id"],
                "presupuesto": b["monto"],
                "real_spent": spent,
                "available": b["monto"] - max(spent, 0.0),
                "absorbed": 0.0,
            })
        budget_cats = {b["categoria_id"] for b in budgets}
        non_budgeted = sum(v for cat, v in raw.items() if cat not in budget_cats)

        credit_carried = self.credit_debt_carried_into(account_id, month)

        pre = (
            income + remaining_from_previous_month
            - fixed_total - budget_impact - non_budgeted - transfers_out
            - credit_carried
        )
        resultado = _absorb_deficit(pre, details, track_absorbed=True)
        return {"resultado": resultado, "resultado_pre_absorcion": pre, "budget_details": details,
                "deuda_tarjeta_arrastrada": credit_carried}

    @_memo
    def remaining_from_previous_month(self, month: str, main_account_id: str) -> float:
        """
        Carry-over into `month`:
          - previous month closed (< current): real result of prev month + its own carry-in
          - otherwise: chain projected results from the current month up to prev month,
            subtracting pending 'gastos propios' each month.
        """
        if month <= self.min_managed_month:
            return 0.0
        prev = add_months(month, -1)
        if prev < self.min_managed_month:
            return 0.0

        if prev < self.current_month:
            return (
                self.month_real_result(main_account_id, prev)
                + self.remaining_from_previous_month(prev, main_account_id)
            )

        carry = (
            self.remaining_from_previous_month(self.current_month, main_account_id)
            if add_months(self.current_month, -1) >= self.min_managed_month
            else 0.0
        )
        m = self.current_month
        while m <= prev:
            proj = self.month_projected_result(main_account_id, m, carry)
            propios = sum(self.propio_expenses_by_account(m, main_account_id).values())
            carry = proj["resultado"] - propios
            m = add_months(m, 1)
        return carry

    # ----- cumulative balances ---------------------------------------------

    @_memo
    def historical_salary_incomes(self, account_id: str, up_to_month: str | None = None) -> float:
        target = parse_month(up_to_month or self.current_month)
        total = 0.0
        for s in self.data["salaries"]:
            if s.get("account_id") != account_id:
                continue
            start = as_date(s["fecha_inicio"])
            end = as_date(s["fecha_fin"]) if s.get("fecha_fin") else None
            itr = start.replace(day=1)
            end_itr = target.replace(day=1)
            if end and end.replace(day=1) < end_itr:
                end_itr = end.replace(day=1)
            while itr <= end_itr:
                m = itr.strftime("%Y-%m")
                if is_active_in_month(start, end, m):
                    total += self.salary_net(s["id"], m)
                itr += relativedelta(months=1)
        return total

    @_memo
    def real_balance(self, account_id: str, month: str | None = None) -> float:
        """Cumulative balance from initial balance to the end of `month`."""
        account = next((a for a in self.data["accounts"] if a.get("id") == account_id), None)
        if not account:
            return 0.0
        target_month = month or self.current_month
        target = parse_month(target_month)
        cutoff = target.replace(day=monthrange(target.year, target.month)[1])

        def upto(collection, field):
            return sum(
                x.get("monto", 0.0)
                for x in self.data[collection]
                if x.get(field) == account_id and as_date(x["fecha"]) <= cutoff
            )

        balance = account.get("saldo_inicial", 0.0)
        balance += self.historical_salary_incomes(account_id, target_month)
        balance += upto("incomes", "account_id")
        balance -= sum(
            e.get("monto", 0.0) for e in self._cash_expenses()
            if e.get("account_id") == account_id and as_date(e["fecha"]) <= cutoff
        )
        balance -= sum(
            st_.get("monto", 0.0) for st_ in self.data.get("credit_settlements", [])
            if st_.get("account_id") == account_id and as_date(st_["fecha"]) <= cutoff
        )

        fes = {fe["id"]: fe for fe in self.data["fixed_expenses"] if fe.get("account_id") == account_id}
        for inst in self.data["fixed_expense_instances"]:
            fe = fes.get(inst.get("fixed_expense_id"))
            if fe and inst.get("estado") == "pagado" and inst.get("mes", "") <= target_month:
                balance -= inst.get("monto") if inst.get("monto") is not None else fe.get("monto", 0.0)

        balance -= upto("transfers", "cuenta_origen")
        balance += upto("transfers", "cuenta_destino")
        return balance

    @_memo
    def projected_balance(self, account_id: str, month: str | None = None) -> dict:
        """real balance - unpaid fixed expenses - unspent budget, with deficit absorption."""
        target_month = month or self.current_month
        real = self.real_balance(account_id, target_month)
        fixed_pending = sum(
            fe["monto"]
            for fe in self.fixed_expenses_for_month(target_month)
            if fe.get("account_id") == account_id and fe["estado"] == "impagado"
        )
        raw = self.raw_category_expenses(target_month, account_id)
        details = []
        pending_budget = 0.0
        for b in self.active_budgets(target_month):
            if b["account_id"] != account_id:
                continue
            spent = raw.get(b["categoria_id"], 0.0)
            effective = max(spent, 0.0)
            details.append({
                "budget_id": b["id"],
                "categoria_id": b["categoria_id"],
                "presupuesto": b["monto"],
                "real_spent": spent,
                "available": b["monto"] - effective,
            })
            if effective < b["monto"]:
                pending_budget += b["monto"] - effective
        credit_pending = self.credit_outstanding(account_id, target_month, True)
        resultado = _absorb_deficit(real - fixed_pending - pending_budget - credit_pending,
                                    details, track_absorbed=False)
        return {"resultado": resultado, "budget_details": details}

    # ----- summary ---------------------------------------------------------

    @_memo
    def month_summary(self, month: str) -> dict:
        d = self.data
        main = next((a for a in d["accounts"] if a.get("is_main", False)), None)
        summary = {
            "ingreso_total": sum(self.salary_net(s["id"], month) for s in d["salaries"] if _active(s, month)),
            "gastos_fijos": sum(fe["monto"] for fe in self.fixed_expenses_for_month(month)),
            "presupuestos": sum(b["monto"] for b in self.active_budgets(month)),
            "gastos_reales": sum(e["monto"] for e in d["expenses"] if month_of(e["fecha"]) == month),
            "ingresos_extra": sum(i["monto"] for i in d["incomes"] if month_of(i["fecha"]) == month),
            "remaining_from_previous_month": 0.0,
            "resultado_real": 0.0,
            "resultado_proyectado": 0.0,
            "resultado_proyectado_pre_absorcion": 0.0,
            "resultado_real_details": None,
        }
        if main:
            main_id = main["id"]
            carry = self.remaining_from_previous_month(month, main_id)
            proj = self.month_projected_result(main_id, month, carry)
            summary.update({
                "remaining_from_previous_month": carry,
                "resultado_real": self.month_real_result(main_id, month) + carry,
                "resultado_proyectado": proj["resultado"],
                "resultado_proyectado_pre_absorcion": proj["resultado_pre_absorcion"],
                "deuda_tarjeta_arrastrada": proj["deuda_tarjeta_arrastrada"],
                "resultado_real_details": {
                    "main_account_id": main_id,
                    "main_account_name": main.get("nombre", "Main"),
                    "pending_loans": self.pending_loans_for_account(main_id),
                    "snapshot_status": None,
                },
            })
        return summary
