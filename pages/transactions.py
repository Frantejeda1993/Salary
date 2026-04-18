import streamlit as st
from datetime import date, datetime
from services.firestore_service import FirestoreService, clear_firestore_read_caches
from models.expense import Expense
from models.income import Income
from models.fuel_expense import FuelExpense
from models.transfer import Transfer
from utils.money_utils import format_currency

st.title("💸 Transactions (Real)")
refresh_col, _ = st.columns([1, 5])
with refresh_col:
    if st.button("🔄 Refresh Data", use_container_width=True):
        clear_firestore_read_caches()
        st.rerun()

cat_srv = FirestoreService("categories")
acc_srv = FirestoreService("accounts")
exp_srv = FirestoreService("expenses")
inc_srv = FirestoreService("incomes")
trf_srv = FirestoreService("transfers")

accounts = acc_srv.get_all()
categories = cat_srv.get_all()


def build_account_options(account_items):
    return [
        {
            "label": f"{a.get('nombre', 'Unknown Account')} · {str(a.get('id', ''))[:6]}",
            "id": a.get('id'),
            "bank_id": a.get('bank_id'),
            "nombre": a.get('nombre', ''),
            "is_main": a.get('is_main', False)
        }
        for a in account_items
    ]

def parse_amount_input(raw_value):
    cleaned = (raw_value or "").strip().replace(",", ".")
    if not cleaned:
        return 0.0
    try:
        return float(cleaned)
    except ValueError:
        return None


def build_category_options(category_items):
    return [
        {
            "label": f"{c.get('nombre', 'Unknown Category')} · {str(c.get('id', ''))[:6]}",
            "id": c.get('id')
        }
        for c in category_items
    ]

if not accounts:
    st.warning("Please add an Account first.")
