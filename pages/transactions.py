import streamlit as st
from datetime import date, datetime
from services.firestore_service import FirestoreService
from models.expense import Expense
from models.income import Income
from models.fuel_expense import FuelExpense
from models.transfer import Transfer
from utils.money_utils import format_currency

st.title("💸 Transactions (Real)")

cat_srv = FirestoreService("categories")
acc_srv = FirestoreService("accounts")
exp_srv = FirestoreService("expenses")
inc_srv = FirestoreService("incomes")
trf_srv = FirestoreService("transfers")

accounts = acc_srv.get_all()
categories = cat_srv.get_all()

if not accounts:
    st.warning("Please add an Account first.")
else:
    acc_options = {a['nombre']: a for a in accounts}
    cat_options = {c['nombre']: c['id'] for c in categories}
    
    tab1, tab2, tab3, tab4 = st.tabs(["Add Expense", "Add Extra Income", "Add Fuel Expense", "Add Loan"])
    
    with tab1:
        with st.form("add_exp_form", clear_on_submit=True):
            st.subheader("New Real Expense")
            col1, col2 = st.columns(2)
            with col1:
                nombre = st.text_input("Concept / Name")
                monto = st.number_input("Amount", min_value=0.0, step=10.0)
                account_nombre = st.selectbox("Account from", list(acc_options.keys()))
            with col2:
                fecha = st.date_input("Date", value=date.today(), format="DD/MM/YYYY")
                categoria_nombre = st.selectbox("Category", list(cat_options.keys()) if cat_options else ["None"])
                
            if st.form_submit_button("Save Expense") and nombre and monto > 0:
                selected_acc = acc_options[account_nombre]
                new_exp = Expense(
                    nombre=nombre, fecha=fecha, monto=monto,
                    categoria_id=cat_options.get(categoria_nombre, ''),
                    bank_id=selected_acc['bank_id'], account_id=selected_acc['id']
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
                monto_inc = st.number_input("Amount (Income)", min_value=0.0, step=10.0)
                account_inc = st.selectbox("Account to", list(acc_options.keys()), key="acc_inc")
            with col2:
                fecha_inc = st.date_input("Date (Income)", value=date.today(), key="dt_inc", format="DD/MM/YYYY")
                cat_options_with_none = ["None"] + list(cat_options.keys())
                categoria_inc = st.selectbox("Category (Optional)", cat_options_with_none, help="If related to a category, it reduces the spent amount.")
                
            if st.form_submit_button("Save Income") and nombre_inc and monto_inc > 0:
                selected_acc = acc_options[account_inc]
                cat_val = '' if categoria_inc == "None" else cat_options[categoria_inc]
                new_inc = Income(
                    nombre=nombre_inc, fecha=fecha_inc, monto=monto_inc,
                    categoria_id=cat_val,
                    bank_id=selected_acc['bank_id'], account_id=selected_acc['id']
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
                monto_fuel = st.number_input("Total Amount Paid", min_value=0.0, step=10.0, key="mf")
                km_done = st.number_input("Km Done", min_value=0.0, step=10.0)
                price_per_l = st.number_input("Price per L", min_value=0.0, step=0.1, format="%.3f")
            with col2:
                fecha_fuel = st.date_input("Date", value=date.today(), format="DD/MM/YYYY", key="df")
                account_fuel = st.selectbox("Account from", list(acc_options.keys()), key="af")
                categoria_fuel = st.selectbox("Category", list(cat_options.keys()) if cat_options else ["None"], key="cf")

            if monto_fuel > 0 and km_done > 0 and price_per_l > 0:
                cost_per_1km = monto_fuel / km_done
                cost_per_100km = cost_per_1km * 100
                st.info(f"💡 **Calculations**:\n- Cost per 1 km: {format_currency(cost_per_1km)}\n- Cost per 100 km: {format_currency(cost_per_100km)}")

            if st.form_submit_button("Save Fuel Expense") and nombre_fuel and monto_fuel > 0:
                selected_acc = acc_options[account_fuel]
                new_fuel_exp = FuelExpense(
                    nombre=nombre_fuel, fecha=fecha_fuel, monto=monto_fuel,
                    categoria_id=cat_options.get(categoria_fuel, ''),
                    bank_id=selected_acc['bank_id'], account_id=selected_acc['id'],
                    km_done=km_done, price_per_l=price_per_l
                )
                exp_srv.add(new_fuel_exp.to_dict())
                st.success("Fuel Expense logged.")
                st.rerun()

    with tab4:
        with st.form("add_loan_form", clear_on_submit=True):
            st.subheader("New Loan (Prestamo)")
            col1, col2 = st.columns(2)
            with col1:
                origen_name = st.selectbox("From Account", list(acc_options.keys()), key="loan_from")
                monto_loan = st.number_input("Amount", min_value=0.0, step=10.0, key="loan_amount")
            with col2:
                destino_name = st.selectbox("To Account", list(acc_options.keys()), key="loan_to", index=1 if len(acc_options) > 1 else 0)
                fecha_loan = st.date_input("Date", value=date.today(), format="DD/MM/YYYY", key="loan_date")
                
            if st.form_submit_button("Save Loan"):
                if origen_name == destino_name:
                    st.error("Origin and Destination accounts must be different.")
                elif monto_loan <= 0:
                    st.error("Amount must be greater than zero.")
                else:
                    new_loan = Transfer(
                        fecha=fecha_loan,
                        cuenta_origen=acc_options[origen_name]['id'],
                        cuenta_destino=acc_options[destino_name]['id'],
                        monto=monto_loan,
                        is_loan=True,
                        status='pending'
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
            acc_names = list(acc_op.keys())
            try:
                current_acc_name = next(name for name, acc in acc_op.items() if acc['id'] == current_acc_id)
                acc_index = acc_names.index(current_acc_name)
            except StopIteration:
                acc_index = 0
            account_nombre = st.selectbox("Account from", acc_names, index=acc_index)
            
        with col2:
            fecha = st.date_input("Date", value=exp.get("fecha", date.today()), format="DD/MM/YYYY")
            
            # Match category
            cat_names = ["None"] if not cat_op else list(cat_op.keys())
            current_cat_id = exp.get("categoria_id")
            try:
                if current_cat_id:
                    current_cat_name = next(name for name, cid in cat_op.items() if cid == current_cat_id)
                    cat_index = cat_names.index(current_cat_name)
                else:
                    cat_index = 0
            except StopIteration:
                cat_index = 0 if "None" in cat_names else -1
            
            categoria_nombre = st.selectbox("Category", cat_names, index=max(0, cat_index))
            
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
                selected_acc = acc_op[account_nombre]
                update_payload = {
                    "nombre": nombre, "fecha": datetime.combine(fecha, datetime.min.time()) if fecha else None, "monto": monto,
                    "categoria_id": cat_op.get(categoria_nombre, ''),
                    "bank_id": selected_acc['bank_id'], "account_id": selected_acc['id']
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
            acc_names = list(acc_op.keys())
            try:
                current_acc_name = next(name for name, acc in acc_op.items() if acc['id'] == current_acc_id)
                acc_index = acc_names.index(current_acc_name)
            except StopIteration:
                acc_index = 0
            account_inc = st.selectbox("Account to", acc_names, index=acc_index)
            
        with col2:
            fecha_inc = st.date_input("Date (Income)", value=inc.get("fecha", date.today()), format="DD/MM/YYYY")
            cat_options_with_none = ["None"] + list(cat_op.keys())
            
            current_cat_id = inc.get("categoria_id")
            try:
                if current_cat_id:
                    current_cat_name = next(name for name, cid in cat_op.items() if cid == current_cat_id)
                    cat_index = cat_options_with_none.index(current_cat_name)
                else:
                    cat_index = 0
            except StopIteration:
                cat_index = 0
                
            categoria_inc = st.selectbox("Category (Optional)", cat_options_with_none, index=cat_index, help="If related to a category, it reduces the spent amount.")
            
        if st.form_submit_button("Update Income"):
            if nombre_inc and monto_inc > 0:
                selected_acc = acc_op[account_inc]
                cat_val = '' if categoria_inc == "None" else cat_op[categoria_inc]
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
f_col1, f_col2, f_col3 = st.columns(3)
with f_col1:
    date_filter = st.date_input("Date Range", value=None)
with f_col2:
    cat_filter = st.selectbox("Category", ["All"] + list(cat_options.keys()))
with f_col3:
    acc_filter = st.selectbox("Account", ["All"] + list(acc_options.keys()))

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
        if not tx_cat_id or tx_cat_id != cat_options[cat_filter]:
            continue
            
    # Filter Account
    if acc_filter != "All":
        tx_acc_id = tx.get('account_id')
        if not tx_acc_id or tx_acc_id != acc_options[acc_filter]['id']:
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
    display_type = "Fuel Exp." if is_fuel else tx['type']
    
    c1.markdown(f":{color}[{display_type}]")
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
        extra_info = ""
        if km > 0 and pl > 0:
            price_per_km = monto / km
            l_per_100 = (monto / km / pl) * 100
            extra_info = f"\n\n🚗 {format_currency(price_per_km)}/km | {l_per_100:.1f}L/100km"
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
pending_loans = [l for l in loans if l.get('status') == 'pending']

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
        c4.write(format_currency(pl.get('monto', 0.0)))
        
        if c5.button("Mark Paid", key=f"pay_loan_{pl['id']}"):
            # Update status to paid
            trf_srv.update(pl['id'], {"status": "paid"})
            
            # Create reverse transfer (repayment)
            repayment = Transfer(
                fecha=date.today(),
                cuenta_origen=pl['cuenta_destino'], # Reverse direction
                cuenta_destino=pl['cuenta_origen'],
                monto=pl['monto'],
                is_loan=False, # It's just a transfer back
                status='paid'
            )
            trf_srv.add(repayment.to_dict())
            st.success("Loan marked as paid and funds returned.")
            st.rerun()
else:
    st.info("No pending loans.")

