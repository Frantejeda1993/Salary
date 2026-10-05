import streamlit as st
from datetime import date, datetime
from services.firestore_service import FirestoreService
from models.salary import Salary, normalize_deductions
from models.overtime import Overtime
from services.finance_engine import calculate_salary_net, get_salary_breakdown
from services.finance_core import FinanceCore
from utils.date_utils import get_current_month, get_month_options
from calendar import monthrange
from utils.money_utils import format_currency, format_percentage

st.title("💼 Salaries & Overtimes")

sal_srv = FirestoreService("salaries")
ot_srv = FirestoreService("overtimes")
acc_srv = FirestoreService("accounts")

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
                # Employee-side defaults (Spain, indefinite contract). Check against your payslip.
                {"name": "Cont. Común", "percentage": 0.0470, "applies_to_extras": True},
                {"name": "MEI", "percentage": 0.0015, "applies_to_extras": True},
                {"name": "Formación", "percentage": 0.0010, "applies_to_extras": True},
                {"name": "Desempleo", "percentage": 0.0155, "applies_to_extras": True},
                {"name": "IRPF", "percentage": 0.0000, "applies_to_extras": True},
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
                        step=0.0001,
                        format="%.4f",
                        required=True
                    ),
                    "applies_to_extras": st.column_config.CheckboxColumn("Applies to Extras", default=True)
                },
                key="new_salary_deductions",
                use_container_width=True
            )
            
            submitted = st.form_submit_button("Save Salary")
            
            if submitted and nombre:
                final_deductions = [
                    {
                        "name": d.get("name", ""),
                        "percentage": float(d.get("percentage", 0.0)),
                        "applies_to_extras": bool(d.get("applies_to_extras", False))
                    } for d in edited_deductions if d.get("name")
                ]
                
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
            salario_bruto = st.number_input("Bruto inicial", value=float(salary.get("salario_bruto", 0.0)), step=100.0,
                                            help="Corrige el bruto desde el inicio (todo el histórico). "
                                                 "Para una subida usa 'Subida salarial'.")
            
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
        
        current_deductions = normalize_deductions(salary)
            
        edited_deductions = st.data_editor(
            current_deductions,
            num_rows="dynamic",
            column_config={
                "name": st.column_config.TextColumn("Deduction Name", required=True),
                "percentage": st.column_config.NumberColumn(
                    "Deduction (%)",
                    min_value=0.0,
                    max_value=100.0,
                    step=0.0001,
                    format="%.4f",
                    required=True
                ),
                "applies_to_extras": st.column_config.CheckboxColumn("Applies to Extras", default=True)
            },
            key=f"edit_salary_deductions_{salary['id']}",
            use_container_width=True
        )
            
        submitted = st.form_submit_button("Update Salary")
        
        if submitted:
            if nombre:
                final_deductions = [
                    {
                        "name": d.get("name", ""),
                        "percentage": float(d.get("percentage", 0.0)),
                        "applies_to_extras": bool(d.get("applies_to_extras", False))
                    } for d in edited_deductions if d.get("name")
                ]
                
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

def _month_end(month: str) -> datetime:
    y, m = map(int, month.split("-"))
    return datetime(y, m, monthrange(y, m)[1])


def _month_options_with(value: str) -> list:
    months = get_month_options()
    return months if value in months else sorted(months + [value])


