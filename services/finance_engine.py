from datetime import datetime
from calendar import monthrange
from typing import Optional
import streamlit as st
from dateutil.relativedelta import relativedelta
from utils.date_utils import is_active_in_month, get_current_month, parse_month
from services.firestore_service import FirestoreService
from services.data_cache import load_all_data

MIN_MANAGED_MONTH = "2026-02"  # Months before this return 0 for remaining


def _get_service(collection_name):
    return FirestoreService(collection_name)


def _as_date(value):
    if isinstance(value, datetime):
        return value.date()
    return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()


def _month_of(value) -> str:
    return _as_date(value).strftime("%Y-%m")


# ---------------------------------------------------------------------------
# Salary & snapshot helpers
# ---------------------------------------------------------------------------

@st.cache_data(ttl=120, show_spinner=False)
def calculate_salary_net(salary_id: str, month: str) -> float:
    """Calculates the net salary for a given month considering active deductions and overtimes."""
    data = load_all_data()
    salary_data = next((s for s in data["salaries"] if s.get("id") == salary_id), None)
    if not salary_data:
        return 0.0

    bruto = salary_data.get('salario_bruto', 0.0)
    overtimes = [ot for ot in data["overtimes"] if ot.get("salary_id") == salary_id]
    overtime_amount = sum(ot.get('monto_bruto', 0.0) for ot in overtimes if ot.get('mes_aplicacion') == month)

    net = bruto + overtime_amount
    total_deductions = 0.0

    if 'deductions' in salary_data and isinstance(salary_data['deductions'], list):
        for d in salary_data['deductions']:
            percent = float(d.get('percentage', 0.0))
            apply_extra = d.get('applies_to_extras', False)
            base = bruto + (overtime_amount if apply_extra else 0.0)
            total_deductions += base * percent
    else:
        old_deductions = [
            ('cont_comun', 'cont_comun_aplica_extras'),
            ('mei', 'mei_aplica_extras'),
            ('formacion', 'formacion_aplica_extras'),
            ('desempleo', 'desempleo_aplica_extras'),
            ('irpf', 'irpf_aplica_extras'),
        ]
        for ded, applies_key in old_deductions:
            percent = salary_data.get(ded, 0.0) / 100.0
            apply_extra = salary_data.get(applies_key, False)
            base = bruto + (overtime_amount if apply_extra else 0.0)
            total_deductions += base * percent

    return net - total_deductions


@st.cache_data(ttl=120, show_spinner=False)
def get_active_budgets(month: str) -> list:
    """Returns all budgets active in a given month."""
    budgets = load_all_data()["budgets"]
    active = []
    for b in budgets:
        start = _as_date(b['fecha_inicio'])
        end = _as_date(b['fecha_fin']) if b.get('fecha_fin') else None
        if is_active_in_month(start, end, month):
            active.append(b)
    return active


@st.cache_data(ttl=120, show_spinner=False)
def get_fixed_expenses_for_month(month: str) -> list:
    """Returns fixed expenses active in the month along with their payment status."""
    data = load_all_data()
    instances_by_fe = {}
    for inst in data["fixed_expense_instances"]:
        fe_id = inst.get("fixed_expense_id")
        if fe_id:
            instances_by_fe.setdefault(fe_id, []).append(inst)

    result = []
    for fe in data["fixed_expenses"]:
        start = _as_date(fe['fecha_inicio'])
        end = _as_date(fe['fecha_fin']) if fe.get('fecha_fin') else None
        if not is_active_in_month(start, end, month):
            continue
        month_inst = next((i for i in instances_by_fe.get(fe['id'], []) if i.get('mes') == month), None)
        res = dict(fe)
        res['estado'] = month_inst.get('estado') if month_inst else 'impagado'
        res['monto_pagado'] = month_inst.get('monto') if month_inst else None
        result.append(res)
    return result


