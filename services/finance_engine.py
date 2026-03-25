from datetime import datetime
from dateutil.relativedelta import relativedelta
from utils.date_utils import is_active_in_month, get_current_month, parse_month
from services.firestore_service import FirestoreService

# Services for easy access
def _get_service(collection_name):
    return FirestoreService(collection_name)

MONTH_ROLLOVER_START = "2026-03"

def _calculate_month_resultado_real_for_main_account(month: str) -> tuple:
    """Returns (resultado_real, main_account_dict_or_none) for a specific month."""
    acc_srv = _get_service("accounts")
    accounts = acc_srv.get_all()
    main_acc = next((a for a in accounts if a.get('is_main', False)), None)

    if not main_acc:
        return 0.0, None

    main_id = main_acc['id']
    salaries = _get_service("salaries").get_by_field("account_id", "==", main_id)
    expenses = _get_service("expenses").get_by_field("account_id", "==", main_id)
    incomes = _get_service("incomes").get_by_field("account_id", "==", main_id)
    fixed_all = get_fixed_expenses_for_month(month)

    main_salaries = sum(
        calculate_salary_net(s['id'], month)
        for s in salaries
        if is_active_in_month(
            s['fecha_inicio'].date() if isinstance(s['fecha_inicio'], datetime) else datetime.strptime(s['fecha_inicio'][:10], "%Y-%m-%d").date(),
            s['fecha_fin'].date() if isinstance(s['fecha_fin'], datetime) else datetime.strptime(s['fecha_fin'][:10], "%Y-%m-%d").date() if s.get('fecha_fin') else None,
            month
        )
    )
    main_fixed = sum(
        (fe.get('monto_pagado') if fe.get('monto_pagado') is not None else fe['monto'])
        for fe in fixed_all
        if fe.get('account_id') == main_id and fe['estado'] == 'pagado'
    )
    main_expenses = sum(
        e['monto']
        for e in expenses
        if (e['fecha'].date() if isinstance(e['fecha'], datetime) else datetime.strptime(e['fecha'][:10], "%Y-%m-%d").date()).strftime("%Y-%m") == month
    )
    main_base_incomes = sum(
        i['monto']
        for i in incomes
        if (i['fecha'].date() if isinstance(i['fecha'], datetime) else datetime.strptime(i['fecha'][:10], "%Y-%m-%d").date()).strftime("%Y-%m") == month
    )
    main_loans_total = sum(
        l.get('outstanding_amount', l.get('monto', 0.0))
        for l in get_pending_loans_for_account(main_id, month)
    )

    return main_salaries + main_base_incomes + main_loans_total - main_expenses - main_fixed, main_acc

def _get_month_rollover_doc(month: str) -> dict:
    docs = _get_service("month_rollovers").get_by_field("month", "==", month)
    return docs[0] if docs else None

def _upsert_month_rollover_doc(month: str, data: dict) -> dict:
    rollover_srv = _get_service("month_rollovers")
    existing = _get_month_rollover_doc(month)
    payload = dict(data)
    payload["month"] = month
    if existing:
        rollover_srv.update(existing["id"], payload)
        return {**existing, **payload}
    doc_id = rollover_srv.add(payload)
    return {"id": doc_id, **payload}