else:
    acc_options = build_account_options(accounts)
    cat_options = build_category_options(categories)
    main_acc_index = next((i for i, a in enumerate(acc_options) if a.get("is_main") or a.get("nombre") == "Main"), 0)
    
    tab1, tab2, tab3, tab4 = st.tabs(["Add Expense", "Add Extra Income", "Add Fuel Expense", "Add Loan"])
    acc_labels = [a['label'] for a in acc_options]
    cat_labels = [c['label'] for c in cat_options]
    
    with tab1:
        with st.form("add_exp_form", clear_on_submit=True):
            st.subheader("New Real Expense")
            col1, col2 = st.columns(2)
            with col1:
                nombre = st.text_input("Concept / Name")
                monto_raw = st.text_input("Amount", value="", placeholder="0", key="amount_expense")
                monto = parse_amount_input(monto_raw)
                account_label = st.selectbox("Account from", acc_labels, index=main_acc_index)
                selected_acc = next((a for a in acc_options if a['label'] == account_label), None)
            with col2:
                fecha = st.date_input("Date", value=date.today(), format="DD/MM/YYYY")
                categoria_label = st.selectbox("Category", cat_labels if cat_labels else ["None"])
                selected_cat = next((c for c in cat_options if c['label'] == categoria_label), None)
                es_propio = st.checkbox("Gasto Propio", value=False, help="Marca si este gasto pertenece a la cuenta seleccionada pero debería ser reembolsado desde la cuenta principal.")
                
            if st.form_submit_button("Save Expense"):
                if monto is None:
                    st.error("Please enter a valid amount.")
                elif not nombre or monto <= 0:
                    st.error("Please complete name and amount greater than zero.")
                elif not selected_acc:
                    st.error("Please select a valid account.")
                else:
                    new_exp = Expense(
                    nombre=nombre, fecha=fecha, monto=monto,
                    categoria_id=selected_cat['id'] if selected_cat else '',
                    bank_id=selected_acc['bank_id'], account_id=selected_acc['id'],
                    es_propio=es_propio
                )
                    exp_srv.add(new_exp.to_dict())
                    st.success("Expense logged.")
                    st.rerun()

    with tab2:
        with st.form("add_inc_form", clear_on_submit=True):
            st.subheader("New Extra Income")
            col1, col2 = st.columns(2)
            with col1:
                nombre_inc = st.text_input("Concept / Name (Income)")
                monto_inc_raw = st.text_input("Amount (Income)", value="", placeholder="0", key="amount_income")
                monto_inc = parse_amount_input(monto_inc_raw)
                account_inc_label = st.selectbox("Account to", acc_labels, key="acc_inc", index=main_acc_index)
                selected_acc_inc = next((a for a in acc_options if a['label'] == account_inc_label), None)
            with col2:
                fecha_inc = st.date_input("Date (Income)", value=date.today(), key="dt_inc", format="DD/MM/YYYY")
                cat_options_with_none = ["None"] + cat_labels
                categoria_inc = st.selectbox("Category (Optional)", cat_options_with_none, help="If related to a category, it reduces the spent amount.")
                
            if st.form_submit_button("Save Income"):
                if monto_inc is None:
                    st.error("Please enter a valid amount.")
                elif not nombre_inc or monto_inc <= 0:
                    st.error("Please complete name and amount greater than zero.")
                elif not selected_acc_inc:
                    st.error("Please select a valid account.")
                else:
                    cat_selected = next((c for c in cat_options if c['label'] == categoria_inc), None)
                    cat_val = '' if categoria_inc == "None" else (cat_selected['id'] if cat_selected else '')
                    new_inc = Income(
                    nombre=nombre_inc, fecha=fecha_inc, monto=monto_inc,
                    categoria_id=cat_val,
                    bank_id=selected_acc_inc['bank_id'], account_id=selected_acc_inc['id']
                )
                    inc_srv.add(new_inc.to_dict())
                    st.success("Extra Income logged.")
                    st.rerun()

    with tab3:
        with st.form("add_fuel_exp_form", clear_on_submit=True):
            st.subheader("New Fuel Expense")
            col1, col2 = st.columns(2)
            with col1:
                nombre_fuel = st.text_input("Concept / Name", value="Fuel")
                monto_fuel_raw = st.text_input("Total Amount Paid", value="", placeholder="0", key="mf")
                monto_fuel = parse_amount_input(monto_fuel_raw)
                km_done = st.number_input("Km Done", min_value=0.0, step=10.0)
                price_per_l = st.number_input("Price per L", min_value=0.0, step=0.1, format="%.3f")
            with col2:
                fecha_fuel = st.date_input("Date", value=date.today(), format="DD/MM/YYYY", key="df")
                account_fuel_label = st.selectbox("Account from", acc_labels, key="af", index=main_acc_index)
                selected_acc_fuel = next((a for a in acc_options if a['label'] == account_fuel_label), None)
                categoria_fuel_label = st.selectbox("Category", cat_labels if cat_labels else ["None"], key="cf")
                selected_cat_fuel = next((c for c in cat_options if c['label'] == categoria_fuel_label), None)
                es_propio_fuel = st.checkbox("Gasto Propio", value=False, key="propio_fuel", help="Marca si este gasto pertenece a la cuenta seleccionada pero debería ser reembolsado desde la cuenta principal.")

            if monto_fuel and monto_fuel > 0 and km_done > 0 and price_per_l > 0:
                cost_per_1km = monto_fuel / km_done
                cost_per_100km = cost_per_1km * 100
                st.info(f"💡 **Calculations**:\n- Cost per 1 km: {format_currency(cost_per_1km)}\n- Cost per 100 km: {format_currency(cost_per_100km)}")

            if st.form_submit_button("Save Fuel Expense"):
                if monto_fuel is None:
                    st.error("Please enter a valid amount.")
                elif not nombre_fuel or monto_fuel <= 0:
                    st.error("Please complete name and amount greater than zero.")
                elif not selected_acc_fuel:
                    st.error("Please select a valid account.")
                else:
                    new_fuel_exp = FuelExpense(
                    nombre=nombre_fuel, fecha=fecha_fuel, monto=monto_fuel,
                    categoria_id=selected_cat_fuel['id'] if selected_cat_fuel else '',
                    bank_id=selected_acc_fuel['bank_id'], account_id=selected_acc_fuel['id'],
                    km_done=km_done, price_per_l=price_per_l,
                    es_propio=es_propio_fuel
                )
                    exp_srv.add(new_fuel_exp.to_dict())
                    st.success("Fuel Expense logged.")
                    st.rerun()

    with tab4:
        with st.form("add_loan_form", clear_on_submit=True):
            st.subheader("New Loan (Prestamo)")
            col1, col2 = st.columns(2)
            with col1:
                origen_label = st.selectbox("From Account", acc_labels, key="loan_from")
                origen = next((a for a in acc_options if a['label'] == origen_label), None)
                monto_loan = st.number_input("Amount", min_value=0.0, step=10.0, key="loan_amount")
            with col2:
                destino_label = st.selectbox("To Account", acc_labels, key="loan_to", index=1 if len(acc_options) > 1 else 0)
                destino = next((a for a in acc_options if a['label'] == destino_label), None)
                fecha_loan = st.date_input("Date", value=date.today(), format="DD/MM/YYYY", key="loan_date")
                
            if st.form_submit_button("Save Loan"):
                if not origen or not destino:
                    st.error("Please select valid accounts.")
                elif origen['id'] == destino['id']:
                    st.error("Origin and Destination accounts must be different.")
                elif monto_loan <= 0:
                    st.error("Amount must be greater than zero.")
                else:
                    new_loan = Transfer(
                        fecha=fecha_loan,
                        cuenta_origen=origen['id'],
                        cuenta_destino=destino['id'],
                        monto=monto_loan,
                        is_loan=True,
                        status='pending',
                        outstanding_amount=monto_loan
                    )
                    trf_srv.add(new_loan.to_dict())
                    st.success("Loan recorded successfully.")
                    st.rerun()