@st.cache_data(ttl=120, show_spinner=False)
def calculate_category_spending(month: str, account_id: str = None) -> dict:
    """Calculates spending per category for a given month, optionally filtered by account."""
    data = load_all_data()
    expenses = data["expenses"]
    if account_id:
        expenses = [e for e in expenses if e.get('account_id') == account_id]

    spending = {}
    for exp in expenses:
        if _month_of(exp['fecha']) == month:
            cat_id = exp['categoria_id']
            spending[cat_id] = spending.get(cat_id, 0.0) + exp.get('monto', 0.0)

    # Extra incomes with a non-"extra" category reduce that category's spending
    incomes = data["incomes"]
    if account_id:
        incomes = [i for i in incomes if i.get('account_id') == account_id]

    categories_by_id = {c.get("id"): c for c in data["categories"]}
    for inc in incomes:
        cat_id = inc.get('categoria_id')
        if _month_of(inc['fecha']) == month and cat_id:
            cat = categories_by_id.get(cat_id)
            if cat and cat.get('tipo', 'normal') != 'extra':
                spending[cat_id] = spending.get(cat_id, 0.0) - inc.get('monto', 0.0)

    return spending


@st.cache_data(ttl=120, show_spinner=False)
def get_pending_loans_for_account(account_id: str, month: str = None) -> list:
    """Returns incoming pending loans for an account, optionally filtered by month."""
    transfers = [t for t in load_all_data()["transfers"] if t.get("cuenta_destino") == account_id]
    pending = [
        t for t in transfers
        if t.get('is_loan', False)
        and t.get('status', 'pending') == 'pending'
        and t.get('outstanding_amount', t.get('monto', 0.0)) > 0
    ]
    if month:
        pending = [t for t in pending if _month_of(t['fecha']) == month]
    return pending


@st.cache_data(ttl=120, show_spinner=False)
def get_propio_expenses_by_account(month: str, main_account_id: str) -> dict:
    """
    Returns total propio expenses by non-main account for the month.
    Includes both fixed expenses and real expenses marked as es_propio.
    """
    result = {}

    # 1) Propio fixed expenses active in month
    for fe in get_fixed_expenses_for_month(month):
        if not fe.get("es_propio", False):
            continue
        acc_id = fe.get("account_id")
        if acc_id and acc_id != main_account_id:
            amount = fe.get("monto_pagado") if fe.get("monto_pagado") is not None else fe.get("monto", 0.0)
            result[acc_id] = result.get(acc_id, 0.0) + amount

    # 2) Propio real expenses in month
    data = load_all_data()
    for exp in data["expenses"]:
        if not exp.get("es_propio", False):
            continue
        if _month_of(exp["fecha"]) != month:
            continue
        acc_id = exp.get("account_id")
        if acc_id and acc_id != main_account_id:
            result[acc_id] = result.get(acc_id, 0.0) + exp.get("monto", 0.0)

    return result


# ---------------------------------------------------------------------------
# Month-scoped result calculations
# ---------------------------------------------------------------------------