@st.dialog("Subida salarial")
def raise_dialog(salary):
    st.write(f"**{salary.get('nombre')}**")
    months = get_month_options()
    current_m = get_current_month()
    desde = st.selectbox("Nuevo bruto desde (mes en que te corresponde)", months, index=months.index(current_m))
    actual = FinanceCore._gross_owed(salary, desde, "9999-12")
    nuevo = st.number_input("Nuevo bruto mensual", value=float(actual), step=50.0)
    if actual:
        st.caption(f"Antes {format_currency(actual)} → {((nuevo - actual) / actual) * 100:+.2f} %")
    retro = st.checkbox("Se cobra más tarde, con atrasos (retroactiva)")
    cobro = desde
    if retro:
        later = [m for m in months if m > desde]
        cobro = st.selectbox("Primer mes en que se cobra", later)
        n = sum(1 for m in months if desde <= m < cobro)
        st.info(f"En {cobro} cobrarás el nuevo bruto + {n} mes(es) de atrasos "
                f"≈ {format_currency(n * (nuevo - actual))} brutos.")
    if st.button("Aplicar subida", type="primary", use_container_width=True):
        revs = [r for r in (salary.get("revisiones") or []) if r["desde"] != desde]
        rev = {"desde": desde, "salario_bruto": float(nuevo)}
        if retro:
            rev["cobro_desde"] = cobro
        revs.append(rev)
        sal_srv.update(salary["id"], {"revisiones": sorted(revs, key=lambda r: r["desde"])})
        st.rerun()


@st.dialog("Editar horas extra")
def edit_overtime_dialog(ot):
    months = _month_options_with(ot.get("mes_aplicacion", get_current_month()))
    mes = st.selectbox("Mes en que se cobran", months, index=months.index(ot.get("mes_aplicacion")) if ot.get("mes_aplicacion") in months else 0)
    monto = st.number_input("Importe bruto", value=float(ot.get("monto_bruto", 0.0)), min_value=0.0, step=10.0)
    c1, c2 = st.columns(2)
    if c1.button("Guardar", type="primary", use_container_width=True):
        ot_srv.update(ot["id"], {"mes_aplicacion": mes, "monto_bruto": float(monto)})
        st.rerun()
    if c2.button("Borrar", use_container_width=True):
        ot_srv.delete(ot["id"])
        st.rerun()


@st.dialog("Eliminar salario")
def delete_salary_dialog(salary):
    started = str(salary.get("fecha_inicio"))[:7] <= get_current_month()
    if started:
        st.warning(
            f"**{salary.get('nombre')}** ya se ha cobrado. Si lo borras, todos esos ingresos desaparecen de tus "
            "**saldos reales y del arrastre de los meses pasados**."
        )
        st.write("Si el trabajo terminó, **finalízalo**: deja de contar desde el mes siguiente y conserva la historia.")
        months = get_month_options()
        last = st.selectbox("Último mes cobrado", months, index=months.index(get_current_month()))
        if st.button("Finalizar", type="primary", use_container_width=True):
            sal_srv.update(salary["id"], {"fecha_fin": _month_end(last)})
            st.rerun()
        st.divider()
        confirm = st.checkbox("Entiendo que borrar altera el histórico")
        if st.button("Borrar igualmente", disabled=not confirm, use_container_width=True):
            sal_srv.delete(salary["id"])
            st.rerun()
    else:
        if st.button("Borrar", type="primary", use_container_width=True):
            sal_srv.delete(salary["id"])
            st.rerun()