@st.dialog("Edit Expense")
def edit_expense_dialog(exp, acc_op, cat_op):
    with st.form(f"edit_exp_form_{exp['id']}", clear_on_submit=False):
        st.subheader("Edit Real Expense")
        col1, col2 = st.columns(2)
        with col1:
            nombre = st.text_input("Concept / Name", value=exp.get("nombre", ""))
            monto = st.number_input("Amount", value=float(exp.get("monto", 0.0)), min_value=0.0, step=10.0)
            
            # Match account
            current_acc_id = exp.get("account_id")
            acc_labels = [a['label'] for a in acc_op]
            acc_index = next((i for i, a in enumerate(acc_op) if a['id'] == current_acc_id), 0)
            account_label = st.selectbox("Account from", acc_labels, index=acc_index)
            selected_acc = next((a for a in acc_op if a['label'] == account_label), None)
            
        with col2:
            fecha = st.date_input("Date", value=exp.get("fecha", date.today()), format="DD/MM/YYYY")
            
            # Match category
            cat_names = ["None"] + [c['label'] for c in cat_op]
            current_cat_id = exp.get("categoria_id")
            try:
                if current_cat_id:
                    current_cat_name = next(c['label'] for c in cat_op if c['id'] == current_cat_id)
                    cat_index = cat_names.index(current_cat_name)
                else:
                    cat_index = 0
            except StopIteration:
                cat_index = 0 if "None" in cat_names else -1
            
            categoria_nombre = st.selectbox("Category", cat_names, index=max(0, cat_index))
            es_propio = st.checkbox("Gasto Propio", value=exp.get("es_propio", False), help="Marca si este gasto pertenece a la cuenta seleccionada pero debería ser reembolsado desde la cuenta principal.")
            
        is_fuel = exp.get("fuel_expense", False)
        if is_fuel:
            st.subheader("Fuel Details")
            f_col1, f_col2 = st.columns(2)
            with f_col1:
                km_done = st.number_input("Km Done", value=float(exp.get("km_done", 0.0)), min_value=0.0, step=10.0)
            with f_col2:
                price_per_l = st.number_input("Price per L", value=float(exp.get("price_per_l", 0.0)), min_value=0.0, step=0.1, format="%.3f")
                
            if monto > 0 and km_done > 0 and price_per_l > 0:
                cost_per_1km = monto / km_done
                cost_per_100km = cost_per_1km * 100
                st.info(f"💡 **Calculations**:\n- Cost per 1 km: {format_currency(cost_per_1km)}\n- Cost per 100 km: {format_currency(cost_per_100km)}")

        if st.form_submit_button("Update Expense"):
            if nombre and monto > 0:
                if not selected_acc:
                    st.error("Please select a valid account.")
                    return
                update_payload = {
                    "nombre": nombre, "fecha": datetime.combine(fecha, datetime.min.time()) if fecha else None, "monto": monto,
                    "categoria_id": next((c['id'] for c in cat_op if c['label'] == categoria_nombre), ''),
                    "bank_id": selected_acc['bank_id'], "account_id": selected_acc['id'],
                    "es_propio": es_propio
                }
                
                if is_fuel:
                    update_payload["km_done"] = km_done
                    update_payload["price_per_l"] = price_per_l
                    
                exp_srv.update(exp["id"], update_payload)
                st.success("Expense updated.")
                st.rerun()

