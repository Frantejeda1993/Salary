from datetime import datetime
from typing import Optional
import streamlit as st
from dateutil.relativedelta import relativedelta
from utils.date_utils import is_active_in_month, get_current_month, parse_month
from services.firestore_service import FirestoreService
from services.data_cache import load_all_data

# Services for easy access
def _get_service(collection_name):
    return FirestoreService(collection_name)


def _get_monthly_snapshot_service():
    return _get_service("monthly_account_snapshots")


def get_monthly_account_snapshot(month: str, account_id: str) -> Optional[dict]:
    """Returns the monthly snapshot for (month, account_id), if present."""
    snapshots = [
        s for s in load_all_data()["monthly_account_snapshots"]
        if s.get("month") == month and s.get("account_id") == account_id
    ]
    return snapshots[0] if snapshots else None


def upsert_monthly_account_snapshot(month: str, account_id: str, data: dict) -> dict:
    """Creates or updates snapshot identified by logical key (month, account_id)."""
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
    if "resultado_proyectado_frozen" in data and data.get("resultado_proyectado_frozen") is not None:
        payload["resultado_proyectado_frozen"] = float(data["resultado_proyectado_frozen"])

    existing = get_monthly_account_snapshot(month, account_id)
    if existing:
        snapshot_srv.update(existing["id"], payload)
        return snapshot_srv.get_by_id(existing["id"])

    payload["created_at"] = now
    doc_id = snapshot_srv.add(payload)
    return snapshot_srv.get_by_id(doc_id)


def resolve_main_account_for_month(month: str) -> Optional[dict]:
    """Resolves the main account for a month using snapshot state first."""
    data = load_all_data()
    month_snapshots = [s for s in data["monthly_account_snapshots"] if s.get("month") == month]
    main_snapshot = next((s for s in month_snapshots if s.get("is_main_account_for_month", False)), None)

    if main_snapshot and main_snapshot.get("account_id"):
        account = next((a for a in data["accounts"] if a.get("id") == main_snapshot["account_id"]), None)
        if account:
            account["snapshot"] = main_snapshot
            return account

    accounts = data["accounts"]
    return next((a for a in accounts if a.get("is_main", False)), None)


def _get_previous_month(month: str) -> str:
    return (parse_month(month) - relativedelta(months=1)).strftime("%Y-%m")


MIN_MANAGED_MONTH = "2026-04"  # March and before = 0


def get_remaining_from_previous_month(month: str, main_account_id: str) -> float:
    """
    Returns the carry-over balance from the previous month into `month`.

    Rules:
    - If month <= MIN_MANAGED_MONTH: return 0.0
    - If previous month is closed: return resultado_real_closed from snapshot
    - If previous month is open: return calculate_projected_balance() for that month
    """
    if month <= MIN_MANAGED_MONTH:
        return 0.0

    previous_month = _get_previous_month(month)
    if previous_month < MIN_MANAGED_MONTH:
        return 0.0

    previous_snapshot = get_monthly_account_snapshot(previous_month, main_account_id)
    if previous_snapshot and previous_snapshot.get("status") == "closed":
        return float(previous_snapshot.get("resultado_real_closed", 0.0))

    proj = calculate_projected_balance(main_account_id, previous_month)
    return float(proj["resultado"])


def _get_snapshot_effective_result(snapshot: Optional[dict]) -> Optional[float]:
    if not snapshot:
        return None

    status = snapshot.get("status")
    if status == "closed":
        return float(snapshot.get("resultado_real_closed", 0.0))
    if status == "future_projection":
        return float(snapshot.get("resultado_proyectado_frozen", 0.0))

    return None


def _as_date(value):
    if isinstance(value, datetime):
        return value.date()
    return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()


def _month_of(value) -> str:
    return _as_date(value).strftime("%Y-%m")


