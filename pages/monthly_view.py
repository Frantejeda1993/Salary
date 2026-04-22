import streamlit as st
import pandas as pd
from datetime import datetime
from services import finance_engine
from utils.date_utils import get_current_month, get_month_options
from services.firestore_service import FirestoreService, clear_firestore_read_caches
from models.transfer import Transfer
from utils.money_utils import format_currency


# Backward-compatible function bindings.
get_month_summary = finance_engine.get_month_summary
calculate_real_balance = finance_engine.calculate_real_balance
calculate_projected_balance = finance_engine.calculate_projected_balance
get_active_budgets = finance_engine.get_active_budgets
calculate_category_spending = finance_engine.calculate_category_spending
calculate_raw_category_expenses = getattr(finance_engine, "_calculate_raw_category_expenses", None)
get_fixed_expenses_for_month = finance_engine.get_fixed_expenses_for_month
get_propio_expenses_by_account = getattr(finance_engine, "get_propio_expenses_by_account", None)
calculate_month_real_result = getattr(
    finance_engine,
    "calculate_month_real_result",
    getattr(finance_engine, "calculate_real_result", None),
)
calculate_month_projected_result = getattr(
    finance_engine,
    "calculate_month_projected_result",
    getattr(finance_engine, "calculate_projected_result", None),
)

if calculate_month_real_result is None or calculate_month_projected_result is None:
    raise ImportError(
        "Missing month result calculators in services.finance_engine. "
        "Expected calculate_month_real_result and calculate_month_projected_result "
        "(or legacy calculate_real_result / calculate_projected_result)."
    )

st.title("📅 Monthly View Breakdown")
refresh_col, _ = st.columns([1, 5])
with refresh_col:
    if st.button("🔄 Refresh Data", use_container_width=True):
        clear_firestore_read_caches()
        st.rerun()

acc_srv = FirestoreService("accounts")
bank_srv = FirestoreService("banks")
trf_srv = FirestoreService("transfers")
accounts = acc_srv.get_all()
banks = bank_srv.get_all()
bank_lookup = {b['id']: b['nombre'] for b in banks}

months = get_month_options()
if 'sel_month' not in st.session_state:
    st.session_state['sel_month'] = get_current_month()

selected_month = st.selectbox(
    "Select Month",
    months,
    index=months.index(st.session_state['sel_month']) if st.session_state['sel_month'] in months else 0,
)
st.session_state['sel_month'] = selected_month

st.divider()
st.subheader(f"Summary for {selected_month}")

summary = get_month_summary(selected_month)
if not summary.get('resultado_real_details'):
    st.warning(
        "⚠️ No hay cuenta principal activa. "
        "Ve a **Configuración → Accounts** y marca una cuenta como principal."
    )

col1, col2, col3, col4 = st.columns(4)
col1.metric("Ingreso Total (Salaries)", format_currency(summary['ingreso_total']))
col2.metric("Ingresos Extra", format_currency(summary['ingresos_extra']))
col3.metric("Gastos Reales", format_currency(summary['gastos_reales']))
col4.metric("Gastos Fijos", format_currency(summary['gastos_fijos']))

st.metric("Total Presupuestado", format_currency(summary['presupuestos']))
st.metric(
    "Remaining from Previous Month",
    format_currency(summary.get('remaining_from_previous_month', 0.0)),
)

st.divider()
rc1, rc2 = st.columns(2)

res_details = summary.get('resultado_real_details')

with rc1:
    if res_details:
        main_id = res_details['main_account_id']
        main_name = res_details['main_account_name']
        main_real = summary["resultado_real"]
        st.info(f"### Resultado Real ({main_name})\n# {format_currency(main_real)}")
        pending_loans = res_details.get('pending_loans', [])
        if pending_loans:
            acc_lookup = {a["id"]: a.get("nombre", "Unknown Account") for a in accounts}
            for loan in pending_loans:
                acc_origen_name = acc_lookup.get(loan.get("cuenta_origen"), "Unknown Account")
                loan_fecha = str(loan.get('fecha'))[:10]
                pending_amount = loan.get('outstanding_amount', loan.get('monto', 0.0))
                st.markdown(
                    f"<small style='color:#ff4b4b; font-weight:bold;'>"
                    f"- Pending Loan: {format_currency(pending_amount)} from {acc_origen_name} (since {loan_fecha})"
                    f"</small>",
                    unsafe_allow_html=True,
                )
    else:
        st.info(f"### Resultado Real\n# {format_currency(summary['resultado_real'])}")