@st.dialog("Edit Income")
def edit_income_dialog(inc, acc_op, cat_op):
    with st.form(f"edit_inc_form_{inc['id']}", clear_on_submit=False):
        st.subheader("Edit Extra Income")
        col1, col2 = st.columns(2)
        with col1:
            nombre_inc = st.text_input("Concept / Name (Income)", value=inc.get("nombre", ""))
            monto_inc = st.number_input("Amount (Income)", value=float(inc.get("monto", 0.0)), min_value=0.0, step=10.0)
            
            current_acc_id = inc.get("account_id")
            acc_labels = [a['label'] for a in acc_op]
            acc_index = next((i for i, a in enumerate(acc_op) if a['id'] == current_acc_id), 0)
            account_inc_label = st.selectbox("Account to", acc_labels, index=acc_index)
            selected_acc = next((a for a in acc_op if a['label'] == account_inc_label), None)
            
        with col2:
            fecha_inc = st.date_input("Date (Income)", value=inc.get("fecha", date.today()), format="DD/MM/YYYY")
            cat_options_with_none = ["None"] + [c['label'] for c in cat_op]
            
            current_cat_id = inc.get("categoria_id")
            try:
                if current_cat_id:
                    current_cat_name = next(c['label'] for c in cat_op if c['id'] == current_cat_id)
                    cat_index = cat_options_with_none.index(current_cat_name)
                else:
                    cat_index = 0
            except StopIteration:
                cat_index = 0
                
            categoria_inc = st.selectbox("Category (Optional)", cat_options_with_none, index=cat_index, help="If related to a category, it reduces the spent amount.")
            
        if st.form_submit_button("Update Income"):
            if nombre_inc and monto_inc > 0:
                if not selected_acc:
                    st.error("Please select a valid account.")
                    return
                cat_val = '' if categoria_inc == "None" else next((c['id'] for c in cat_op if c['label'] == categoria_inc), '')
                inc_srv.update(inc["id"], {
                    "nombre": nombre_inc, "fecha": datetime.combine(fecha_inc, datetime.min.time()) if fecha_inc else None, "monto": monto_inc,
                    "categoria_id": cat_val,
                    "bank_id": selected_acc['bank_id'], "account_id": selected_acc['id']
                })
                st.success("Extra Income updated.")
                st.rerun()

st.divider()
st.subheader("Recent Transactions")
expenses = exp_srv.get_all()
incomes = inc_srv.get_all()

# Sort by id roughly
all_tx = []
for e in expenses: all_tx.append({**e, 'type': 'Expense'})
for i in incomes: all_tx.append({**i, 'type': 'Income'})

all_tx.sort(key=lambda x: str(x.get('fecha', '')), reverse=True)

# Filters
st.write("### Filters")
f_col1, f_col2, f_col3, f_col4 = st.columns(4)
with f_col1:
    date_filter = st.date_input("Date Range", value=None)
with f_col2:
    cat_filter = st.selectbox("Category", ["All"] + cat_labels)
with f_col3:
    acc_filter = st.selectbox("Account", ["All"] + acc_labels)
with f_col4:
    propio_filter = st.selectbox("Tipo", ["All", "Propio", "Normal"])

filtered_tx = []
for tx in all_tx:
    # Filter Date
    tx_date_str = str(tx.get('fecha', ''))[:10]
    if tx_date_str:
        try:
            tx_date = datetime.strptime(tx_date_str, "%Y-%m-%d").date()
            if isinstance(date_filter, tuple) and len(date_filter) == 2:
                if not (date_filter[0] <= tx_date <= date_filter[1]):
                    continue
        except:
            pass

    # Filter Category
    if cat_filter != "All":
        tx_cat_id = tx.get('categoria_id')
        selected_cat_filter = next((c for c in cat_options if c['label'] == cat_filter), None)
        if not tx_cat_id or not selected_cat_filter or tx_cat_id != selected_cat_filter['id']:
            continue
            
    # Filter Account
    if acc_filter != "All":
        tx_acc_id = tx.get('account_id')
        selected_acc_filter = next((a for a in acc_options if a['label'] == acc_filter), None)
        if not tx_acc_id or not selected_acc_filter or tx_acc_id != selected_acc_filter['id']:
            continue

    # Filter Propio
    if propio_filter == "Propio" and not tx.get('es_propio', False):
        continue
    if propio_filter == "Normal" and tx.get('es_propio', False):
        continue
            
    filtered_tx.append(tx)

st.write(f"Showing **{len(filtered_tx)}** matching transactions.")
st.write("")

# Header row
hc1, hc2, hc3, hc4, hc5, hc6 = st.columns([1, 2, 2, 1.5, 1, 1])
hc1.write("**Type**")
hc2.write("**Name & Date**")
hc3.write("**Account / Category**")
hc4.write("**Amount**")

# Display loop
cat_lookup = {c['id']: c['nombre'] for c in categories}
acc_lookup = {a['id']: a['nombre'] for a in accounts}