def _ensure_future_projection_snapshot(month: str, account_id: str, resultado_proyectado: float) -> dict:
    """
    Creates/updates a future month snapshot for the selected main account.
    remaining_from_previous_month is derived from a chain of snapshots when possible.
    """
    current_month = get_current_month()
    previous_month = _get_previous_month(month)

    previous_snapshot = get_monthly_account_snapshot(previous_month, account_id)
    if previous_snapshot is None and previous_month > current_month:
        # Build chain for future months that do not yet have snapshots.
        _ensure_future_projection_snapshot(previous_month, account_id, 0.0)
        previous_snapshot = get_monthly_account_snapshot(previous_month, account_id)

    # Determina el remaining según el estado del mes anterior
    remaining_from_previous_month = 0.0
    if previous_snapshot:
        status = previous_snapshot.get("status")
        if status == "closed":
            # Mes anterior cerrado: usar resultado_real_closed
            remaining_from_previous_month = float(previous_snapshot.get("resultado_real_closed", 0.0))
        elif status == "open":
            # Mes anterior abierto: usar resultado_proyectado_frozen
            remaining_from_previous_month = float(previous_snapshot.get("resultado_proyectado_frozen", 0.0))
        else:
            # Fallback: usar remaining_from_previous_month
            remaining_from_previous_month = float(previous_snapshot.get("remaining_from_previous_month", 0.0))

    return upsert_monthly_account_snapshot(month, account_id, {
        "is_main_account_for_month": True,
        "remaining_from_previous_month": float(remaining_from_previous_month),
        "resultado_proyectado_frozen": float(resultado_proyectado),
        "status": "future_projection",
    })


def _calculate_main_account_result_for_month(account_id: str, month: str, remaining_from_previous_month: float = 0.0) -> float:
    """Calcula el resultado real de una cuenta principal para un mes."""
    data = load_all_data()
    salaries = data["salaries"]
    expenses = data["expenses"]
    incomes = data["incomes"]
    transfers = data["transfers"]
    fixed_all = get_fixed_expenses_for_month(month)

    main_salaries = sum(calculate_salary_net(s['id'], month) for s in salaries if s.get('account_id') == account_id and is_active_in_month(
        _as_date(s['fecha_inicio']),
        _as_date(s['fecha_fin']) if s.get('fecha_fin') else None,
        month
    ))

    main_fixed = sum(
        (fe.get('monto_pagado') if fe.get('monto_pagado') is not None else fe['monto'])
        for fe in fixed_all
        if fe.get('account_id') == account_id and fe['estado'] == 'pagado'
    )
    main_expenses = sum(
        e['monto'] for e in expenses
        if e.get('account_id') == account_id and
        _month_of(e['fecha']) == month
    )

    main_base_incomes = sum(
        i['monto'] for i in incomes
        if i.get('account_id') == account_id and
        _month_of(i['fecha']) == month
    )
    main_loans_total = sum(
        l.get('outstanding_amount', l.get('monto', 0.0))
        for l in get_pending_loans_for_account(account_id, month)
    )
    main_extra_incomes = main_base_incomes + main_loans_total
    main_transfers_out = sum(
        t['monto'] for t in transfers
        if t.get('cuenta_origen') == account_id and
        _month_of(t['fecha']) == month
    )
    main_transfers_in = sum(
        t['monto'] for t in transfers
        if t.get('cuenta_destino') == account_id and
        _month_of(t['fecha']) == month
    )

    return remaining_from_previous_month + main_salaries + main_extra_incomes - main_expenses - main_fixed - main_transfers_out + main_transfers_in


