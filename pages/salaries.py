import streamlit as st
from datetime import date, datetime
from services.firestore_service import FirestoreService
from models.salary import Salary
from models.overtime import Overtime
from services.finance_engine import calculate_salary_net
from utils.date_utils import get_current_month
from utils.money_utils import format_currency, format_percentage

st.title("💼 Salaries & Overtimes")

sal_srv = FirestoreService("salaries")
ot_srv = FirestoreService("overtimes")
acc_srv = FirestoreService("accounts")


def normalize_percentage_to_0_100(value: float) -> float:
    pct = float(value)
    if 0.0 <= pct <= 1.0:
        return pct * 100.0
    return pct


def validate_deductions_percentages(deductions: list[dict]) -> tuple[bool, str]:
    for d in deductions:
        pct = float(d.get("percentage", 0.0))
        if pct < 0 or pct > 100:
            name = d.get("name", "(unnamed deduction)")
            return False, f"Invalid percentage in '{name}': {pct}. Use values between 0 and 100."
    return True, ""


accounts = acc_srv.get_all()
salaries = sal_srv.get_all()


def build_account_options(account_items):
    return [
        {
            "label": f"{a.get('nombre', 'Unknown Account')} · {str(a.get('id', ''))[:6]}",
            "id": a.get("id"),
            "bank_id": a.get("bank_id"),
        }
        for a in account_items
    ]

if not accounts:
    st.warning("Please add an Account first.")
else:
    acc_options = build_account_options(accounts)

    with st.expander("Add New Salary", expanded=False):
        with st.form("add_salary_form", clear_on_submit=True):
            st.subheader("General Info")
            col1, col2 = st.columns(2)
            with col1:
                nombre = st.text_input("Position / Title")
                salario_bruto = st.number_input("Gross Salary", min_value=0.0, step=100.0)
                acc_labels = [a["label"] for a in acc_options]
                account_label = st.selectbox("Account to deposit", acc_labels)
                selected_acc = next((a for a in acc_options if a["label"] == account_label), None)
            with col2:
                fecha_inicio = st.date_input("Start Date", value=date.today(), format="DD/MM/YYYY")
                has_end_date = st.checkbox("Has End Date?", value=False)
                fecha_fin = st.date_input("End Date", value=date.today(), format="DD/MM/YYYY") if has_end_date else None
                
            st.subheader("Deductions (%)")
            default_deductions = [
                {"name": "Cont. Común", "percentage": 15.0, "applies_to_extras": True},
                {"name": "MEI", "percentage": 0.1, "applies_to_extras": True},
                {"name": "Formación", "percentage": 0.1, "applies_to_extras": True},
                {"name": "Desempleo", "percentage": 0.1, "applies_to_extras": True},
                {"name": "IRPF", "percentage": 0.0, "applies_to_extras": True},
            ]
            
            edited_deductions = st.data_editor(
                default_deductions,
                num_rows="dynamic",
                column_config={
                    "name": st.column_config.TextColumn("Deduction Name", required=True),
                    "percentage": st.column_config.NumberColumn(
                        "Deduction (%)",
                        min_value=0.0,
                        max_value=100.0,
                        step=0.1,
                        format="%.2f",
                        required=True
                    ),
                    "applies_to_extras": st.column_config.CheckboxColumn("Applies to Extras", default=True)
                },
                key="new_salary_deductions",
                use_container_width=True
            )
            st.caption("Formato de porcentaje: usa escala 0-100 (ej: 15.0 para 15%, 0.1 para 0.1%).")
            
            submitted = st.form_submit_button("Save Salary")
            
            if submitted and nombre:
                final_deductions = [
                    {
                        "name": d.get("name", ""),
                        "percentage": normalize_percentage_to_0_100(d.get("percentage", 0.0)),
                        "applies_to_extras": bool(d.get("applies_to_extras", False))
                    } for d in edited_deductions if d.get("name")
                ]
                valid, msg = validate_deductions_percentages(final_deductions)
                if not valid:
                    st.error(msg)
                    st.stop()

                new_sal = Salary(
                    nombre=nombre, salario_bruto=salario_bruto,
                    deductions=final_deductions,
                    fecha_inicio=fecha_inicio, fecha_fin=fecha_fin,
                    bank_id=selected_acc['bank_id'], account_id=selected_acc['id']
                )
                sal_srv.add(new_sal.to_dict())
                st.success("Salary added successfully!")
                st.rerun()

