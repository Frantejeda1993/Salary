import streamlit as st
from datetime import date, datetime
from services.firestore_service import FirestoreService
from services.finance_engine import get_fixed_expenses_for_month
from utils.date_utils import get_current_month, format_month, get_month_options
from models.fixed_expense import FixedExpense, FixedExpenseInstance
from utils.money_utils import format_currency

st.title("📆 Fixed Expenses Management")

acc_srv = FirestoreService("accounts")
fe_srv = FirestoreService("fixed_expenses")
fei_srv = FirestoreService("fixed_expense_instances")

accounts = acc_srv.get_all()


def build_account_options(account_items):
    return [
        {
            "label": f"{a.get('nombre', 'Unknown Account')} · {str(a.get('id', ''))[:6]}",
            "id": a.get('id'),
            "bank_id": a.get('bank_id')
        }
        for a in account_items
    ]


acc_options = build_account_options(accounts) if accounts else []

# Add new Fixed Expense
with st.expander("Add New Fixed Expense", expanded=False):
    if not accounts:
        st.warning("Please add an Account first.")
    else:
        with st.form("add_fe_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            
            with col1:
                nombre = st.text_input("Expense Name")
                monto = st.number_input("Monthly Amount", step=100.0)
                acc_labels = [a['label'] for a in acc_options]
                account_label = st.selectbox("Account", acc_labels)
                selected_acc = next((a for a in acc_options if a['label'] == account_label), None)
                
            with col2:
                fecha_inicio = st.date_input("Start Date", value=date.today(), format="DD/MM/YYYY")
                has_end_date = st.checkbox("Has End Date?", value=False)
                fecha_fin = st.date_input("End Date", value=date.today(), format="DD/MM/YYYY") if has_end_date else None
            
            submitted = st.form_submit_button("Save Fixed Expense")
            
            if submitted and nombre:
                if not selected_acc:
                    st.error("Please select a valid account.")
                else:
                    new_fe = FixedExpense(
                    nombre=nombre,
                    monto=monto,
                    fecha_inicio=fecha_inicio,
                    fecha_fin=fecha_fin,
                    bank_id=selected_acc['bank_id'],
                    account_id=selected_acc['id']
                )
                    fe_srv.add(new_fe.to_dict())
                    st.success("Fixed Expense added successfully!")
                    st.rerun()

st.divider()
st.subheader("Manage Monthly Payments")

# Month Selector
months = get_month_options()
# Use a session state to remember selected month or current
if 'fe_month' not in st.session_state:
    st.session_state['fe_month'] = get_current_month()

selected_month = st.selectbox("Select Month", months, index=months.index(st.session_state['fe_month']) if st.session_state['fe_month'] in months else 0)
st.session_state['fe_month'] = selected_month

# List active fixed expenses for the selected month
active_fes = get_fixed_expenses_for_month(selected_month)

if active_fes:
    st.write(f"Fixed Expenses for **{selected_month}**:")
    for fe in active_fes:
        col1, col2, col3, col4 = st.columns([3, 2, 2, 2])
        col1.markdown(f"**{fe['nombre']}**")
        col2.write(format_currency(fe['monto']))
        
        estado = fe['estado']
        color = "green" if estado == "pagado" else "red"
        col3.markdown(f":{color}[{estado.upper()}]")
        
        btn_label = "Mark Unpaid" if estado == "pagado" else "Mark Paid"
        
        if col4.button(btn_label, key=f"toggle_{fe['id']}_{selected_month}"):
            # Check if an instance already exists
            instances = fei_srv.get_by_field("fixed_expense_id", "==", fe['id'])
            inst = next((i for i in instances if i['mes'] == selected_month), None)
            
            new_estado = "impagado" if estado == "pagado" else "pagado"
            
            if inst:
                inst_id = inst['id']
                fei_srv.update(inst_id, {"estado": new_estado})
            else:
                new_inst = FixedExpenseInstance(
                    fixed_expense_id=fe['id'],
                    mes=selected_month,
                    estado=new_estado
                )
                fei_srv.add(new_inst.to_dict())
                
            st.rerun()
else:
    st.info("No active fixed expenses for this month.")

@st.dialog("Edit Fixed Expense")
def edit_fe_dialog(fe, acc_options):
    with st.form(f"edit_fe_form_{fe['id']}", clear_on_submit=False):
        col1, col2 = st.columns(2)
        
        with col1:
            nombre = st.text_input("Expense Name", value=fe.get("nombre", ""))
            monto = st.number_input("Monthly Amount", value=float(fe.get("monto", 0.0)), step=100.0)
            
            current_acc_id = fe.get("account_id")
            acc_labels = [a['label'] for a in acc_options]
            acc_index = next((i for i, a in enumerate(acc_options) if a['id'] == current_acc_id), 0)
            account_label = st.selectbox("Account", acc_labels, index=acc_index)
            selected_acc = next((a for a in acc_options if a['label'] == account_label), None)
            
        with col2:
            fecha_inicio = st.date_input("Start Date", value=fe.get("fecha_inicio", date.today()), format="DD/MM/YYYY")
            current_end = fe.get("fecha_fin")
            has_end_date = st.checkbox("Has End Date?", value=current_end is not None, key=f"he_{fe['id']}")
            fecha_fin = st.date_input("End Date", value=current_end if current_end else date.today(), format="DD/MM/YYYY") if has_end_date else None
        
        submitted = st.form_submit_button("Update Fixed Expense")
        
        if submitted:
            if nombre:
                if not selected_acc:
                    st.error("Please select a valid account.")
                    return
                fe_srv.update(fe["id"], {
                    "nombre": nombre,
                    "monto": monto,
                    "fecha_inicio": datetime.combine(fecha_inicio, datetime.min.time()) if fecha_inicio else None,
                    "fecha_fin": datetime.combine(fecha_fin, datetime.min.time()) if fecha_fin else None,
                    "bank_id": selected_acc['bank_id'],
                    "account_id": selected_acc['id']
                })
                st.success("Fixed Expense updated successfully!")
                st.rerun()
            else:
                st.error("Please fill in the expense name.")

st.divider()
st.subheader("All Fixed Expenses Definition")
all_fe = fe_srv.get_all()
if all_fe:
    for fe in all_fe:
        c1, c2, c3, c4, c5 = st.columns([3, 2, 2, 1, 1])
        c1.write(f"**{fe['nombre']}**")
        c2.write(format_currency(fe['monto']))
        
        start_d = str(fe.get('fecha_inicio'))[:10]
        end_d = str(fe.get('fecha_fin'))[:10] if fe.get('fecha_fin') else 'Ongoing'
        c3.write(f"Period: {start_d} to {end_d}")
        
        if c4.button("Edit", key=f"edit_fe_{fe['id']}"):
            edit_fe_dialog(fe, acc_options)
        if c5.button("Delete", key=f"del_fe_{fe['id']}"):
            fe_srv.delete(fe['id'])
            # Also potentially delete instances, but kept simple here
            st.rerun()