def run_month_rollover_if_needed(today=None) -> dict:
    """Cierra el mes anterior y abre el mes actual de forma idempotente."""
    today_date = today.date() if isinstance(today, datetime) else today
    if today_date is None:
        today_date = datetime.now().date()

    current_month = today_date.strftime("%Y-%m")
    previous_month = (today_date.replace(day=1) - relativedelta(months=1)).strftime("%Y-%m")
    min_managed_month = "2026-03"

    if current_month < min_managed_month:
        return {
            "current_month": current_month,
            "previous_month": previous_month,
            "skipped": True
        }

    closed_result = None
    previous_main = resolve_main_account_for_month(previous_month) if previous_month >= min_managed_month else None
    if previous_main:
        previous_account_id = previous_main["id"]
        previous_snapshot = get_monthly_account_snapshot(previous_month, previous_account_id)
        previous_remaining = float(previous_snapshot.get("remaining_from_previous_month", 0.0)) if previous_snapshot else 0.0

        if previous_snapshot and previous_snapshot.get("status") == "closed":
            closed_result = float(previous_snapshot.get("resultado_real_closed", 0.0))
        else:
            closed_result = _calculate_main_account_result_for_month(previous_account_id, previous_month, previous_remaining)
            upsert_monthly_account_snapshot(previous_month, previous_account_id, {
                "is_main_account_for_month": True,
                "remaining_from_previous_month": previous_remaining,
                "resultado_real_closed": closed_result,
                "status": "closed",
            })

    current_main = resolve_main_account_for_month(current_month)
    if current_main:
        current_account_id = current_main["id"]
        current_snapshot = get_monthly_account_snapshot(current_month, current_account_id)
        current_status = current_snapshot.get("status") if current_snapshot else "open"
        carry_value = float(closed_result if closed_result is not None else 0.0)

        upsert_monthly_account_snapshot(current_month, current_account_id, {
            "is_main_account_for_month": True,
            "remaining_from_previous_month": carry_value,
            "resultado_real_closed": float(current_snapshot.get("resultado_real_closed", 0.0)) if current_snapshot else 0.0,
            "status": "closed" if current_status == "closed" else "open",
        })

    return {
        "current_month": current_month,
        "previous_month": previous_month,
        "closed_result": closed_result,
        "skipped": False
    }

@st.cache_data(ttl=120, show_spinner=False)
def calculate_salary_net(salary_id: str, month: str) -> float:
    """Calculates the net salary for a given month considering active deductions and overtimes."""
    data = load_all_data()
    salary_data = next((s for s in data["salaries"] if s.get("id") == salary_id), None)
    if not salary_data:
        return 0.0
    
    bruto = salary_data.get('salario_bruto', 0.0)
    
    # Get overtime for this month
    overtimes = [ot for ot in data["overtimes"] if ot.get("salary_id") == salary_id]
    overtime_amount = sum(ot.get('monto_bruto', 0.0) for ot in overtimes if ot.get('mes_aplicacion') == month)
    
    net = bruto + overtime_amount
    
    # Calculate deductions
    total_deductions = 0.0
    
    if 'deductions' in salary_data and isinstance(salary_data['deductions'], list):
        for d in salary_data['deductions']:
            percent = float(d.get('percentage', 0.0))
            apply_extra = d.get('applies_to_extras', False)
            
            base_for_deduction = bruto
            if apply_extra:
                base_for_deduction += overtime_amount
                
            total_deductions += base_for_deduction * percent
    else:
        # Fallback to old format
        old_deductions = [
            ('cont_comun', 'cont_comun_aplica_extras'),
            ('mei', 'mei_aplica_extras'),
            ('formacion', 'formacion_aplica_extras'),
            ('desempleo', 'desempleo_aplica_extras'),
            ('irpf', 'irpf_aplica_extras')
        ]
        
        for ded, applies_to_extras in old_deductions:
            percent = salary_data.get(ded, 0.0) / 100.0
            apply_extra = salary_data.get(applies_to_extras, False)
            
            base_for_deduction = bruto
            if apply_extra:
                base_for_deduction += overtime_amount
                
            total_deductions += base_for_deduction * percent
            
    return net - total_deductions

