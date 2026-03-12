import streamlit as st
from datetime import date, datetime
from services.firestore_service import FirestoreService
from models.transfer import Transfer
from utils.money_utils import format_currency

st.title("🔄 Transfers")

acc_srv = FirestoreService("accounts")
trf_srv = FirestoreService("transfers")

accounts = acc_srv.get_all()

if len(accounts) < 2:
    st.warning("You need at least two Accounts to make a transfer.")
else:
    acc_options = {a['nombre']: a for a in accounts}
    acc_names = list(acc_options.keys())
    
    with st.form("transfer_form", clear_on_submit=True):
        st.subheader("New Transfer")
        col1, col2 = st.columns(2)
        with col1:
            fecha = st.date_input("Date", value=date.today(), format="DD/MM/YYYY")
            origen = st.selectbox("From Account", acc_names, index=0)
        with col2:
            monto = st.number_input("Amount", min_value=0.0, step=100.0)
            destino = st.selectbox("To Account", acc_names, index=1)
            
        submitted = st.form_submit_button("Execute Transfer")
        
        if submitted:
            if origen == destino:
                st.error("Origin and Destination accounts must be different.")
            elif monto <= 0:
                st.error("Amount must be greater than zero.")
            else:
                new_trf = Transfer(
                    fecha=fecha,
                    cuenta_origen=acc_options[origen]['id'],
                    cuenta_destino=acc_options[destino]['id'],
                    monto=monto
                )
                trf_srv.add(new_trf.to_dict())
                st.success("Transfer recorded.")
                st.rerun()

@st.dialog("Edit Transfer")
def edit_transfer_dialog(tr, accounts_list, acc_opts, acc_nms):
    with st.form(f"edit_tr_form_{tr['id']}", clear_on_submit=False):
        col1, col2 = st.columns(2)
        
        with col1:
            fecha = st.date_input("Date", value=tr.get("fecha", date.today()), format="DD/MM/YYYY")
            
            # Find index of current origin account
            current_origen_id = tr.get("cuenta_origen")
            try:
                current_origen_name = next(name for name, acc in acc_opts.items() if acc['id'] == current_origen_id)
                origen_index = acc_nms.index(current_origen_name)
            except StopIteration:
                origen_index = 0
            origen = st.selectbox("From Account", acc_nms, index=origen_index)
            
        with col2:
            monto = st.number_input("Amount", value=float(tr.get("monto", 0.0)), min_value=0.0, step=100.0)
            
            # Find index of current destination account
            current_destino_id = tr.get("cuenta_destino")
            try:
                current_destino_name = next(name for name, acc in acc_opts.items() if acc['id'] == current_destino_id)
                destino_index = acc_nms.index(current_destino_name)
            except StopIteration:
                destino_index = min(1, len(acc_nms)-1)
            destino = st.selectbox("To Account", acc_nms, index=destino_index)
            
        submitted = st.form_submit_button("Update Transfer")
        
        if submitted:
            if origen == destino:
                st.error("Origin and Destination accounts must be different.")
            elif monto <= 0:
                st.error("Amount must be greater than zero.")
            else:
                trf_srv.update(tr["id"], {
                    "fecha": datetime.combine(fecha, datetime.min.time()) if fecha else None,
                    "cuenta_origen": acc_opts[origen]['id'],
                    "cuenta_destino": acc_opts[destino]['id'],
                    "monto": monto
                })
                st.success("Transfer updated successfully!")
                st.rerun()

st.divider()
st.subheader("Recent Transfers")
transfers = trf_srv.get_all()

if transfers:
    acc_lookup = {a['id']: a['nombre'] for a in accounts}
    transfers.sort(key=lambda x: str(x.get('fecha', '')), reverse=True)
    
    for tr in transfers[:20]:
        c1, c2, c3, c4, c5 = st.columns([2, 2, 2, 1, 1])
        c1.write(f"**From**: {acc_lookup.get(tr.get('cuenta_origen'), 'Unknown')}")
        c2.write(f"**To**: {acc_lookup.get(tr.get('cuenta_destino'), 'Unknown')}")
        
        amt_str = format_currency(tr.get('monto', 0.0))
        loan_badge = ""
        if tr.get('is_loan', False):
            if tr.get('status') == 'pending':
                loan_badge = " *(Loan: Pending)*"
            elif tr.get('status') == 'paid':
                loan_badge = " *(Loan: Paid)*"
                
        c3.write(f"Amount: **{amt_str}**{loan_badge}")
        
        if c4.button("Edit", key=f"edit_tr_{tr['id']}"):
            edit_transfer_dialog(tr, accounts, acc_options, acc_names)
        if c5.button("Delete", key=f"del_tr_{tr['id']}"):
            trf_srv.delete(tr['id'])
            st.rerun()
else:
    st.info("No transfers recorded.")
