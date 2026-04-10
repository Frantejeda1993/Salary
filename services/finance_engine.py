from datetime import datetime
from typing import Optional
from dateutil.relativedelta import relativedelta
from utils.date_utils import is_active_in_month, get_current_month, parse_month
from services.firestore_service import FirestoreService

# Services for easy access
def _get_service(collection_name):
    return FirestoreService(collection_name)


def _get_monthly_snapshot_service():
    return _get_service("monthly_account_snapshots")


def get_monthly_account_snapshot(month: str, account_id: str) -> Optional[dict]:
    """Returns the monthly snapshot for (month, account_id), if present."""
    snapshot_srv = _get_monthly_snapshot_service()
    snapshots = snapshot_srv.get_by_field("month", "==", month)
    return next((s for s in snapshots if s.get("account_id") == account_id), None)


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
    snapshot_srv = _get_monthly_snapshot_service()
    month_snapshots = snapshot_srv.get_by_field("month", "==", month)
    main_snapshot = next((s for s in month_snapshots if s.get("is_main_account_for_month", False)), None)

    if main_snapshot and main_snapshot.get("account_id"):
        account = _get_service("accounts").get_by_id(main_snapshot["account_id"])
        if account:
            account["snapshot"] = main_snapshot
            return account

    accounts = _get_service("accounts").get_all()
    return next((a for a in accounts if a.get("is_main", False)), None)


def _get_previous_month(month: str) -> str:
    return (parse_month(month) - relativedelta(months=1)).strftime("%Y-%m")


def _get_snapshot_effective_result(snapshot: Optional[dict]) -> Optional[float]:
    if not snapshot:
        return None

    status = snapshot.get("status")
    if status == "closed":
        return float(snapshot.get("resultado_real_closed", 0.0))
    if status == "future_projection":
        return float(snapshot.get("resultado_proyectado_frozen", 0.0))

    return None


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

    remaining_from_previous_month = _get_snapshot_effective_result(previous_snapshot)
    if remaining_from_previous_month is None:
        remaining_from_previous_month = float(previous_snapshot.get("remaining_from_previous_month", 0.0)) if previous_snapshot else 0.0

    return upsert_monthly_account_snapshot(month, account_id, {
        "is_main_account_for_month": True,
        "remaining_from_previous_month": float(remaining_from_previous_month),
        "resultado_proyectado_frozen": float(resultado_proyectado),
        "status": "future_projection",
    })