@st.cache_data(ttl=120, show_spinner=False)
def _get_account_historical_salary_incomes(account_id: str, up_to_month: str = None) -> float:
    """Calculates total net salary incomes received in the account up to a certain month (inclusive)."""
    data = load_all_data()
    salaries = [s for s in data["salaries"] if s.get("account_id") == account_id]
    
    current_m = up_to_month or get_current_month()
    target_date = parse_month(current_m)
    
    total = 0.0
    for s in salaries:
        start_date = _as_date(s['fecha_inicio'])
        # End date might be None
        end_date = s.get('fecha_fin')
        if end_date:
            end_date = _as_date(end_date)
            
        # Iterate months from start_date to min(target_date, end_date)
        # For simplicity, we can just check is_active_in_month for all months past
        # We need a proper way to iterate months.
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
    """Calculated as: saldo_inicial + sueldos netos_pasados + ingresos_extra - gastos - transferencias_salientes + transferencias_entrantes"""
    data = load_all_data()
    account = next((a for a in data["accounts"] if a.get("id") == account_id), None)
    if not account: return 0.0
    
    balance = account.get('saldo_inicial', 0.0)
    target_month = month or get_current_month()
    
    # Add all past and current month salaries
    balance += _get_account_historical_salary_incomes(account_id, target_month)
    
    # Extra incomes
    incomes = [i for i in data["incomes"] if i.get("account_id") == account_id]
    balance += sum(inc.get('monto', 0.0) for inc in incomes)
    
    # Expenses (gastos_pagados are essentially the expenses table)
    expenses = [e for e in data["expenses"] if e.get("account_id") == account_id]
    balance -= sum(exp.get('monto', 0.0) for exp in expenses)
    
    # Paid fixed expenses
    all_fixed = [fe for fe in data["fixed_expenses"] if fe.get("account_id") == account_id]
    instances_by_fixed_expense = {}
    for inst in data["fixed_expense_instances"]:
        fe_id = inst.get("fixed_expense_id")
        if fe_id:
            instances_by_fixed_expense.setdefault(fe_id, []).append(inst)
    for fe in all_fixed:
        instances = instances_by_fixed_expense.get(fe['id'], [])
        paid_instances = [inst for inst in instances if inst.get('estado') == 'pagado']
        balance -= sum(inst.get('monto', fe.get('monto', 0.0)) for inst in paid_instances)
    
    # Transfers out
    transfers_out = [t for t in data["transfers"] if t.get("cuenta_origen") == account_id]
    balance -= sum(tr.get('monto', 0.0) for tr in transfers_out)
    
    # Transfers in
    transfers_in = [t for t in data["transfers"] if t.get("cuenta_destino") == account_id]
    balance += sum(tr.get('monto', 0.0) for tr in transfers_in)
    
    return balance

@st.cache_data(ttl=120, show_spinner=False)
def get_active_budgets(month: str) -> list:
    """Returns all budgets active in a given month."""
    budgets = load_all_data()["budgets"]
    active = []
    for b in budgets:
        start = _as_date(b['fecha_inicio'])
        end = b.get('fecha_fin')
        if end:
            end = _as_date(end)
        if is_active_in_month(start, end, month):
            active.append(b)
    return active

@st.cache_data(ttl=120, show_spinner=False)
def get_fixed_expenses_for_month(month: str) -> list:
    """Returns fixed expenses active in the month along with their payment status."""
    data = load_all_data()
    fixed_exps = data["fixed_expenses"]
    instances_by_fixed_expense = {}
    for inst in data["fixed_expense_instances"]:
        fe_id = inst.get("fixed_expense_id")
        if fe_id:
            instances_by_fixed_expense.setdefault(fe_id, []).append(inst)
    active_in_month = []
    
    for fe in fixed_exps:
        start = _as_date(fe['fecha_inicio'])
        end = fe.get('fecha_fin')
        if end:
            end = _as_date(end)
            
        if is_active_in_month(start, end, month):
            # Check if paid
            instances = instances_by_fixed_expense.get(fe['id'], [])
            month_instance = next((inst for inst in instances if inst.get('mes') == month), None)
            estado = month_instance.get('estado') if month_instance else 'impagado'
            monto_pagado = month_instance.get('monto') if month_instance else None

            # append state to dictionary
            res = dict(fe)
            res['estado'] = estado
            res['monto_pagado'] = monto_pagado
            active_in_month.append(res)
            
    return active_in_month