@st.dialog("Edit Salary")
def edit_salary_dialog(salary, acc_options):
    with st.form(f"edit_sal_form_{salary['id']}", clear_on_submit=False):
        st.subheader("General Info")
        col1, col2 = st.columns(2)
        with col1:
            nombre = st.text_input("Position / Title", value=salary.get("nombre", ""))
            salario_bruto = st.number_input("Gross Salary", value=float(salary.get("salario_bruto", 0.0)), step=100.0)
            
            # Match account
            current_acc_id = salary.get("account_id")
            acc_labels = [a["label"] for a in acc_options]
            acc_index = next((i for i, a in enumerate(acc_options) if a["id"] == current_acc_id), 0)
            account_label = st.selectbox("Account to deposit", acc_labels, index=acc_index)
            selected_acc = next((a for a in acc_options if a["label"] == account_label), None)
            
        with col2:
            fecha_inicio = st.date_input("Start Date", value=salary.get("fecha_inicio", date.today()), format="DD/MM/YYYY")
            current_end = salary.get("fecha_fin")
            has_end_date = st.checkbox("Has End Date?", value=current_end is not None)
            fecha_fin = st.date_input("End Date", value=current_end if current_end else date.today(), format="DD/MM/YYYY") if has_end_date else None
            
        st.subheader("Deductions (%)")
        
        current_deductions = salary.get("deductions")
        if not current_deductions:
            current_deductions = [
                {"name": "Cont. Común", "percentage": float(salary.get("cont_comun", 15.0)), "applies_to_extras": bool(salary.get("cont_comun_aplica_extras", True))},
                {"name": "MEI", "percentage": float(salary.get("mei", 0.1)), "applies_to_extras": bool(salary.get("mei_aplica_extras", True))},
                {"name": "Formación", "percentage": float(salary.get("formacion", 0.1)), "applies_to_extras": bool(salary.get("formacion_aplica_extras", True))},
                {"name": "Desempleo", "percentage": float(salary.get("desempleo", 0.1)), "applies_to_extras": bool(salary.get("desempleo_aplica_extras", True))},
                {"name": "IRPF", "percentage": float(salary.get("irpf", 0.0)), "applies_to_extras": bool(salary.get("irpf_aplica_extras", True))},
            ]

        current_deductions = [
            {
                "name": d.get("name", ""),
                "percentage": normalize_percentage_to_0_100(d.get("percentage", 0.0)),
                "applies_to_extras": bool(d.get("applies_to_extras", False))
            }
            for d in current_deductions
        ]
            
        edited_deductions = st.data_editor(
            current_deductions,
            num_rows="dynamic",
            column_config={
                "name": st.column_config.TextColumn("Deduction Name", required=True),
                "percentage": st.column_config.NumberColumn(
                    "Deduction (%)",
                    min_value=0.0,
                    max_value=100.0,
                    step=0.1,
                    format="%.2f",
                    required=True
                ),
                "applies_to_extras": st.column_config.CheckboxColumn("Applies to Extras", default=True)
            },
            key=f"edit_salary_deductions_{salary['id']}",
            use_container_width=True
        )
        st.caption("Formato de porcentaje: usa escala 0-100 (ej: 15.0 para 15%, 0.1 para 0.1%).")

        submitted = st.form_submit_button("Update Salary")
        
        if submitted:
            if nombre:
                final_deductions = [
                    {
                        "name": d.get("name", ""),
                        "percentage": normalize_percentage_to_0_100(d.get("percentage", 0.0)),
                        "applies_to_extras": bool(d.get("applies_to_extras", False))
                    } for d in edited_deductions if d.get("name")
                ]
                valid, msg = validate_deductions_percentages(final_deductions)
                if not valid:
                    st.error(msg)
                    st.stop()

                sal_srv.update(salary["id"], {
                    "nombre": nombre, "salario_bruto": salario_bruto,
                    "deductions": final_deductions,
                    "fecha_inicio": datetime.combine(fecha_inicio, datetime.min.time()) if fecha_inicio else None,
                    "fecha_fin": datetime.combine(fecha_fin, datetime.min.time()) if fecha_fin else None,
                    "bank_id": selected_acc['bank_id'], "account_id": selected_acc['id']
                })
                st.success("Salary updated successfully!")
                st.rerun()
            else:
                st.error("Please fill in the title.")

st.subheader("Existing Salaries")
if salaries:
    current_m = get_current_month()
    for s in salaries:
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([3, 2, 1, 1])
            c1.markdown(f"**{s.get('nombre')}**")
            c1.write(f"Gross: {format_currency(s.get('salario_bruto', 0.0))}")
            
            net_this_month = calculate_salary_net(s['id'], current_m)
            c2.write(f"Net (Current Month): **{format_currency(net_this_month)}**")
            
            if c3.button("Edit", key=f"edit_s_{s['id']}"):
                edit_salary_dialog(s, acc_options)
            if c4.button("Delete", key=f"del_s_{s['id']}"):
                sal_srv.delete(s['id'])
                st.rerun()
                
            with st.expander("Add Overtime (Horas Extra)"):
                with st.form(f"ot_form_{s['id']}", clear_on_submit=True):
                    ot_col1, ot_col2 = st.columns(2)
                    monto_bruto = ot_col1.number_input("Gross Amount", min_value=0.0, step=50.0)
                    mes_app = ot_col2.text_input("Application Month (YYYY-MM)", value=current_m)
                    
                    if st.form_submit_button("Log Overtime") and monto_bruto > 0:
                        new_ot = Overtime(
                            salary_id=s['id'],
                            monto_bruto=monto_bruto,
                            mes_aplicacion=mes_app
                        )
                        ot_srv.add(new_ot.to_dict())
                        st.success("Overtime logged!")
                        st.rerun()
else:
    st.info("No salaries defined.")
