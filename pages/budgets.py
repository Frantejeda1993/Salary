import streamlit as st
from datetime import date, datetime
from services.firestore_service import FirestoreService
from models.budget import Budget
from utils.money_utils import format_currency

st.title("🎯 Budgets Management")

cat_srv = FirestoreService("categories")
bank_srv = FirestoreService("banks")
acc_srv = FirestoreService("accounts")
bud_srv = FirestoreService("budgets")

categories = cat_srv.get_all()
banks = bank_srv.get_all()
accounts = acc_srv.get_all()
budgets = bud_srv.get_all()


def build_category_options(category_items):
    return [
        {"label": f"{c.get('nombre', 'Unknown Category')} · {str(c.get('id', ''))[:6]}", "id": c.get('id')}
        for c in category_items if c.get('tipo', 'normal') != 'extra'
    ]


def build_account_options(account_items, bank_lookup):
    return [
        {
            "label": f"{a.get('nombre', 'Unknown Account')} · {bank_lookup.get(a.get('bank_id'), 'Unknown Bank')} · {str(a.get('id', ''))[:6]}",
            "id": a.get('id'),
            "bank_id": a.get('bank_id')
        }
        for a in account_items
    ]

if not categories or not accounts:
    st.warning("Please ensure you have at least one Category and one Account created before adding a Budget.")
else:
    bank_lookup = {b['id']: b['nombre'] for b in banks}
    cat_options = build_category_options(categories)
    acc_options = build_account_options(accounts, bank_lookup)

    with st.expander("Add New Budget", expanded=False):
        with st.form("add_budget_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            
            with col1:
                cat_labels = [c['label'] for c in cat_options]
                categoria_label = st.selectbox("Category", cat_labels if cat_labels else ["None"])
                selected_category = next((c for c in cat_options if c['label'] == categoria_label), None)
                monto = st.number_input("Monthly Budget Amount", min_value=0.0, step=100.0)
                acc_labels = [a['label'] for a in acc_options]
                account_label = st.selectbox("Account", acc_labels)
                selected_acc = next((a for a in acc_options if a['label'] == account_label), None)
                
            with col2:
                fecha_inicio = st.date_input("Start Date", value=date.today(), format="DD/MM/YYYY")
                has_end_date = st.checkbox("Has End Date?", value=False)
                fecha_fin = st.date_input("End Date", value=date.today(), format="DD/MM/YYYY") if has_end_date else None
            
            submitted = st.form_submit_button("Save Budget")
            
            if submitted:
                if selected_category and selected_acc:
                    new_budget = Budget(
                        categoria_id=selected_category['id'],
                        monto=monto,
                        fecha_inicio=fecha_inicio,
                        fecha_fin=fecha_fin,
                        bank_id=selected_acc['bank_id'],
                        account_id=selected_acc['id']
                    )
                    bud_srv.add(new_budget.to_dict())
                    st.success("Budget added successfully!")
                    st.rerun()
                else:
                    st.error("Please fill in valid category and account.")

@st.dialog("Edit Budget")
def edit_budget_dialog(budget, cat_options, acc_options):
    with st.form(f"edit_budget_form_{budget['id']}", clear_on_submit=False):
        col1, col2 = st.columns(2)
        
        with col1:
            current_cat_id = budget.get("categoria_id")
            cat_labels = [c['label'] for c in cat_options]
            cat_index = next((i for i, c in enumerate(cat_options) if c['id'] == current_cat_id), 0)
            categoria_label = st.selectbox("Category", cat_labels if cat_labels else ["None"], index=cat_index)
            selected_category = next((c for c in cat_options if c['label'] == categoria_label), None)
            
            monto = st.number_input("Monthly Budget Amount", value=float(budget.get("monto", 0.0)), step=100.0)
            
            current_acc_id = budget.get("account_id")
            acc_labels = [a['label'] for a in acc_options]
            acc_index = next((i for i, a in enumerate(acc_options) if a['id'] == current_acc_id), 0)
            account_label = st.selectbox("Account", acc_labels, index=acc_index)
            selected_acc = next((a for a in acc_options if a['label'] == account_label), None)
            
        with col2:
            fecha_inicio = st.date_input("Start Date", value=budget.get("fecha_inicio", date.today()), format="DD/MM/YYYY")
            current_end = budget.get("fecha_fin")
            has_end_date = st.checkbox("Has End Date?", value=current_end is not None, key=f"he_b_{budget['id']}")
            fecha_fin = st.date_input("End Date", value=current_end if current_end else date.today(), format="DD/MM/YYYY") if has_end_date else None
        
        submitted = st.form_submit_button("Update Budget")
        
        if submitted:
            if selected_category and selected_acc:
                bud_srv.update(budget["id"], {
                    "categoria_id": selected_category['id'],
                    "monto": monto,
                    "fecha_inicio": datetime.combine(fecha_inicio, datetime.min.time()) if fecha_inicio else None,
                    "fecha_fin": datetime.combine(fecha_fin, datetime.min.time()) if fecha_fin else None,
                    "bank_id": selected_acc['bank_id'],
                    "account_id": selected_acc['id']
                })
                st.success("Budget updated successfully!")
                st.rerun()
            else:
                st.error("Please fill in valid category and account.")

st.subheader("Existing Budgets")
if budgets:
    cat_lookup = {c['id']: c['nombre'] for c in categories}
    acc_lookup = {a['id']: a['nombre'] for a in accounts}
    
    for b in budgets:
        c1, c2, c3, c4, c5 = st.columns([2, 1, 2, 1, 1])
        c1.markdown(f"**{cat_lookup.get(b.get('categoria_id'), 'Unknown Category')}**")
        c2.write(f"Amount: {format_currency(b.get('monto', 0.0))}")
        
        start_d = str(b.get('fecha_inicio'))[:10]
        end_d = str(b.get('fecha_fin'))[:10] if b.get('fecha_fin') else 'Ongoing'
        c3.write(f"Period: {start_d} to {end_d}")
        
        if c4.button("Edit", key=f"edit_b_{b['id']}"):
            cat_options_pass = build_category_options(categories)
            bank_lookup_pass = {b['id']: b['nombre'] for b in banks}
            acc_options_pass = build_account_options(accounts, bank_lookup_pass)
            edit_budget_dialog(b, cat_options_pass, acc_options_pass)
        if c5.button("Delete", key=f"del_b_{b['id']}"):
            bud_srv.delete(b['id'])
            st.rerun()
else:
    st.info("No budgets found.")
