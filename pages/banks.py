import streamlit as st
from services.firestore_service import FirestoreService
from models.bank import Bank

st.title("🏦 Banks Management")

bank_srv = FirestoreService("banks")
banks = bank_srv.get_all()

# Add Bank Form
with st.expander("Add New Bank", expanded=False):
    with st.form("add_bank_form", clear_on_submit=True):
        nombre = st.text_input("Bank Name")
        duenio = st.text_input("Owner")
        submitted = st.form_submit_button("Save Bank")
        
        if submitted:
            if nombre and duenio:
                new_bank = Bank(nombre=nombre, duenio=duenio)
                bank_srv.add(new_bank.to_dict())
                st.success("Bank added successfully!")
                st.rerun()
            else:
                st.error("Please fill in all fields.")

@st.dialog("Edit Bank")
def edit_bank_dialog(bank):
    with st.form(f"edit_bank_form_{bank['id']}", clear_on_submit=False):
        nombre = st.text_input("Bank Name", value=bank.get("nombre", ""))
        duenio = st.text_input("Owner", value=bank.get("duenio", ""))
        submitted = st.form_submit_button("Update Bank")
        
        if submitted:
            if nombre and duenio:
                bank_srv.update(bank["id"], {"nombre": nombre, "duenio": duenio})
                st.success("Bank updated successfully!")
                st.rerun()
            else:
                st.error("Please fill in all fields.")

# List Banks
st.subheader("Existing Banks")
if banks:
    for b in banks:
        col1, col2, col3, col4 = st.columns([3, 2, 1, 1])
        col1.write(f"**{b.get('nombre')}**")
        col2.write(f"Owner: {b.get('duenio')}")
        if col3.button("Edit", key=f"edit_{b['id']}"):
            edit_bank_dialog(b)
        if col4.button("Delete", key=f"del_{b['id']}"):
            bank_srv.delete(b['id'])
            st.rerun()
else:
    st.info("No banks found. Please add one.")