@st.cache_data(ttl=120, show_spinner=False)
def calculate_category_spending(month: str, account_id: str = None) -> dict:
    """Calculates spending directly from 'expenses' mapping category_id -> amount for a given month."""
    data = load_all_data()
    expenses = data["expenses"]
    if account_id:
        expenses = [e for e in expenses if e.get('account_id') == account_id]
        
    spending = {}
    for exp in expenses:
        if _month_of(exp['fecha']) == month:
            cat_id = exp['categoria_id']
            spending[cat_id] = spending.get(cat_id, 0.0) + exp.get('monto', 0.0)
            
    # Include extra incomes reduction: Si tiene categoría reduce gasto de la categoría (user spec)
    incomes = data["incomes"]
    if account_id:
        incomes = [i for i in incomes if i.get('account_id') == account_id]
        
    categories_by_id = {c.get("id"): c for c in data["categories"]}
    for inc in incomes:
        cat_id = inc.get('categoria_id')
        if _month_of(inc['fecha']) == month and cat_id:
            cat = categories_by_id.get(cat_id)
            if cat and cat.get('tipo', 'normal') != 'extra':
                # Reduce expense
                spending[cat_id] = spending.get(cat_id, 0.0) - inc.get('monto', 0.0)
                
    return spending

@st.cache_data(ttl=120, show_spinner=False)
def calculate_projected_balance(account_id: str, month: str | None = None) -> dict:
    """Calcula el saldo proyectado para el mes indicado (o mes actual por defecto).

    El saldo real ya incluye los gastos reales registrados. Por eso aquí solo se resta:
    - gastos fijos impagados del mes objetivo, y
    - la parte pendiente de cada presupuesto activo (presupuesto - gasto_real, si es positiva).

    Si el resultado es negativo y hay budgets con dinero disponible, el déficit se distribuye
    proporcionalmente entre ellos y el resultado vuelve a 0.0.
    Si no hay budgets con disponibilidad, el resultado se mantiene negativo.

    Retorna:
        dict con:
        - 'resultado': float - El resultado proyectado final
        - 'budget_details': list - Detalles de cada budget con disponibilidad actualizada
    """
    target_month = month or get_current_month()
    real = calculate_real_balance(account_id, target_month)
    
    # Gastos fijos pendientes for target month
    fixed_this_month = get_fixed_expenses_for_month(target_month)
    fixed_pendientes = sum(fe['monto'] for fe in fixed_this_month if fe['account_id'] == account_id and fe['estado'] == 'impagado')
    
    # Presupuestos
    active_budgets = get_active_budgets(target_month)
    spending = calculate_category_spending(target_month, account_id)
    
    # Calcula detalles de cada presupuesto
    budget_details = []
    pending_budget_impact = 0.0

    for b in active_budgets:
        if b['account_id'] != account_id:
            continue

        cat_id = b['categoria_id']
        presupuesto = b['monto']
        real_spent = spending.get(cat_id, 0.0)
        available = presupuesto - real_spent

        budget_details.append({
            'budget_id': b['id'],
            'categoria_id': cat_id,
            'presupuesto': presupuesto,
            'real_spent': real_spent,
            'available': available
        })

        if real_spent < presupuesto:
            pending_budget_impact += available

    resultado = real - fixed_pendientes - pending_budget_impact

    # Si el resultado es negativo, distribuir el déficit entre budgets con disponibilidad
    if resultado < 0:
        budgets_with_available = [bd for bd in budget_details if bd['available'] > 0]

        if budgets_with_available:
            # Hay presupuestos con dinero disponible para absorber el déficit
            deficit = abs(resultado)
            total_available = sum(bd['available'] for bd in budgets_with_available)

            if total_available >= deficit:
                # El déficit se puede cubrir completamente con los budgets disponibles
                # Distribuir el déficit proporcionalmente
                for bd in budgets_with_available:
                    proportion = bd['available'] / total_available if total_available > 0 else 0
                    reduction = deficit * proportion
                    bd['available'] -= reduction

                # El resultado proyectado ahora es 0.0 (déficit absorbido completamente)
                resultado = 0.0
            else:
                # El déficit es mayor que la disponibilidad total: distribuir todo lo disponible
                # y dejar el déficit restante como resultado negativo
                total_deficit_absorbed = total_available
                remaining_deficit = deficit - total_available

                for bd in budgets_with_available:
                    proportion = bd['available'] / total_available if total_available > 0 else 0
                    reduction = total_deficit_absorbed * proportion
                    bd['available'] -= reduction

                resultado = -remaining_deficit
        # Si no hay disponibilidad en budgets, el resultado se mantiene negativo

    return {
        'resultado': resultado,
        'budget_details': budget_details
    }

