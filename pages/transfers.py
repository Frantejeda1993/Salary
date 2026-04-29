import streamlit as st
from datetime import date, datetime
from services.firestore_service import FirestoreService
from models.transfer import Transfer
from utils.money_utils import format_currency

st.title("🔄 Transfers")

acc_srv = FirestoreService("accounts")
trf_srv = FirestoreService("transfers")

accounts = acc_srv.get_all()


def build_account_options(account_items):
    return [
        {
            "label": f"{a.get('nombre', 'Unknown Account')} · {str(a.get('id', ''))[:6]}",
            "id": a.get('id'),
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


acc_options = build_account_options(accounts) if accounts else []

if len(accounts) < 2:
    st.warning("You need at least two Accounts to make a transfer.")
else:
    acc_labels = [a['label'] for a in acc_options]
    main_acc_index = next((i for i, a in enumerate(acc_options) if a.get("is_main") or a.get("nombre") == "Main"), 0)
    default_destino_index = next((i for i, a in enumerate(acc_options) if i != main_acc_index), 0)
    
    with st.form("transfer_form", clear_on_submit=True):
        st.subheader("New Transfer")
        col1, col2 = st.columns(2)
        with col1:
            fecha = st.date_input("Date", value=date.today(), format="DD/MM/YYYY")
            origen_label = st.selectbox("From Account", acc_labels, index=main_acc_index)
            origen = next((a for a in acc_options if a['label'] == origen_label), None)
        with col2:
            monto_raw = st.text_input("Amount", value="", placeholder="0")
            monto = parse_amount_input(monto_raw)
            destino_label = st.selectbox("To Account", acc_labels, index=default_destino_index)
            destino = next((a for a in acc_options if a['label'] == destino_label), None)
            
        submitted = st.form_submit_button("Execute Transfer")
        
        if submitted:
            if not origen or not destino:
                st.error("Please select valid accounts.")
            elif origen['id'] == destino['id']:
                st.error("Origin and Destination accounts must be different.")
            elif monto is None:
                st.error("Please enter a valid amount.")
            elif monto <= 0:
                st.error("Amount must be greater than zero.")
            else:
                new_trf = Transfer(
                    fecha=fecha,
                    cuenta_origen=origen['id'],
                    cuenta_destino=destino['id'],
                    monto=monto
                )
                trf_srv.add(new_trf.to_dict())
                st.success("Transfer recorded.")
                st.rerun()

@st.dialog("Edit Transfer")
def edit_transfer_dialog(tr, accounts_list, acc_opts):
    with st.form(f"edit_tr_form_{tr['id']}", clear_on_submit=False):
        col1, col2 = st.columns(2)
        
        with col1:
            fecha = st.date_input("Date", value=tr.get("fecha", date.today()), format="DD/MM/YYYY")
            
            # Find index of current origin account
            current_origen_id = tr.get("cuenta_origen")
            try:
                origen_index = next(i for i, acc in enumerate(acc_opts) if acc['id'] == current_origen_id)
            except StopIteration:
                origen_index = 0
            origen_label = st.selectbox("From Account", [a['label'] for a in acc_opts], index=origen_index)
            origen = next((a for a in acc_opts if a['label'] == origen_label), None)
            
        with col2:
            monto = st.number_input("Amount", value=float(tr.get("monto", 0.0)), min_value=0.0, step=100.0)
            
            # Find index of current destination account
            current_destino_id = tr.get("cuenta_destino")
            try:
                destino_index = next(i for i, acc in enumerate(acc_opts) if acc['id'] == current_destino_id)
            except StopIteration:
                destino_index = min(1, len(acc_opts)-1)
            destino_label = st.selectbox("To Account", [a['label'] for a in acc_opts], index=destino_index)
            destino = next((a for a in acc_opts if a['label'] == destino_label), None)
            
        submitted = st.form_submit_button("Update Transfer")
        
        if submitted:
            if not origen or not destino:
                st.error("Please select valid accounts.")
            elif origen['id'] == destino['id']:
                st.error("Origin and Destination accounts must be different.")
            elif monto <= 0:
                st.error("Amount must be greater than zero.")
            else:
                update_data = {
                    "fecha": datetime.combine(fecha, datetime.min.time()) if fecha else None,
                    "cuenta_origen": origen['id'],
                    "cuenta_destino": destino['id'],
                    "monto": monto
                }

                if tr.get('is_loan', False):
                    current_outstanding = float(tr.get('outstanding_amount', tr.get('monto', 0.0)))
                    paid_amount = max(float(tr.get('monto', 0.0)) - current_outstanding, 0.0)
                    new_outstanding = max(monto - paid_amount, 0.0)
                    update_data["outstanding_amount"] = new_outstanding
                    update_data["status"] = 'paid' if new_outstanding == 0 else 'pending'

                trf_srv.update(tr["id"], update_data)
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
            pending_amount = tr.get('outstanding_amount', tr.get('monto', 0.0))
            if tr.get('status') == 'pending':
                loan_badge = f" *(Loan: Pending {format_currency(pending_amount)})*"
            elif tr.get('status') == 'paid':
                loan_badge = " *(Loan: Paid)*"
                
        c3.write(f"Amount: **{amt_str}**{loan_badge}")
        
        if c4.button("Edit", key=f"edit_tr_{tr['id']}"):
            edit_transfer_dialog(tr, accounts, acc_options)
        if c5.button("Delete", key=f"del_tr_{tr['id']}"):
            trf_srv.delete(tr['id'])
            st.rerun()
else:
    st.info("No transfers recorded.")