def run_month_rollover_if_needed(today=None) -> dict:
    """Idempotently closes previous month and opens current month from 2026-03 onwards."""
    if today is None:
        today_date = datetime.now().date()
    elif isinstance(today, datetime):
        today_date = today.date()
    else:
        today_date = today

    current_month = today_date.strftime("%Y-%m")
    previous_month = (today_date.replace(day=1) - relativedelta(months=1)).strftime("%Y-%m")

    if current_month < MONTH_ROLLOVER_START:
        return {"status": "ignored", "current_month": current_month, "previous_month": previous_month}

    previous_closed_value = 0.0
    main_acc = None
    previous_doc = None

    if previous_month >= MONTH_ROLLOVER_START:
        previous_doc = _get_month_rollover_doc(previous_month)
        if previous_doc and previous_doc.get("resultado_real_closed") is not None:
            previous_closed_value = previous_doc.get("resultado_real_closed", 0.0)
            main_acc = {
                "id": previous_doc.get("main_account_id"),
                "nombre": previous_doc.get("main_account_name")
            } if previous_doc.get("main_account_id") else None
        else:
            previous_closed_value, main_acc = _calculate_month_resultado_real_for_main_account(previous_month)

    previous_updates = {}
    if previous_month >= MONTH_ROLLOVER_START:
        if not previous_doc or previous_doc.get("resultado_real_closed") is None:
            previous_updates["resultado_real_closed"] = previous_closed_value
            previous_updates["closed_at"] = datetime.now()
        if main_acc:
            if not previous_doc or not previous_doc.get("main_account_id"):
                previous_updates["main_account_id"] = main_acc.get("id")
            if not previous_doc or not previous_doc.get("main_account_name"):
                previous_updates["main_account_name"] = main_acc.get("nombre")
        if previous_updates:
            _upsert_month_rollover_doc(previous_month, previous_updates)

    current_doc = _get_month_rollover_doc(current_month)
    current_updates = {}
    if not current_doc or current_doc.get("remaining_from_previous_month") is None:
        current_updates["remaining_from_previous_month"] = previous_closed_value
    if not current_doc or not current_doc.get("rollover_source_month"):
        current_updates["rollover_source_month"] = previous_month
    if main_acc:
        if not current_doc or not current_doc.get("main_account_id"):
            current_updates["main_account_id"] = main_acc.get("id")
        if not current_doc or not current_doc.get("main_account_name"):
            current_updates["main_account_name"] = main_acc.get("nombre")
    if not current_doc or not current_doc.get("opened_at"):
        current_updates["opened_at"] = datetime.now()

    if current_updates:
        _upsert_month_rollover_doc(current_month, current_updates)

    return {"status": "ok", "current_month": current_month, "previous_month": previous_month}

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

def calculate_real_balance(account_id: str) -> float:
    """Calculated as: saldo_inicial + sueldos netos_pasados + ingresos_extra - gastos - transferencias_salientes + transferencias_entrantes"""
    account = _get_service("accounts").get_by_id(account_id)
    if not account: return 0.0
    
    balance = account.get('saldo_inicial', 0.0)
    current_m = get_current_month()
    
    # Add all past and current month salaries
    balance += _get_account_historical_salary_incomes(account_id, current_m)
    
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

def calculate_projected_balance(account_id: str) -> float:
    """Calcula el saldo proyectado del mes actual.

    El saldo real ya incluye los gastos reales registrados. Por eso aquí solo se resta:
    - gastos fijos impagados del mes actual, y
    - la parte pendiente de cada presupuesto activo (presupuesto - gasto_real, si es positiva).
    """
    real = calculate_real_balance(account_id)
    current_m = get_current_month()
    
    # Gastos fijos pendientes for current month
    fixed_this_month = get_fixed_expenses_for_month(current_m)
    fixed_pendientes = sum(fe['monto'] for fe in fixed_this_month if fe['account_id'] == account_id and fe['estado'] == 'impagado')
    
    # Presupuestos
    active_budgets = get_active_budgets(current_m)
    spending = calculate_category_spending(current_m, account_id)
    
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
    
    # Identify Main Account for "Resultado Real"
    acc_srv = _get_service("accounts")
    accounts = acc_srv.get_all()
    main_acc = next((a for a in accounts if a.get('is_main', False)), None)
    
    resultado_real_details = None
    if main_acc:
        main_id = main_acc['id']
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
        
        resultado_real = main_salaries + main_extra_incomes - main_expenses - main_fixed
        resultado_real_details = {
            "main_account_id": main_id,
            "main_account_name": main_acc.get('nombre', 'Main'),
            "pending_loans": get_pending_loans_for_account(main_id) # all pending loans for the main account, regardless of month
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
    
    return {
        "ingreso_total": ingreso_total,
        "gastos_fijos": gastos_fijos_total,
        "presupuestos": presupuestos_total,
        "gastos_reales": gastos_reales,
        "ingresos_extra": ingresos_extra_total,
        "resultado_real": resultado_real,
        "resultado_proyectado": resultado_proyectado,
        "resultado_real_details": resultado_real_details
    }
