import streamlit as st
from services.firestore_service import FirestoreService
from models.category import Category

st.title("📁 Categories Management")

cat_srv = FirestoreService("categories")
categories = cat_srv.get_all()

with st.expander("Add New Category", expanded=False):
    with st.form("add_cat_form", clear_on_submit=True):
        nombre = st.text_input("Category Name")
        tipo = st.selectbox("Type", ["normal", "extra"], help="Extra categories reduce expenses when generating extra income.")
        submitted = st.form_submit_button("Save Category")
        
        if submitted:
            if nombre:
                new_cat = Category(nombre=nombre, tipo=tipo)
                cat_srv.add(new_cat.to_dict())
                st.success("Category added successfully!")
                st.rerun()
            else:
                st.error("Please fill in the name.")

@st.dialog("Edit Category")
def edit_category_dialog(category):
    with st.form(f"edit_cat_form_{category['id']}", clear_on_submit=False):
        nombre = st.text_input("Category Name", value=category.get("nombre", ""))
        tipo_index = 0 if category.get("tipo", "normal") == "normal" else 1
        tipo = st.selectbox("Type", ["normal", "extra"], index=tipo_index, help="Extra categories reduce expenses when generating extra income.")
        submitted = st.form_submit_button("Update Category")
        
        if submitted:
            if nombre:
                cat_srv.update(category["id"], {"nombre": nombre, "tipo": tipo})
                st.success("Category updated successfully!")
                st.rerun()
            else:
                st.error("Please fill in the name.")

st.subheader("Existing Categories")
if categories:
    for c in categories:
        col1, col2, col3, col4 = st.columns([3, 2, 1, 1])
        col1.write(f"**{c.get('nombre')}**")
        color = "blue" if c.get('tipo') == "normal" else "green"
        col2.markdown(f":{color}[{c.get('tipo', 'normal').capitalize()}]")
        if col3.button("Edit", key=f"edit_{c['id']}"):
            edit_category_dialog(c)
        if col4.button("Delete", key=f"del_{c['id']}"):
            cat_srv.delete(c['id'])
            st.rerun()
else:
    st.info("No categories found. Please add one.")