st.subheader("Existing Salaries")
if salaries:
    current_m = get_current_month()
    overtimes = ot_srv.get_all()
    for s in salaries:
        with st.container(border=True):
            c1, c2, c3, c4, c5 = st.columns([3, 3, 1.6, 1, 1])
            c1.markdown(f"**{s.get('nombre')}**")
            current_gross = FinanceCore._gross_owed(s, current_m, current_m)
            c1.write(f"Bruto actual: {format_currency(current_gross)}")
            pending = [r for r in (s.get("revisiones") or []) if (r.get("cobro_desde") or r["desde"]) > current_m]
            for r in pending:
                c1.caption(f"⏳ Subida a {format_currency(r['salario_bruto'])} desde {r['desde']}"
                           f"{' · se cobra en ' + r['cobro_desde'] if r.get('cobro_desde') else ''}")

            net_this_month = calculate_salary_net(s['id'], current_m)
            c2.write(f"Neto este mes: **{format_currency(net_this_month)}**")

            if c3.button("Subida salarial", key=f"raise_{s['id']}"):
                raise_dialog(s)
            if c4.button("Edit", key=f"edit_s_{s['id']}"):
                edit_salary_dialog(s, acc_options)
            if c5.button("Delete", key=f"del_s_{s['id']}"):
                delete_salary_dialog(s)

            revs = sorted(s.get("revisiones") or [], key=lambda r: r["desde"])
            if revs:
                with st.expander("Historial salarial"):
                    rows, prev = [{"Desde": str(s.get("fecha_inicio"))[:7], "Bruto": format_currency(s.get("salario_bruto", 0.0)),
                                   "Variación": "", "Se cobra desde": ""}], s.get("salario_bruto", 0.0)
                    for r in revs:
                        rows.append({"Desde": r["desde"], "Bruto": format_currency(r["salario_bruto"]),
                                     "Variación": f"{((r['salario_bruto'] - prev) / prev) * 100:+.2f} %" if prev else "",
                                     "Se cobra desde": r.get("cobro_desde", r["desde"])})
                        prev = r["salario_bruto"]
                    st.dataframe(rows, hide_index=True, use_container_width=True)
                    for r in revs:
                        if st.button(f"Quitar subida de {r['desde']}", key=f"rmrev_{s['id']}_{r['desde']}"):
                            sal_srv.update(s["id"], {"revisiones": [x for x in revs if x["desde"] != r["desde"]]})
                            st.rerun()

            s_ots = sorted((o for o in overtimes if o.get("salary_id") == s["id"]),
                           key=lambda o: o.get("mes_aplicacion", ""), reverse=True)
            with st.expander(f"Horas extra ({len(s_ots)})"):
                with st.form(f"ot_form_{s['id']}", clear_on_submit=True):
                    ot_col1, ot_col2, ot_col3 = st.columns([2, 2, 1])
                    monto_bruto = ot_col1.number_input("Importe bruto", min_value=0.0, step=10.0)
                    months = get_month_options()
                    mes_app = ot_col2.selectbox("Mes en que se cobran", months, index=months.index(current_m))
                    if ot_col3.form_submit_button("Añadir") and monto_bruto > 0:
                        ot_srv.add(Overtime(salary_id=s['id'], monto_bruto=monto_bruto, mes_aplicacion=mes_app).to_dict())
                        st.rerun()
                if s_ots:
                    for o in s_ots:
                        oc1, oc2, oc3 = st.columns([2, 2, 1])
                        oc1.write(o.get("mes_aplicacion", "?"))
                        oc2.write(format_currency(o.get("monto_bruto", 0.0)))
                        if oc3.button("Editar", key=f"edit_ot_{o['id']}"):
                            edit_overtime_dialog(o)
                    st.caption(f"Total registrado: {format_currency(sum(o.get('monto_bruto', 0.0) for o in s_ots))} brutos")
                else:
                    st.caption("Sin horas extra registradas.")

            with st.expander("Detalle mensual"):
                start = str(s.get("fecha_inicio"))[:7]
                rows = []
                for m in get_month_options():
                    fin = s.get("fecha_fin")
                    if m < start or (fin and m > str(fin)[:7]):
                        continue
                    b = get_salary_breakdown(s["id"], m)
                    rows.append({
                        "Mes": f"{m}{' ◀' if m == current_m else ''}",
                        "Bruto": format_currency(b["base"]),
                        "Atrasos": format_currency(b["atrasos"]) if b["atrasos"] else "",
                        "Horas extra": format_currency(b["horas_extra"]) if b["horas_extra"] else "",
                        "Deducciones": format_currency(-b["deducciones"]),
                        "Neto": format_currency(b["neto"]),
                    })
                st.dataframe(rows, hide_index=True, use_container_width=True)
else:
    st.info("No salaries defined.")
