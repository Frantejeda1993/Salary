import streamlit as st
import pandas as pd
from services.finance_engine import get_month_summary, calculate_real_balance, calculate_projected_balance, get_active_budgets, calculate_category_spending, get_fixed_expenses_for_month
from utils.date_utils import get_current_month, get_month_options
from services.firestore_service import FirestoreService
from utils.money_utils import format_currency

st.title("📅 Monthly View Breakdown")

acc_srv = FirestoreService("accounts")
bank_srv = FirestoreService("banks")
accounts = acc_srv.get_all()
banks = bank_srv.get_all()
bank_lookup = {b['id']: b['nombre'] for b in banks}

months = get_month_options()
if 'sel_month' not in st.session_state:
    st.session_state['sel_month'] = get_current_month()

selected_month = st.selectbox("Select Month", months, index=months.index(st.session_state['sel_month']) if st.session_state['sel_month'] in months else 0)
st.session_state['sel_month'] = selected_month

st.divider()
st.subheader(f"Summary for {selected_month}")

summary = get_month_summary(selected_month)

col1, col2, col3, col4 = st.columns(4)
col1.metric("Ingreso Total (Salaries)", format_currency(summary['ingreso_total']))
col2.metric("Ingresos Extra", format_currency(summary['ingresos_extra']))
col3.metric("Gastos Reales", format_currency(summary['gastos_reales']))
col4.metric("Gastos Fijos", format_currency(summary['gastos_fijos']))

st.metric("Total Presupuestado", format_currency(summary['presupuestos']))

st.divider()
rc1, rc2 = st.columns(2)
with rc1:
    res_details = summary.get('resultado_real_details')
    if res_details:
        st.info(f"### Resultado Real ({res_details['main_account_name']})\n# {format_currency(summary['resultado_real'])}")
        pending_loans = res_details.get('pending_loans', [])
        if pending_loans:
            for l in pending_loans:
                acc_origen = acc_srv.get_by_id(l['cuenta_origen'])
                acc_origen_name = acc_origen.get('nombre', 'Unknown Account') if acc_origen else 'Unknown Account'
                loan_fecha = str(l.get('fecha'))[:10]
                pending_amount = l.get('outstanding_amount', l.get('monto', 0.0))
                st.markdown(f"<small style='color:#ff4b4b; font-weight:bold;'>- Pending Loan: {format_currency(pending_amount)} from {acc_origen_name} (since {loan_fecha})</small>", unsafe_allow_html=True)
    else:
        st.info(f"### Resultado Real\n# {format_currency(summary['resultado_real'])}")
with rc2:
    if res_details:
        st.success(f"### Resultado Proyectado ({res_details['main_account_name']})\n# {format_currency(summary['resultado_proyectado'])}")
    else:
        st.success(f"### Resultado Proyectado\n# {format_currency(summary['resultado_proyectado'])}")

st.divider()
st.subheader("Budget Usage Breakdown")

active_budgets = get_active_budgets(selected_month)
if active_budgets:
    spending = calculate_category_spending(selected_month)
    cat_srv = FirestoreService("categories")
    categories = {c['id']: c['nombre'] for c in cat_srv.get_all()}
    
    for b in active_budgets:
        cat_name = categories.get(b.get('categoria_id'), 'Unknown Category')
        acc = acc_srv.get_by_id(b.get('account_id')) if b.get('account_id') else None
        if acc:
            acc_name = f"{bank_lookup.get(acc.get('bank_id'), 'Banco desconocido')} - {acc.get('nombre', 'Cuenta')}"
        else:
            acc_name = "Cuenta eliminada" if b.get('account_id') else ''
        
        limit = b.get('monto', 0.0)
        used = spending.get(b.get('categoria_id'), 0.0)
        available = limit - used
        
        pct_used = min(used / limit if limit > 0 else 0, 1.0)
        
        st.write(f"**{cat_name}** {f'({acc_name})' if acc_name else ''}")
        c1, c2, c3 = st.columns(3)
        c1.metric("Limit", format_currency(limit))
        c2.metric("Used", format_currency(used))
        
        # Color the available depending on if it's negative or positive
        if available < 0:
            c3.metric("Available", format_currency(available), delta=format_currency(available), delta_color="inverse")
        else:
            c3.metric("Available", format_currency(available), delta=format_currency(available), delta_color="normal")
            
        st.progress(pct_used)
        st.write("") # spacing
else:
    st.info("No active budgets for this month.")

st.divider()
st.subheader("Fixed Expenses Status")

fixed_expenses = get_fixed_expenses_for_month(selected_month)
if fixed_expenses:
    account_lookup = {a['id']: a for a in accounts}
    fixed_rows = []
    for fe in fixed_expenses:
        account = account_lookup.get(fe.get('account_id'))
        if account:
            bank_name = bank_lookup.get(account.get('bank_id'), 'Unknown Bank')
            account_name = account.get('nombre', 'Unknown Account')
            debit_account = f"{bank_name} - {account_name}"
        else:
            debit_account = "Deleted account"

        estado = fe.get('estado', 'impagado')
        estado_badge = "🟢 Paid" if estado == 'pagado' else "🟠 Pending"
        amount = fe.get('monto_pagado') if fe.get('monto_pagado') is not None else fe.get('monto', 0.0)

        fixed_rows.append({
            "Expense": fe.get('nombre', 'Unnamed fixed expense'),
            "Status": estado_badge,
            "Amount": format_currency(amount),
            "Debit Account": debit_account
        })

    st.dataframe(pd.DataFrame(fixed_rows), use_container_width=True, hide_index=True)

    paid_count = sum(1 for fe in fixed_expenses if fe.get('estado') == 'pagado')
    pending_count = len(fixed_expenses) - paid_count
    c1, c2 = st.columns(2)
    c1.metric("Paid", paid_count)
    c2.metric("Pending", pending_count)
else:
    st.info("No active fixed expenses for this month.")

st.divider()
st.subheader("Balances per Account")

if accounts:
    bank_groups = {}
    for a in accounts:
        bank_name = bank_lookup.get(a.get('bank_id'), 'Unknown')
        if bank_name not in bank_groups:
            bank_groups[bank_name] = []
        bank_groups[bank_name].append(a)

    acc_data = []
    for bank_name, bank_accounts in bank_groups.items():
        subtotal_real = 0.0
        subtotal_proj = 0.0
        
        for a in bank_accounts:
            acc_name = a.get('nombre')
            real_bal = calculate_real_balance(a['id'])
            proj_bal = calculate_projected_balance(a['id'])
            
            subtotal_real += real_bal
            subtotal_proj += proj_bal
            
            acc_data.append({
                "Banco": bank_name,
                "Cuenta": acc_name,
                "Saldo Real (Current)": format_currency(real_bal),
                "Saldo Proyectado": format_currency(proj_bal)
            })
            
        acc_data.append({
            "Banco": f"TOTAL {bank_name}",
            "Cuenta": "---",
            "Saldo Real (Current)": format_currency(subtotal_real),
            "Saldo Proyectado": format_currency(subtotal_proj)
        })
        
    df = pd.DataFrame(acc_data)
    
    def highlight_subtotal(row):
        return ['background-color: rgba(255, 255, 255, 0.1); font-weight: bold;' if 'TOTAL' in row['Banco'] else '' for _ in row]

    st.dataframe(df.style.apply(highlight_subtotal, axis=1), use_container_width=True, hide_index=True)
else:
    st.info("No accounts to display.")