def _calculate_main_account_result_for_month(account_id: str, month: str, remaining_from_previous_month: float = 0.0) -> float:
    """Calcula el resultado real de una cuenta principal para un mes."""
    salaries = _get_service("salaries").get_all()
    expenses = _get_service("expenses").get_all()
    incomes = _get_service("incomes").get_all()
    transfers = _get_service("transfers").get_all()
    fixed_all = get_fixed_expenses_for_month(month)

    main_salaries = sum(calculate_salary_net(s['id'], month) for s in salaries if s.get('account_id') == account_id and is_active_in_month(
        s['fecha_inicio'].date() if isinstance(s['fecha_inicio'], datetime) else datetime.strptime(s['fecha_inicio'][:10], "%Y-%m-%d").date(),
        s['fecha_fin'].date() if isinstance(s['fecha_fin'], datetime) else datetime.strptime(s['fecha_fin'][:10], "%Y-%m-%d").date() if s.get('fecha_fin') else None,
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
        (e['fecha'].date() if isinstance(e['fecha'], datetime) else datetime.strptime(e['fecha'][:10], "%Y-%m-%d").date()).strftime("%Y-%m") == month
    )

    main_base_incomes = sum(
        i['monto'] for i in incomes
        if i.get('account_id') == account_id and
        (i['fecha'].date() if isinstance(i['fecha'], datetime) else datetime.strptime(i['fecha'][:10], "%Y-%m-%d").date()).strftime("%Y-%m") == month
    )
    main_loans_total = sum(
        l.get('outstanding_amount', l.get('monto', 0.0))
        for l in get_pending_loans_for_account(account_id, month)
    )
    main_extra_incomes = main_base_incomes + main_loans_total
    main_transfers_out = sum(
        t['monto'] for t in transfers
        if t.get('cuenta_origen') == account_id and
        (t['fecha'].date() if isinstance(t['fecha'], datetime) else datetime.strptime(t['fecha'][:10], "%Y-%m-%d").date()).strftime("%Y-%m") == month
    )
    main_transfers_in = sum(
        t['monto'] for t in transfers
        if t.get('cuenta_destino') == account_id and
        (t['fecha'].date() if isinstance(t['fecha'], datetime) else datetime.strptime(t['fecha'][:10], "%Y-%m-%d").date()).strftime("%Y-%m") == month
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

def calculate_salary_net(salary_id: str, month: str) -> float:
    """Calculates the net salary for a given month considering active deductions and overtimes."""
    salary_srv = _get_service("salaries")
    overtime_srv = _get_service("overtimes")
    
    salary_data = salary_srv.get_by_id(salary_id)
    if not salary_data:
        return 0.0
    
    bruto = salary_data.get('salario_bruto', 0.0)
    
    # Get overtime for this month
    overtimes = overtime_srv.get_by_field("salary_id", "==", salary_id)
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

def _get_account_historical_salary_incomes(account_id: str, up_to_month: str = None) -> float:
    """Calculates total net salary incomes received in the account up to a certain month (inclusive)."""
    salary_srv = _get_service("salaries")
    salaries = salary_srv.get_by_field("account_id", "==", account_id)
    
    current_m = up_to_month or get_current_month()
    target_date = parse_month(current_m)
    
    total = 0.0
    for s in salaries:
        start_date = s['fecha_inicio'].date() if isinstance(s['fecha_inicio'], datetime) else datetime.strptime(s['fecha_inicio'][:10], "%Y-%m-%d").date()
        # End date might be None
        end_date = s.get('fecha_fin')
        if end_date:
            end_date = end_date.date() if isinstance(end_date, datetime) else datetime.strptime(end_date[:10], "%Y-%m-%d").date()
            
        # Iterate months from start_date to min(target_date, end_date)
        # For simplicity, we can just check is_active_in_month for all months past
        # We need a proper way to iterate months.
        from dateutil.relativedelta import relativedelta
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

def calculate_real_balance(account_id: str, month: str | None = None) -> float:
    """Calculated as: saldo_inicial + sueldos netos_pasados + ingresos_extra - gastos - transferencias_salientes + transferencias_entrantes"""
    account = _get_service("accounts").get_by_id(account_id)
    if not account: return 0.0
    
    balance = account.get('saldo_inicial', 0.0)
    target_month = month or get_current_month()
    
    # Add all past and current month salaries
    balance += _get_account_historical_salary_incomes(account_id, target_month)
    
    # Extra incomes
    incomes = _get_service("incomes").get_by_field("account_id", "==", account_id)
    balance += sum(inc.get('monto', 0.0) for inc in incomes)
    
    # Expenses (gastos_pagados are essentially the expenses table)
    expenses = _get_service("expenses").get_by_field("account_id", "==", account_id)
    balance -= sum(exp.get('monto', 0.0) for exp in expenses)
    
    # Paid fixed expenses
    fixed_exp_srv = _get_service("fixed_expenses")
    fixed_inst_srv = _get_service("fixed_expense_instances")
    all_fixed = fixed_exp_srv.get_by_field("account_id", "==", account_id)
    for fe in all_fixed:
        instances = fixed_inst_srv.get_by_field("fixed_expense_id", "==", fe['id'])
        paid_instances = [inst for inst in instances if inst.get('estado') == 'pagado']
        balance -= sum(inst.get('monto', fe.get('monto', 0.0)) for inst in paid_instances)
    
    # Transfers out
    transfers_out = _get_service("transfers").get_by_field("cuenta_origen", "==", account_id)
    balance -= sum(tr.get('monto', 0.0) for tr in transfers_out)
    
    # Transfers in
    transfers_in = _get_service("transfers").get_by_field("cuenta_destino", "==", account_id)
    balance += sum(tr.get('monto', 0.0) for tr in transfers_in)
    
    return balance

def get_active_budgets(month: str) -> list:
    """Returns all budgets active in a given month."""
    budgets = _get_service("budgets").get_all()
    active = []
    for b in budgets:
        start = b['fecha_inicio'].date() if isinstance(b['fecha_inicio'], datetime) else datetime.strptime(b['fecha_inicio'][:10], "%Y-%m-%d").date()
        end = b.get('fecha_fin')
        if end:
            end = end.date() if isinstance(end, datetime) else datetime.strptime(end[:10], "%Y-%m-%d").date()
        if is_active_in_month(start, end, month):
            active.append(b)
    return active

def get_fixed_expenses_for_month(month: str) -> list:
    """Returns fixed expenses active in the month along with their payment status."""
    fixed_exp_srv = _get_service("fixed_expenses")
    fixed_inst_srv = _get_service("fixed_expense_instances")
    
    fixed_exps = fixed_exp_srv.get_all()
    active_in_month = []
    
    for fe in fixed_exps:
        start = fe['fecha_inicio'].date() if isinstance(fe['fecha_inicio'], datetime) else datetime.strptime(fe['fecha_inicio'][:10], "%Y-%m-%d").date()
        end = fe.get('fecha_fin')
        if end:
            end = end.date() if isinstance(end, datetime) else datetime.strptime(end[:10], "%Y-%m-%d").date()
            
        if is_active_in_month(start, end, month):
            # Check if paid
            instances = fixed_inst_srv.get_by_field("fixed_expense_id", "==", fe['id'])
            month_instance = next((inst for inst in instances if inst.get('mes') == month), None)
            estado = month_instance.get('estado') if month_instance else 'impagado'
            monto_pagado = month_instance.get('monto') if month_instance else None

            # append state to dictionary
            res = dict(fe)
            res['estado'] = estado
            res['monto_pagado'] = monto_pagado
            active_in_month.append(res)
            
    return active_in_month

def calculate_category_spending(month: str, account_id: str = None) -> dict:
    """Calculates spending directly from 'expenses' mapping category_id -> amount for a given month."""
    expenses = _get_service("expenses").get_all()
    if account_id:
        expenses = [e for e in expenses if e.get('account_id') == account_id]
        
    spending = {}
    for exp in expenses:
        fecha = exp['fecha'].date() if isinstance(exp['fecha'], datetime) else datetime.strptime(exp['fecha'][:10], "%Y-%m-%d").date()
        if fecha.strftime("%Y-%m") == month:
            cat_id = exp['categoria_id']
            spending[cat_id] = spending.get(cat_id, 0.0) + exp.get('monto', 0.0)
            
    # Include extra incomes reduction: Si tiene categoría reduce gasto de la categoría (user spec)
    incomes = _get_service("incomes").get_all()
    if account_id:
        incomes = [i for i in incomes if i.get('account_id') == account_id]
        
    for inc in incomes:
        fecha = inc['fecha'].date() if isinstance(inc['fecha'], datetime) else datetime.strptime(inc['fecha'][:10], "%Y-%m-%d").date()
        cat_id = inc.get('categoria_id')
        if fecha.strftime("%Y-%m") == month and cat_id:
            cat_srv = _get_service("categories")
            cat = cat_srv.get_by_id(cat_id)
            if cat and cat.get('tipo', 'normal') != 'extra':
                # Reduce expense
                spending[cat_id] = spending.get(cat_id, 0.0) - inc.get('monto', 0.0)
                
    return spending

def calculate_projected_balance(account_id: str, month: str | None = None) -> float:
    """Calcula el saldo proyectado para el mes indicado (o mes actual por defecto).

    El saldo real ya incluye los gastos reales registrados. Por eso aquí solo se resta:
    - gastos fijos impagados del mes objetivo, y
    - la parte pendiente de cada presupuesto activo (presupuesto - gasto_real, si es positiva).
    """
    target_month = month or get_current_month()
    real = calculate_real_balance(account_id, target_month)
    
    # Gastos fijos pendientes for target month
    fixed_this_month = get_fixed_expenses_for_month(target_month)
    fixed_pendientes = sum(fe['monto'] for fe in fixed_this_month if fe['account_id'] == account_id and fe['estado'] == 'impagado')
    
    # Presupuestos
    active_budgets = get_active_budgets(target_month)
    spending = calculate_category_spending(target_month, account_id)
    
    # Solo resta la parte de presupuesto que aún no se ha ejecutado en gasto real.
    pending_budget_impact = 0.0
    for b in active_budgets:
        if b['account_id'] != account_id: continue
        cat_id = b['categoria_id']
        presupuesto = b['monto']
        real_spent = spending.get(cat_id, 0.0)

        if real_spent < presupuesto:
            pending_budget_impact += (presupuesto - real_spent)
            
    return real - fixed_pendientes - pending_budget_impact

def get_pending_loans_for_account(account_id: str, month: str = None) -> list:
    """Returns incoming pending loans for an account, optionally filtered by month."""
    transfers = _get_service("transfers").get_by_field("cuenta_destino", "==", account_id)
    pending_loans = [
        t for t in transfers
        if t.get('is_loan', False) and t.get('status', 'pending') == 'pending' and t.get('outstanding_amount', t.get('monto', 0.0)) > 0
    ]
    if month:
        pending_loans = [
            t for t in pending_loans
            if (t['fecha'].date() if isinstance(t['fecha'], datetime) else datetime.strptime(t['fecha'][:10], "%Y-%m-%d").date()).strftime("%Y-%m") == month
        ]
    return pending_loans

def get_month_summary(month: str) -> dict:
    """Returns summary for month view."""
    current_month = get_current_month()
    is_future_month = month > current_month

    # Ingreso total, Gastos fijos, Presupuestos, Gastos reales, Ingresos extra
    salaries = _get_service("salaries").get_all()
    ingreso_total = sum(calculate_salary_net(s['id'], month) for s in salaries if is_active_in_month(
            s['fecha_inicio'].date() if isinstance(s['fecha_inicio'], datetime) else datetime.strptime(s['fecha_inicio'][:10], "%Y-%m-%d").date(),
            s['fecha_fin'].date() if isinstance(s['fecha_fin'], datetime) else datetime.strptime(s['fecha_fin'][:10], "%Y-%m-%d").date() if s.get('fecha_fin') else None,
            month
        ))
        
    fixed_all = get_fixed_expenses_for_month(month)
    gastos_fijos_total = sum(fe['monto'] for fe in fixed_all)
    
    budgets = get_active_budgets(month)
    presupuestos_total = sum(b['monto'] for b in budgets)
    
    expenses = _get_service("expenses").get_all()
    gastos_reales = sum(e['monto'] for e in expenses if (e['fecha'].date() if isinstance(e['fecha'], datetime) else datetime.strptime(e['fecha'][:10], "%Y-%m-%d").date()).strftime("%Y-%m") == month)
    
    incomes = _get_service("incomes").get_all()
    ingresos_extra_base = sum(i['monto'] for i in incomes if (i['fecha'].date() if isinstance(i['fecha'], datetime) else datetime.strptime(i['fecha'][:10], "%Y-%m-%d").date()).strftime("%Y-%m") == month)
    
    # Add ALL pending loans for this month to extra incomes (global)
    transfers = _get_service("transfers").get_all()
    loans_this_month = sum(
        t.get('outstanding_amount', t.get('monto', 0.0)) for t in transfers 
        if t.get('is_loan', False) and t.get('status', 'pending') == 'pending' and 
        t.get('outstanding_amount', t.get('monto', 0.0)) > 0 and
        (t['fecha'].date() if isinstance(t['fecha'], datetime) else datetime.strptime(t['fecha'][:10], "%Y-%m-%d").date()).strftime("%Y-%m") == month
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
        if month_snapshot and month == current_month and month_snapshot.get("status") == "future_projection":
            month_snapshot = upsert_monthly_account_snapshot(month, main_id, {
                "is_main_account_for_month": True,
                "remaining_from_previous_month": float(month_snapshot.get("remaining_from_previous_month", 0.0)),
                "resultado_real_closed": float(month_snapshot.get("resultado_real_closed", 0.0)),
                "resultado_proyectado_frozen": float(month_snapshot.get("resultado_proyectado_frozen", 0.0)),
                "status": "open",
            })
        remaining_from_previous_month = float(month_snapshot.get("remaining_from_previous_month", 0.0)) if month_snapshot else 0.0

        main_salaries = sum(calculate_salary_net(s['id'], month) for s in salaries if s.get('account_id') == main_id and is_active_in_month(
            s['fecha_inicio'].date() if isinstance(s['fecha_inicio'], datetime) else datetime.strptime(s['fecha_inicio'][:10], "%Y-%m-%d").date(),
            s['fecha_fin'].date() if isinstance(s['fecha_fin'], datetime) else datetime.strptime(s['fecha_fin'][:10], "%Y-%m-%d").date() if s.get('fecha_fin') else None,
            month
        ))
        
        main_fixed = sum((fe.get('monto_pagado') if fe.get('monto_pagado') is not None else fe['monto']) for fe in fixed_all if fe.get('account_id') == main_id and fe['estado'] == 'pagado')
        main_expenses = sum(e['monto'] for e in expenses if e.get('account_id') == main_id and (e['fecha'].date() if isinstance(e['fecha'], datetime) else datetime.strptime(e['fecha'][:10], "%Y-%m-%d").date()).strftime("%Y-%m") == month)
        
        main_base_incomes = sum(i['monto'] for i in incomes if i.get('account_id') == main_id and (i['fecha'].date() if isinstance(i['fecha'], datetime) else datetime.strptime(i['fecha'][:10], "%Y-%m-%d").date()).strftime("%Y-%m") == month)
        main_loans = get_pending_loans_for_account(main_id, month)
        main_loans_total = sum(l.get('outstanding_amount', l.get('monto', 0.0)) for l in main_loans)
        
        main_extra_incomes = main_base_incomes + main_loans_total
        main_transfers_out = sum(
            t['monto'] for t in transfers
            if t.get('cuenta_origen') == main_id and
            (t['fecha'].date() if isinstance(t['fecha'], datetime) else datetime.strptime(t['fecha'][:10], "%Y-%m-%d").date()).strftime("%Y-%m") == month
        )
        main_transfers_in = sum(
            t['monto'] for t in transfers
            if t.get('cuenta_destino') == main_id and
            (t['fecha'].date() if isinstance(t['fecha'], datetime) else datetime.strptime(t['fecha'][:10], "%Y-%m-%d").date()).strftime("%Y-%m") == month
        )
        
        if month_snapshot and month_snapshot.get("status") == "closed":
            resultado_real = float(month_snapshot.get("resultado_real_closed", 0.0))
        else:
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