@st.cache_data(ttl=120, show_spinner=False)
def calculate_month_real_result(account_id: str, month: str) -> float:
    """
    Real result for a specific account and month.

    = net salaries (active in month, deposited to this account)
    + extra incomes (fecha in month, to this account)
    + transfers received (fecha in month, to this account)
    - real expenses (fecha in month, from this account)
    - fixed expenses PAID this month (from this account)
    - transfers sent (fecha in month, from this account)
    """
    data = load_all_data()

    # Salaries deposited to this account and active in this month
    salary_total = sum(
        calculate_salary_net(s["id"], month)
        for s in data["salaries"]
        if s.get("account_id") == account_id
        and is_active_in_month(
            _as_date(s["fecha_inicio"]),
            _as_date(s["fecha_fin"]) if s.get("fecha_fin") else None,
            month,
        )
    )

    # Extra incomes received this month into this account
    income_total = sum(
        i["monto"]
        for i in data["incomes"]
        if i.get("account_id") == account_id and _month_of(i["fecha"]) == month
    )

    # Transfers received this month
    transfers_in = sum(
        t["monto"]
        for t in data["transfers"]
        if t.get("cuenta_destino") == account_id and _month_of(t["fecha"]) == month
    )

    # Real expenses this month from this account
    expense_total = sum(
        e["monto"]
        for e in data["expenses"]
        if e.get("account_id") == account_id and _month_of(e["fecha"]) == month
    )

    # Fixed expenses already PAID this month from this account
    fixed_paid = sum(
        (fe.get("monto_pagado") if fe.get("monto_pagado") is not None else fe["monto"])
        for fe in get_fixed_expenses_for_month(month)
        if fe.get("account_id") == account_id and fe["estado"] == "pagado"
    )

    # Transfers sent this month from this account
    transfers_out = sum(
        t["monto"]
        for t in data["transfers"]
        if t.get("cuenta_origen") == account_id and _month_of(t["fecha"]) == month
    )

    return salary_total + income_total + transfers_in - expense_total - fixed_paid - transfers_out


@st.cache_data(ttl=120, show_spinner=False)
def calculate_month_projected_result(account_id: str, month: str) -> dict:
    """
    Projected result for a specific account and month.

    Income side (same as real):
      + net salaries + extra incomes + transfers received

    Expense side (includes pending obligations):
      - ALL fixed expenses this month (paid + pending)
      - For budgeted categories: max(budget, actual_spent)
      - For non-budgeted categories: actual spent (positive only)
      - transfers sent

    If resultado < 0 and there are budgets with available > 0, the deficit is
    absorbed into the budget with the most available capacity (shows projected = 0
    with that budget reduced). If no positive budgets exist, projected stays negative.

    Returns:
        dict with 'resultado' (float) and 'budget_details' (list).
    """
    data = load_all_data()

    # --- Income ---
    salary_total = sum(
        calculate_salary_net(s["id"], month)
        for s in data["salaries"]
        if s.get("account_id") == account_id
        and is_active_in_month(
            _as_date(s["fecha_inicio"]),
            _as_date(s["fecha_fin"]) if s.get("fecha_fin") else None,
            month,
        )
    )

    income_total = sum(
        i["monto"]
        for i in data["incomes"]
        if i.get("account_id") == account_id and _month_of(i["fecha"]) == month
    )

    transfers_in = sum(
        t["monto"]
        for t in data["transfers"]
        if t.get("cuenta_destino") == account_id and _month_of(t["fecha"]) == month
    )

    transfers_out = sum(
        t["monto"]
        for t in data["transfers"]
        if t.get("cuenta_origen") == account_id and _month_of(t["fecha"]) == month
    )

    # --- Fixed expenses (ALL: paid + pending) ---
    fixed_total = sum(
        fe["monto"]
        for fe in get_fixed_expenses_for_month(month)
        if fe.get("account_id") == account_id
    )

    # --- Budget impact ---
    active_budgets = [b for b in get_active_budgets(month) if b.get("account_id") == account_id]
    spending = calculate_category_spending(month, account_id)
    budget_cat_ids = {b["categoria_id"] for b in active_budgets}

    budget_impact = 0.0
    budget_details = []
    for b in active_budgets:
        cat_id = b["categoria_id"]
        presupuesto = b["monto"]
        real_spent = spending.get(cat_id, 0.0)
        # Use actual if it exceeds the budget; otherwise assume full budget will be spent
        effective = max(presupuesto, real_spent)
        available = presupuesto - max(real_spent, 0.0)
        budget_impact += effective
        budget_details.append({
            "budget_id": b["id"],
            "categoria_id": cat_id,
            "presupuesto": presupuesto,
            "real_spent": real_spent,
            "available": available,
        })

    # Non-budgeted actual expenses (only positive values count)
    non_budgeted = sum(
        max(v, 0.0) for k, v in spending.items() if k not in budget_cat_ids
    )

    resultado = (
        salary_total + income_total + transfers_in
        - fixed_total
        - budget_impact
        - non_budgeted
        - transfers_out
    )

    # If projected result is negative but there are budgets with available capacity,
    # absorb the deficit into the budget with the most available (show projected = 0).
    # If no positive budgets exist, resultado stays negative.
    if resultado < 0:
        positive_budgets = [bd for bd in budget_details if bd['available'] > 0]
        total_available = sum(bd['available'] for bd in positive_budgets)
        deficit = abs(resultado)
        if total_available > 0:
            absorption = min(deficit, total_available)
            for bd in positive_budgets:
                proportion = bd['available'] / total_available
                bd['available'] -= absorption * proportion
            resultado = -(deficit - absorption)  # 0.0 if fully covered, negative if not

    return {"resultado": resultado, "budget_details": budget_details}