for tx in filtered_tx[:50]:  # Limit to 50
    c1, c2, c3, c4, c5, c6 = st.columns([1, 2, 2, 1.5, 1, 1])
    is_inc = tx['type'] == 'Income'
    color = "green" if is_inc else "red"
    
    is_fuel = tx.get('fuel_expense', False)
    is_propio = tx.get('es_propio', False)
    display_type = "Fuel Exp." if is_fuel else tx['type']
    propio_badge = " 👤" if is_propio else ""
    
    c1.markdown(f":{color}[{display_type}]{propio_badge}")
    fecha_str = str(tx.get('fecha'))[:10]
    c2.write(f"**{tx.get('nombre')}**\n\n{fecha_str}")
    
    acc_name_str = acc_lookup.get(tx.get('account_id'), 'Unknown')
    cat_name_str = cat_lookup.get(tx.get('categoria_id'), 'No Category')
    c3.write(f"🏦 {acc_name_str}\n\n🏷️ {cat_name_str}")
    
    amount_str = format_currency(tx.get('monto', 0.0))
    if is_fuel:
        km = tx.get('km_done', 0)
        pl = tx.get('price_per_l', 0)
        monto = tx.get('monto', 0)
        if km > 0 and pl > 0 and monto > 0:
            price_per_km = monto / km
            l_per_100 = (monto / km / pl) * 100
            extra_info = f"\n\n🚗 {format_currency(price_per_km)}/km | {l_per_100:.1f}L/100km"
        else:
            extra_info = "\n\n🚗 *sin datos*"
        c4.write(f"**{amount_str}**{extra_info}")
    else:
        c4.write(f"**{amount_str}**")
    
    if c5.button("Edit", key=f"edit_{tx.get('type')}_{tx['id']}"):
        if is_inc:
            edit_income_dialog(tx, acc_options, cat_options)
        else:
            edit_expense_dialog(tx, acc_options, cat_options)
            
    if c6.button("Delete", key=f"del_{tx.get('type')}_{tx['id']}"):
        if is_inc:
            inc_srv.delete(tx['id'])
        else:
            exp_srv.delete(tx['id'])
        st.rerun()

st.divider()
st.subheader("Pending Loans")

loans = trf_srv.get_by_field("is_loan", "==", True)
pending_loans = [l for l in loans if l.get('status') == 'pending' and l.get('outstanding_amount', l.get('monto', 0.0)) > 0]

if pending_loans:
    pending_loans.sort(key=lambda x: str(x.get('fecha', '')), reverse=True)
    
    lc1, lc2, lc3, lc4, lc5 = st.columns([1.5, 2, 2, 1.5, 1.5])
    lc1.write("**Date**")
    lc2.write("**From**")
    lc3.write("**To**")
    lc4.write("**Amount**")
    
    for pl in pending_loans:
        c1, c2, c3, c4, c5 = st.columns([1.5, 2, 2, 1.5, 1.5])
        fecha_str = str(pl.get('fecha'))[:10]
        c1.write(fecha_str)
        c2.write(acc_lookup.get(pl.get('cuenta_origen'), 'Unknown'))
        c3.write(acc_lookup.get(pl.get('cuenta_destino'), 'Unknown'))
        outstanding_amount = float(pl.get('outstanding_amount', pl.get('monto', 0.0)))
        c4.write(f"{format_currency(pl.get('monto', 0.0))} (Pending: {format_currency(outstanding_amount)})")

        repay_key = f"repay_amount_{pl['id']}"
        repay_amount = c5.number_input(
            "Pay",
            min_value=0.0,
            max_value=outstanding_amount,
            value=outstanding_amount,
            step=10.0,
            key=repay_key
        )

        if c5.button("Repay", key=f"pay_loan_{pl['id']}"):
            if repay_amount <= 0:
                st.error("Repayment amount must be greater than zero.")
            else:
                new_outstanding = max(outstanding_amount - repay_amount, 0.0)
                new_status = 'paid' if new_outstanding == 0 else 'pending'
                trf_srv.update(pl['id'], {
                    "outstanding_amount": new_outstanding,
                    "status": new_status
                })

                repayment = Transfer(
                    fecha=date.today(),
                    cuenta_origen=pl['cuenta_destino'],
                    cuenta_destino=pl['cuenta_origen'],
                    monto=repay_amount,
                    is_loan=False,
                    status='paid'
                )
                trf_srv.add(repayment.to_dict())
                st.success(f"Repayment recorded. Pending amount: {format_currency(new_outstanding)}")
                st.rerun()
else:
    st.info("No pending loans.")