with rc2:
    if res_details:
        main_name = res_details['main_account_name']
        main_proj = summary["resultado_proyectado"]
        st.success(f"### Resultado Proyectado ({main_name})\n# {format_currency(main_proj)}")
    else:
        st.success(f"### Resultado Proyectado\n# {format_currency(summary['resultado_proyectado'])}")

# ---------------------------------------------------------------------------
# Gastos Propios de otras cuentas
# ---------------------------------------------------------------------------
if res_details:
    main_id = res_details['main_account_id']
    main_name = res_details['main_account_name']
    propio_by_account = get_propio_expenses_by_account(selected_month, main_id) if get_propio_expenses_by_account else {}

    if propio_by_account:
        st.divider()
        st.subheader("👤 Gastos Propios de otras cuentas")

        acc_lookup_full = {a['id']: a for a in accounts}
        total_propio = sum(propio_by_account.values())

        # Summary line: total + per-account if multiple
        if len(propio_by_account) == 1:
            only_acc_id, only_amt = next(iter(propio_by_account.items()))
            only_acc = acc_lookup_full.get(only_acc_id, {})
            only_acc_name = f"{bank_lookup.get(only_acc.get('bank_id'), '')} - {only_acc.get('nombre', 'Cuenta')}"
            st.write(f"Total gastos propios pendientes de reembolso: **{format_currency(total_propio)}** ({only_acc_name})")
        else:
            breakdown = []
            for acc_id, amt in propio_by_account.items():
                acc = acc_lookup_full.get(acc_id, {})
                acc_name = f"{bank_lookup.get(acc.get('bank_id'), '')} - {acc.get('nombre', 'Cuenta')}"
                breakdown.append(f"{acc_name}: {format_currency(amt)}")
            breakdown_str = " | ".join(breakdown)
            st.write(f"Total gastos propios pendientes de reembolso: **{format_currency(total_propio)}** ({breakdown_str})")

        st.caption(f"Transferir desde **{main_name}** hacia cada cuenta:")

        for acc_id, amt in propio_by_account.items():
            acc = acc_lookup_full.get(acc_id, {})
            acc_name = f"{bank_lookup.get(acc.get('bank_id'), '')} - {acc.get('nombre', 'Cuenta')}"

            col_name, col_amt, col_btn = st.columns([3, 2, 2])
            col_name.write(f"**{acc_name}**")
            col_amt.write(format_currency(amt))

            btn_key = f"transfer_propio_{acc_id}_{selected_month}"
            if col_btn.button(f"💸 Transferir {format_currency(amt)}", key=btn_key, use_container_width=True):
                transfer_date = datetime.strptime(f"{selected_month}-01", "%Y-%m-%d").date()
                new_trf = Transfer(
                    fecha=transfer_date,
                    cuenta_origen=main_id,
                    cuenta_destino=acc_id,
                    monto=amt,
                    is_loan=False,
                    status='paid',
                    descripcion="Transferencia automatica gastos",
                )
                trf_srv.add(new_trf.to_dict())
                clear_firestore_read_caches()
                st.success(f"Transferencia de {format_currency(amt)} registrada hacia {acc_name}.")
                st.rerun()

st.divider()
st.subheader("Budget Usage Breakdown")