# ---------------------------------------------------------------------------
# Remaining from previous month (simplified – no snapshots needed)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=120, show_spinner=False)
def get_remaining_from_previous_month(month: str, main_account_id: str) -> float:
    """
    Result carried over from the previous month into `month`.

    - Uses real cumulative balance at the end of previous month.
    - Previous month is before MIN_MANAGED_MONTH → 0.0
    """
    if month <= MIN_MANAGED_MONTH:
        return 0.0

    prev_month = (parse_month(month) - relativedelta(months=1)).strftime("%Y-%m")
    if prev_month < MIN_MANAGED_MONTH:
        return 0.0

    return calculate_real_balance(main_account_id, prev_month)


# ---------------------------------------------------------------------------
# Cumulative account balance (used in Dashboard and Balances table)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=120, show_spinner=False)
def _get_account_historical_salary_incomes(account_id: str, up_to_month: str = None) -> float:
    """Total net salary incomes received in the account up to a certain month (inclusive)."""
    data = load_all_data()
    salaries = [s for s in data["salaries"] if s.get("account_id") == account_id]
    current_m = up_to_month or get_current_month()
    target_date = parse_month(current_m)

    total = 0.0
    for s in salaries:
        start_date = _as_date(s['fecha_inicio'])
        end_date = _as_date(s['fecha_fin']) if s.get('fecha_fin') else None
        itr = start_date.replace(day=1)
        end_itr = target_date.replace(day=1)
        if end_date and end_date.replace(day=1) < end_itr:
            end_itr = end_date.replace(day=1)
        while itr <= end_itr:
            month_str = itr.strftime("%Y-%m")
            if is_active_in_month(start_date, end_date, month_str):
                total += calculate_salary_net(s['id'], month_str)
            itr += relativedelta(months=1)
    return total


@st.cache_data(ttl=120, show_spinner=False)
def calculate_real_balance(account_id: str, month: str | None = None) -> float:
    """
    Cumulative account balance from initial balance up to the end of target month.
    Used for Dashboard totals and Balances per Account table.
    """
    data = load_all_data()
    account = next((a for a in data["accounts"] if a.get("id") == account_id), None)
    if not account:
        return 0.0

    target_month = month or get_current_month()
    target_date = parse_month(target_month)
    _, last_day = monthrange(target_date.year, target_date.month)
    cutoff = target_date.replace(day=last_day).date()

    balance = account.get('saldo_inicial', 0.0)

    balance += _get_account_historical_salary_incomes(account_id, target_month)

    balance += sum(
        i.get('monto', 0.0)
        for i in data["incomes"]
        if i.get("account_id") == account_id and _as_date(i['fecha']) <= cutoff
    )
    balance -= sum(
        e.get('monto', 0.0)
        for e in data["expenses"]
        if e.get("account_id") == account_id and _as_date(e['fecha']) <= cutoff
    )

    instances_by_fe = {}
    for inst in data["fixed_expense_instances"]:
        fe_id = inst.get("fixed_expense_id")
        if fe_id:
            instances_by_fe.setdefault(fe_id, []).append(inst)
    for fe in [f for f in data["fixed_expenses"] if f.get("account_id") == account_id]:
        paid = [
            i for i in instances_by_fe.get(fe['id'], [])
            if i.get('estado') == 'pagado' and i.get('mes', '') <= target_month
        ]
        balance -= sum(
            i.get('monto') if i.get('monto') is not None else fe.get('monto', 0.0)
            for i in paid
        )

    balance -= sum(
        t.get('monto', 0.0)
        for t in data["transfers"]
        if t.get("cuenta_origen") == account_id and _as_date(t['fecha']) <= cutoff
    )
    balance += sum(
        t.get('monto', 0.0)
        for t in data["transfers"]
        if t.get("cuenta_destino") == account_id and _as_date(t['fecha']) <= cutoff
    )

    return balance