def get_projected_balance_value(account_id: str, month: str | None = None) -> float:
    """Helper function que retorna solo el valor float del resultado proyectado.
    Usa esta función cuando solo necesites el número, no los detalles de budgets.
    """
    result = calculate_projected_balance(account_id, month)
    return result['resultado']

@st.cache_data(ttl=120, show_spinner=False)
def get_pending_loans_for_account(account_id: str, month: str = None) -> list:
    """Returns incoming pending loans for an account, optionally filtered by month."""
    transfers = [t for t in load_all_data()["transfers"] if t.get("cuenta_destino") == account_id]
    pending_loans = [
        t for t in transfers
        if t.get('is_loan', False) and t.get('status', 'pending') == 'pending' and t.get('outstanding_amount', t.get('monto', 0.0)) > 0
    ]
    if month:
        pending_loans = [
            t for t in pending_loans
            if _month_of(t['fecha']) == month
        ]
    return pending_loans

@st.cache_data(ttl=120, show_spinner=False)
def get_month_summary(month: str) -> dict:
    """Returns summary for month view."""
    current_month = get_current_month()
    is_future_month = month > current_month
    data = load_all_data()

    # Ingreso total, Gastos fijos, Presupuestos, Gastos reales, Ingresos extra
    salaries = data["salaries"]
    ingreso_total = sum(calculate_salary_net(s['id'], month) for s in salaries if is_active_in_month(
            _as_date(s['fecha_inicio']),
            _as_date(s['fecha_fin']) if s.get('fecha_fin') else None,
            month
        ))
        
    fixed_all = get_fixed_expenses_for_month(month)
    gastos_fijos_total = sum(fe['monto'] for fe in fixed_all)
    
    budgets = get_active_budgets(month)
    presupuestos_total = sum(b['monto'] for b in budgets)
    
    expenses = data["expenses"]
    gastos_reales = sum(e['monto'] for e in expenses if _month_of(e['fecha']) == month)
    
    incomes = data["incomes"]
    ingresos_extra_base = sum(i['monto'] for i in incomes if _month_of(i['fecha']) == month)
    
    # Add ALL pending loans for this month to extra incomes (global)
    transfers = data["transfers"]
    loans_this_month = sum(
        t.get('outstanding_amount', t.get('monto', 0.0)) for t in transfers 
        if t.get('is_loan', False) and t.get('status', 'pending') == 'pending' and 
        t.get('outstanding_amount', t.get('monto', 0.0)) > 0 and
        _month_of(t['fecha']) == month
    )
    
    ingresos_extra_total = ingresos_extra_base + loans_this_month
    
    # Calculate Results
    fixed_paid = sum((fe.get('monto_pagado') if fe.get('monto_pagado') is not None else fe['monto']) for fe in fixed_all if fe['estado'] == 'pagado')
    
    # Identify Main Account for "Resultado Real" using monthly snapshot if present
    main_acc = resolve_main_account_for_month(month)
    
    resultado_real_details = None
    remaining_from_previous_month = 0.0
    if main_acc:
        main_id = main_acc['id']
        month_snapshot = main_acc.get("snapshot") or get_monthly_account_snapshot(month, main_id)
        remaining_from_previous_month = get_remaining_from_previous_month(month, main_id)

        main_salaries = sum(calculate_salary_net(s['id'], month) for s in salaries if s.get('account_id') == main_id and is_active_in_month(
            _as_date(s['fecha_inicio']),
            _as_date(s['fecha_fin']) if s.get('fecha_fin') else None,
            month
        ))
        
        main_fixed = sum((fe.get('monto_pagado') if fe.get('monto_pagado') is not None else fe['monto']) for fe in fixed_all if fe.get('account_id') == main_id and fe['estado'] == 'pagado')
        main_expenses = sum(e['monto'] for e in expenses if e.get('account_id') == main_id and _month_of(e['fecha']) == month)
        
        main_base_incomes = sum(i['monto'] for i in incomes if i.get('account_id') == main_id and _month_of(i['fecha']) == month)
        main_loans = [
            t for t in transfers
            if t.get('cuenta_destino') == main_id and t.get('is_loan', False) and t.get('status', 'pending') == 'pending'
            and t.get('outstanding_amount', t.get('monto', 0.0)) > 0 and _month_of(t['fecha']) == month
        ]
        main_loans_total = sum(l.get('outstanding_amount', l.get('monto', 0.0)) for l in main_loans)
        
        main_extra_incomes = main_base_incomes + main_loans_total
        main_transfers_out = sum(
            t['monto'] for t in transfers
            if t.get('cuenta_origen') == main_id and
            _month_of(t['fecha']) == month
        )
        main_transfers_in = sum(
            t['monto'] for t in transfers
            if t.get('cuenta_destino') == main_id and
            _month_of(t['fecha']) == month
        )
        
        # SIEMPRE recalcula para asegurar que incluye transferencias
        resultado_real = remaining_from_previous_month + main_salaries + main_extra_incomes - main_expenses - main_fixed - main_transfers_out + main_transfers_in
        
        resultado_real_details = {
            "main_account_id": main_id,
            "main_account_name": main_acc.get('nombre', 'Main'),
            "pending_loans": get_pending_loans_for_account(main_id), # all pending loans for the main account, regardless of month
            "snapshot_status": month_snapshot.get("status") if month_snapshot else None
        }
    else:
        resultado_real = ingreso_total + ingresos_extra_total - gastos_reales - fixed_paid
    
    # Projected Result for the month = Ingreso_Total + Ingresos_Extra - Gastos fijos - max(Presupuestos, Gastos_Reales for budget categories) - Unbudgeted Gastos
    spending = calculate_category_spending(month)
    impacto_presupuestos = 0.0
    budget_cat_ids = [b['categoria_id'] for b in budgets]
    for b in budgets:
        real_spent = spending.get(b['categoria_id'], 0.0)
        impacto_presupuestos += max(b['monto'], real_spent)
        
    gastos_no_presupuestados = sum(v for k, v in spending.items() if k not in budget_cat_ids)
    
    resultado_proyectado = ingreso_total + ingresos_extra_total - gastos_fijos_total - impacto_presupuestos - gastos_no_presupuestados

    if is_future_month and main_acc:
        main_id = main_acc["id"]
        future_snapshot = _ensure_future_projection_snapshot(month, main_id, resultado_proyectado)
        remaining_from_previous_month = float(future_snapshot.get("remaining_from_previous_month", remaining_from_previous_month))
        resultado_proyectado = float(future_snapshot.get("resultado_proyectado_frozen", resultado_proyectado))
        if resultado_real_details:
            resultado_real_details["snapshot_status"] = future_snapshot.get("status")
    
    return {
        "ingreso_total": ingreso_total,
        "gastos_fijos": gastos_fijos_total,
        "presupuestos": presupuestos_total,
        "gastos_reales": gastos_reales,
        "ingresos_extra": ingresos_extra_total,
        "remaining_from_previous_month": remaining_from_previous_month,
        "resultado_real": resultado_real,
        "resultado_proyectado": resultado_proyectado,
        "resultado_real_details": resultado_real_details
    }
