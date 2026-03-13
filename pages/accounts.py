import streamlit as st
from services.firestore_service import FirestoreService
from models.account import Account
from utils.money_utils import format_currency

st.title("💳 Accounts Management")

bank_srv = FirestoreService("banks")
acc_srv = FirestoreService("accounts")

banks = bank_srv.get_all()
accounts = acc_srv.get_all()


def build_bank_options(bank_items):
    return [
        {
            "label": f"{b.get('nombre', 'Unknown Bank')} · {str(b.get('id', ''))[:6]}",
            "id": b.get("id"),
        }
        for b in bank_items
    ]

if not banks:
    st.warning("Please add a Bank first before creating an Account.")
else:
    bank_options = build_bank_options(banks)

    with st.expander("Add New Account", expanded=False):
        with st.form("add_acc_form", clear_on_submit=True):
            bank_labels = [b["label"] for b in bank_options]
            bank_label = st.selectbox("Bank", bank_labels)
            selected_bank = next((b for b in bank_options if b["label"] == bank_label), None)
            nombre = st.text_input("Account Name")
            saldo_inicial = st.number_input("Initial Balance", value=0.0, step=100.0)
            
            submitted = st.form_submit_button("Save Account")
            
            if submitted:
                if nombre:
                    new_acc = Account(
                        bank_id=selected_bank["id"] if selected_bank else None,
                        nombre=nombre,
                        saldo_inicial=saldo_inicial
                    )
                    acc_srv.add(new_acc.to_dict())
                    st.success("Account added successfully!")
                    st.rerun()
                else:
                    st.error("Please provide an Account name.")

@st.dialog("Edit Account")
def edit_account_dialog(account, bank_options):
    with st.form(f"edit_acc_form_{account['id']}", clear_on_submit=False):
        current_bank_id = account.get("bank_id")
        bank_labels = [b["label"] for b in bank_options]
        bank_index = next((i for i, b in enumerate(bank_options) if b["id"] == current_bank_id), 0)
            
        bank_label = st.selectbox("Bank", bank_labels, index=bank_index)
        selected_bank = next((b for b in bank_options if b["label"] == bank_label), None)
        nombre = st.text_input("Account Name", value=account.get("nombre", ""))
        saldo_inicial = st.number_input("Initial Balance", value=float(account.get("saldo_inicial", 0.0)), step=100.0)
        
        submitted = st.form_submit_button("Update Account")
        if submitted:
            if nombre:
                acc_srv.update(account["id"], {
                    "bank_id": selected_bank["id"] if selected_bank else None,
                    "nombre": nombre,
                    "saldo_inicial": saldo_inicial
                })
                st.success("Account updated successfully!")
                st.rerun()
            else:
                st.error("Please provide an Account name.")

st.subheader("Existing Accounts")
if accounts:
    # Build reverse lookup for bank name
    bank_lookup = {b['id']: b['nombre'] for b in banks}
    
    for a in accounts:
        col1, col2, col3, col4, col5 = st.columns([2, 2, 2, 1, 1])
        is_main = a.get('is_main', False)
        
        # Display main account indicator
        main_badge = " ⭐ (Main)" if is_main else ""
        col1.markdown(f"**{a.get('nombre')}**{main_badge}")
        
        col2.write(f"Bank: {bank_lookup.get(a.get('bank_id'), 'Unknown')}")
        col3.write(f"Initial: {format_currency(a.get('saldo_inicial', 0.0))}")
        
        # In col4 we will either have Edit or Set as Main
        if not is_main:
            if col4.button("Set Main", key=f"main_{a['id']}"):
                # Set all other accounts to is_main=False
                for other_a in accounts:
                    if other_a.get('is_main', False):
                        acc_srv.update(other_a['id'], {"is_main": False})
                # Set this account to is_main=True
                acc_srv.update(a['id'], {"is_main": True})
                st.rerun()
        else:
            col4.write("") # empty space
            
        with st.popover("⚙️", use_container_width=True):
            if st.button("Edit", key=f"edit_{a['id']}", use_container_width=True):
                bank_options_pass = build_bank_options(banks)
                edit_account_dialog(a, bank_options_pass)
            
            if st.button("Delete", key=f"del_{a['id']}", type="primary", use_container_width=True):
                acc_srv.delete(a['id'])
                st.rerun()
else:
    st.info("No accounts found. Please add one.")