@st.cache_data(ttl=120, show_spinner=False)
def calculate_projected_balance(account_id: str, month: str | None = None) -> dict:
    """
    Cumulative projected balance = real_balance − pending fixed − pending budgets.
    Used for the Balances per Account table and Dashboard.
    """
    target_month = month or get_current_month()
    real = calculate_real_balance(account_id, target_month)

    fixed_pendientes = sum(
        fe['monto']
        for fe in get_fixed_expenses_for_month(target_month)
        if fe['account_id'] == account_id and fe['estado'] == 'impagado'
    )

    active_budgets = get_active_budgets(target_month)
    spending = calculate_category_spending(target_month, account_id)

    budget_details = []
    pending_budget_impact = 0.0
    for b in active_budgets:
        if b['account_id'] != account_id:
            continue
        cat_id = b['categoria_id']
        presupuesto = b['monto']
        real_spent = max(spending.get(cat_id, 0.0), 0.0)
        available = presupuesto - real_spent
        budget_details.append({
            'budget_id': b['id'],
            'categoria_id': cat_id,
            'presupuesto': presupuesto,
            'real_spent': real_spent,
            'available': available,
        })
        if real_spent < presupuesto:
            pending_budget_impact += available

    resultado = real - fixed_pendientes - pending_budget_impact

    if resultado < 0:
        budgets_with_available = [bd for bd in budget_details if bd['available'] > 0]
        if budgets_with_available:
            deficit = abs(resultado)
            total_available = sum(bd['available'] for bd in budgets_with_available)
            if total_available >= deficit:
                for bd in budgets_with_available:
                    proportion = bd['available'] / total_available if total_available > 0 else 0
                    bd['available'] -= deficit * proportion
                resultado = 0.0
            else:
                for bd in budgets_with_available:
                    proportion = bd['available'] / total_available if total_available > 0 else 0
                    bd['available'] -= total_available * proportion
                resultado = -(deficit - total_available)

    return {'resultado': resultado, 'budget_details': budget_details}