active_budgets = get_active_budgets(selected_month)
if active_budgets:
    cat_srv = FirestoreService("categories")
    categories = {c['id']: c['nombre'] for c in cat_srv.get_all()}

    remaining = summary.get('remaining_from_previous_month', 0.0)
    main_id = res_details['main_account_id'] if res_details else None

    account_budget_details = {}
    for a in accounts:
        r = remaining if (main_id and a['id'] == main_id) else 0.0
        proj_result = calculate_month_projected_result(
            a['id'], selected_month, remaining_from_previous_month=r
        )
        account_budget_details[a['id']] = {
            bd['categoria_id']: {
                'available': bd['available'],
                'absorbed': bd.get('absorbed', 0.0),
            }
            for bd in proj_result['budget_details']
        }

    for b in active_budgets:
        cat_name = categories.get(b.get('categoria_id'), 'Unknown Category')
        acc = acc_srv.get_by_id(b.get('account_id')) if b.get('account_id') else None
        if acc:
            acc_name = f"{bank_lookup.get(acc.get('bank_id'), 'Banco desconocido')} - {acc.get('nombre', 'Cuenta')}"
        else:
            acc_name = "Cuenta eliminada" if b.get('account_id') else ''

        limit = b.get('monto', 0.0)
        # Budget projection/absorption logic uses RAW (non-netted) expenses.
        # Keep "Used" aligned with projected internals so:
        #   limit - used - absorbed - available = 0
        if calculate_raw_category_expenses:
            account_spending = calculate_raw_category_expenses(selected_month, b.get('account_id'))
        else:
            account_spending = calculate_category_spending(selected_month, b.get('account_id'))
        used = account_spending.get(b.get('categoria_id'), 0.0)

        account_id = b.get('account_id')
        cat_id = b.get('categoria_id')
        detail = account_budget_details.get(account_id, {}).get(cat_id, {})
        available = detail.get('available', limit - used)
        absorbed = detail.get('absorbed', 0.0)
        true_available = available

        st.write(f"**{cat_name}** {f'({acc_name})' if acc_name else ''}")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Limit", format_currency(limit))
        c2.metric("Used", format_currency(used))
        if absorbed > 0:
            c3.metric("Absorbed", format_currency(absorbed), delta=f"-{format_currency(absorbed)}", delta_color="inverse")
        if true_available < 0:
            c4.metric("Available", format_currency(true_available), delta=format_currency(true_available), delta_color="inverse")
        else:
            c4.metric("Available", format_currency(true_available), delta=format_currency(true_available), delta_color="normal")

        # Stacked visual bar
        if limit > 0:
            pct_used = min(used / limit, 1.0) * 100
            pct_absorbed = min(absorbed / limit, max(0, 1.0 - pct_used / 100)) * 100
            pct_free = max(100 - pct_used - pct_absorbed, 0)

            st.markdown(
                f"""
                <div style="width:100%;height:18px;border-radius:6px;overflow:hidden;display:flex;background:#3a3a3a;margin-bottom:4px;">
                    <div style="width:{pct_used:.2f}%;background:#ff4b4b;" title="Used"></div>
                    <div style="width:{pct_absorbed:.2f}%;background:#ff8c00;" title="Absorbed by deficit"></div>
                    <div style="width:{pct_free:.2f}%;background:#21c354;" title="Available"></div>
                </div>
                <small style="color:#aaa;">🔴 Used &nbsp;&nbsp; 🟠 Covering deficit &nbsp;&nbsp; 🟢 Available</small>
                """,
                unsafe_allow_html=True,
            )
        st.write("")
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
            "Expense": fe.get('nombre', 'Unnamed'),
            "Status": estado_badge,
            "Amount": format_currency(amount),
            "Debit Account": debit_account,
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
    bank_groups: dict = {}
    for a in accounts:
        bank_name = bank_lookup.get(a.get('bank_id'), 'Unknown')
        bank_groups.setdefault(bank_name, []).append(a)

    acc_data = []
    for bank_name, bank_accounts in bank_groups.items():
        subtotal_real = 0.0
        subtotal_proj = 0.0

        for a in bank_accounts:
            real_bal = calculate_real_balance(a['id'], selected_month)
            proj_bal = calculate_projected_balance(a['id'], selected_month)['resultado']
            subtotal_real += real_bal
            subtotal_proj += proj_bal

            acc_data.append({
                "Banco": bank_name,
                "Cuenta": a.get('nombre'),
                "Saldo Real (Current)": format_currency(real_bal),
                "Saldo Proyectado": format_currency(proj_bal),
            })

        acc_data.append({
            "Banco": f"TOTAL {bank_name}",
            "Cuenta": "---",
            "Saldo Real (Current)": format_currency(subtotal_real),
            "Saldo Proyectado": format_currency(subtotal_proj),
        })

    df = pd.DataFrame(acc_data)

    def highlight_subtotal(row):
        return [
            'background-color: rgba(255,255,255,0.1); font-weight: bold;' if 'TOTAL' in row['Banco'] else ''
            for _ in row
        ]

    st.dataframe(df.style.apply(highlight_subtotal, axis=1), use_container_width=True, hide_index=True)
else:
    st.info("No accounts to display.")