# ---------------------------------------------------------------------------
# Month summary (used by Dashboard and Monthly View headers)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=120, show_spinner=False)
def get_month_summary(month: str) -> dict:
    """High-level summary for a given month."""
    data = load_all_data()

    salaries = data["salaries"]
    ingreso_total = sum(
        calculate_salary_net(s['id'], month)
        for s in salaries
        if is_active_in_month(
            _as_date(s['fecha_inicio']),
            _as_date(s['fecha_fin']) if s.get('fecha_fin') else None,
            month,
        )
    )

    fixed_all = get_fixed_expenses_for_month(month)
    gastos_fijos_total = sum(fe['monto'] for fe in fixed_all)

    budgets = get_active_budgets(month)
    presupuestos_total = sum(b['monto'] for b in budgets)

    gastos_reales = sum(
        e['monto'] for e in data["expenses"] if _month_of(e['fecha']) == month
    )

    ingresos_extra = sum(
        i['monto'] for i in data["incomes"] if _month_of(i['fecha']) == month
    )

    # Locate main account
    main_acc = next((a for a in data["accounts"] if a.get("is_main", False)), None)

    resultado_real = 0.0
    resultado_proyectado = 0.0
    resultado_real_details = None
    remaining_from_previous_month = 0.0

    if main_acc:
        main_id = main_acc['id']
        remaining_from_previous_month = get_remaining_from_previous_month(month, main_id)
        resultado_real = (
            calculate_month_real_result(main_id, month)
            + remaining_from_previous_month
        )
        proj = calculate_month_projected_result(main_id, month)
        resultado_proyectado = proj["resultado"] + remaining_from_previous_month

        resultado_real_details = {
            "main_account_id": main_id,
            "main_account_name": main_acc.get('nombre', 'Main'),
            "pending_loans": get_pending_loans_for_account(main_id),
            "snapshot_status": None,
        }

    return {
        "ingreso_total": ingreso_total,
        "gastos_fijos": gastos_fijos_total,
        "presupuestos": presupuestos_total,
        "gastos_reales": gastos_reales,
        "ingresos_extra": ingresos_extra,
        "remaining_from_previous_month": remaining_from_previous_month,
        "resultado_real": resultado_real,
        "resultado_proyectado": resultado_proyectado,
        "resultado_real_details": resultado_real_details,
    }


# ---------------------------------------------------------------------------
# Snapshot / rollover helpers (kept for backward compatibility, not used for display)
# ---------------------------------------------------------------------------

def _get_monthly_snapshot_service():
    return _get_service("monthly_account_snapshots")


def get_monthly_account_snapshot(month: str, account_id: str) -> Optional[dict]:
    snapshots = [
        s for s in load_all_data()["monthly_account_snapshots"]
        if s.get("month") == month and s.get("account_id") == account_id
    ]
    return snapshots[0] if snapshots else None


def upsert_monthly_account_snapshot(month: str, account_id: str, data: dict) -> dict:
    snapshot_srv = _get_monthly_snapshot_service()
    now = datetime.utcnow()
    payload = {
        "month": month,
        "account_id": account_id,
        "is_main_account_for_month": bool(data.get("is_main_account_for_month", False)),
        "resultado_real_closed": float(data.get("resultado_real_closed", 0.0)),
        "remaining_from_previous_month": float(data.get("remaining_from_previous_month", 0.0)),
        "status": data.get("status", "open"),
        "updated_at": now,
    }
    if data.get("resultado_proyectado_frozen") is not None:
        payload["resultado_proyectado_frozen"] = float(data["resultado_proyectado_frozen"])

    existing = get_monthly_account_snapshot(month, account_id)
    if existing:
        snapshot_srv.update(existing["id"], payload)
        return snapshot_srv.get_by_id(existing["id"])
    payload["created_at"] = now
    doc_id = snapshot_srv.add(payload)
    return snapshot_srv.get_by_id(doc_id)


def resolve_main_account_for_month(month: str) -> Optional[dict]:
    data = load_all_data()
    accounts = data["accounts"]
    return next((a for a in accounts if a.get("is_main", False)), None)


def _get_previous_month(month: str) -> str:
    return (parse_month(month) - relativedelta(months=1)).strftime("%Y-%m")


def run_month_rollover_if_needed(today=None) -> dict:
    """No-op stub kept for compatibility. Display calculations no longer use snapshots."""
    today_date = today.date() if isinstance(today, datetime) else today
    if today_date is None:
        today_date = datetime.now().date()
    current_month = today_date.strftime("%Y-%m")
    previous_month = (today_date.replace(day=1) - relativedelta(months=1)).strftime("%Y-%m")
    return {
        "current_month": current_month,
        "previous_month": previous_month,
        "skipped": True,
    }


def ensure_future_projection_snapshot_for_month(month: str) -> Optional[dict]:
    return None


def get_projected_balance_value(account_id: str, month: str | None = None) -> float:
    return calculate_projected_balance(account_id, month)['resultado']
