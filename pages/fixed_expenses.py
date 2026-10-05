import streamlit as st
from datetime import date, datetime
from services.firestore_service import FirestoreService
from services.finance_engine import get_fixed_expenses_for_month
from utils.date_utils import get_current_month, format_month, get_month_options, month_range
from models.fixed_expense import FixedExpense, FixedExpenseInstance
from utils.money_utils import format_currency
from services.finance_core import fixed_amount_for_month, fixed_account_for_month, add_months
from calendar import monthrange

st.title("📆 Fixed Expenses Management")

acc_srv = FirestoreService("accounts")
bank_srv = FirestoreService("banks")
fe_srv = FirestoreService("fixed_expenses")
fei_srv = FirestoreService("fixed_expense_instances")

accounts = acc_srv.get_all()
banks = bank_srv.get_all()
bank_lookup = {b.get('id'): b.get('nombre', 'Unknown Bank') for b in banks}
account_lookup = {a.get('id'): a for a in accounts}


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

all_fe = fe_srv.get_all()


def history_months() -> list:
    """From the oldest fixed expense (or 6 months back) to 12 months ahead."""
    cur = get_current_month()
    starts = [str(fe.get("fecha_inicio"))[:7] for fe in all_fe if fe.get("fecha_inicio")]
    first = min(starts + [add_months(cur, -6)])
    return month_range(first, add_months(cur, 12))


def acc_label_for(acc_id) -> str:
    acc = account_lookup.get(acc_id)
    if not acc:
        return "Cuenta eliminada"
    return f"{bank_lookup.get(acc.get('bank_id'), 'Unknown Bank')} - {acc.get('nombre', 'Unknown Account')}"

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
            
            es_propio = st.checkbox("Gasto Propio", value=False, help="Este gasto fijo pertenece a esta cuenta pero debe ser reembolsado desde la cuenta principal.")
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
                        account_id=selected_acc['id'],
                        es_propio=es_propio
                    )
                    fe_srv.add(new_fe.to_dict())
                    st.success("Fixed Expense added successfully!")
                    st.rerun()

st.divider()
st.subheader("Manage Monthly Payments")

# Month Selector
months = history_months()
# Use a session state to remember selected month or current
if 'fe_month' not in st.session_state:
    st.session_state['fe_month'] = get_current_month()

selected_month = st.selectbox("Select Month", months, index=months.index(st.session_state['fe_month']) if st.session_state['fe_month'] in months else months.index(get_current_month()))
st.session_state['fe_month'] = selected_month

# List active fixed expenses for the selected month
active_fes = get_fixed_expenses_for_month(selected_month)

if active_fes:
    st.write(f"Fixed Expenses for **{selected_month}**:")
    for fe in active_fes:
        col1, col2, col3, col4, col5, col6 = st.columns([3, 2, 3, 2, 2, 2])
        col1.markdown(f"**{fe['nombre']}**")

        display_amount = fe.get('monto_pagado') if fe.get('monto_pagado') is not None else fe['monto']
        col2.write(format_currency(display_amount))

        account = account_lookup.get(fe.get('account_id'))
        if account:
            bank_name = bank_lookup.get(account.get('bank_id'), 'Unknown Bank')
            account_label = f"{bank_name} - {account.get('nombre', 'Unknown Account')}"
        else:
            account_label = "Deleted account"
        col3.caption(f"Debited from: {account_label}")

        estado = fe['estado']
        color = "green" if estado == "pagado" else "red"
        col4.markdown(f":{color}[{estado.upper()}]")

        amount_key = f"paid_amount_{fe['id']}_{selected_month}"
        default_amount = float(fe.get('monto_pagado') if fe.get('monto_pagado') is not None else fe['monto'])
        min_paid_amount = min(0.0, default_amount)
        paid_amount = col5.number_input(
            "Paid Amount",
            min_value=min_paid_amount,
            value=default_amount,
            step=100.0,
            key=amount_key,
            label_visibility="collapsed"
        )

        btn_label = "Mark Unpaid" if estado == "pagado" else "Mark Paid"

        if col6.button(btn_label, key=f"toggle_{fe['id']}_{selected_month}"):
            # Check if an instance already exists
            instances = fei_srv.get_by_field("fixed_expense_id", "==", fe['id'])
            inst = next((i for i in instances if i['mes'] == selected_month), None)

            new_estado = "impagado" if estado == "pagado" else "pagado"

            if inst:
                inst_id = inst['id']
                update_data = {"estado": new_estado}
                if new_estado == "pagado":
                    update_data["monto"] = float(paid_amount)
                else:
                    update_data["monto"] = None
                fei_srv.update(inst_id, update_data)
            else:
                new_inst = FixedExpenseInstance(
                    fixed_expense_id=fe['id'],
                    mes=selected_month,
                    estado=new_estado,
                    monto=float(paid_amount) if new_estado == "pagado" else None
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
            monto = st.number_input("Importe inicial", value=float(fe.get("monto", 0.0)), step=100.0,
                                    help="Corrige el importe desde el inicio (todo el histórico). "
                                         "Para una subida a partir de un mes usa 'Cambiar importe' en la lista.")
            
            current_acc_id = fe.get("account_id")
            acc_labels = [a['label'] for a in acc_options]
            acc_index = next((i for i, a in enumerate(acc_options) if a['id'] == current_acc_id), 0)
            account_label = st.selectbox("Cuenta inicial", acc_labels, index=acc_index,
                                         help="Corrige la cuenta desde el inicio (todo el histórico). "
                                              "Para cambiarla a partir de un mes usa 'Cambiar importe/cuenta'.")
            selected_acc = next((a for a in acc_options if a['label'] == account_label), None)
            
        with col2:
            fecha_inicio = st.date_input("Start Date", value=fe.get("fecha_inicio", date.today()), format="DD/MM/YYYY")
            current_end = fe.get("fecha_fin")
            has_end_date = st.checkbox("Has End Date?", value=current_end is not None, key=f"he_{fe['id']}")
            fecha_fin = st.date_input("End Date", value=current_end if current_end else date.today(), format="DD/MM/YYYY") if has_end_date else None
        
        es_propio = st.checkbox("Gasto Propio", value=fe.get("es_propio", False), key=f"propio_{fe['id']}", help="Este gasto fijo pertenece a esta cuenta pero debe ser reembolsado desde la cuenta principal.")
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
                    "account_id": selected_acc['id'],
                    "es_propio": es_propio
                })
                st.success("Fixed Expense updated successfully!")
                st.rerun()
            else:
                st.error("Please fill in the expense name.")

def _month_end(month: str) -> datetime:
    y, m = map(int, month.split("-"))
    return datetime(y, m, monthrange(y, m)[1])


@st.dialog("Eliminar gasto fijo")
def delete_fe_dialog(fe):
    paid = [i for i in fei_srv.get_by_field("fixed_expense_id", "==", fe["id"]) if i.get("estado") == "pagado"]
    if paid:
        st.warning(
            f"**{fe['nombre']}** tiene {len(paid)} pago(s) registrados. Si lo borras, esos pagos dejan de "
            "contar y **cambian tus saldos reales y el arrastre de todos los meses pasados**."
        )
        st.write("Lo normal es **finalizarlo**: deja de aplicarse a partir del mes siguiente y conserva la historia.")
        months = history_months()
        last = st.selectbox("Último mes en que se paga", months, index=months.index(get_current_month()))
        if st.button("Finalizar", type="primary", width="stretch"):
            fe_srv.update(fe["id"], {"fecha_fin": _month_end(last)})
            st.rerun()
        st.divider()
        confirm = st.checkbox("Entiendo que borrar altera el histórico")
        if st.button("Borrar igualmente", disabled=not confirm, width="stretch"):
            fe_srv.delete(fe["id"])
            st.rerun()
    else:
        st.write(f"¿Borrar **{fe['nombre']}**? No tiene pagos registrados, así que no altera saldos pasados.")
        if st.button("Borrar", type="primary", width="stretch"):
            fe_srv.delete(fe["id"])
            st.rerun()


@st.dialog("Cambiar importe o cuenta")
def change_dialog(fe):
    st.write(f"**{fe['nombre']}**: el cambio se aplica desde el mes elegido. Los meses anteriores no cambian.")
    months = history_months()
    desde = st.selectbox("A partir de", months, index=months.index(get_current_month()))
    actual_monto = fixed_amount_for_month(fe, desde)
    actual_acc = fixed_account_for_month(fe, desde)
    nuevo = st.number_input("Importe mensual", value=float(actual_monto), step=10.0)
    if actual_monto and nuevo != actual_monto:
        st.caption(f"Antes {format_currency(actual_monto)} → variación {((nuevo - actual_monto) / actual_monto) * 100:+.1f} %")
    acc_ids = [a["id"] for a in acc_options]
    nueva_cuenta = st.selectbox(
        "Cuenta de cargo", acc_ids, format_func=acc_label_for,
        index=acc_ids.index(actual_acc) if actual_acc in acc_ids else 0,
    )
    if st.button("Aplicar", type="primary", width="stretch"):
        rev = {"desde": desde}
        if nuevo != actual_monto:
            rev["monto"] = float(nuevo)
        if nueva_cuenta != actual_acc:
            rev["account_id"] = nueva_cuenta
            rev["bank_id"] = account_lookup.get(nueva_cuenta, {}).get("bank_id")
        if len(rev) == 1:
            st.warning("No has cambiado ni el importe ni la cuenta.")
            return
        revs = fe.get("revisiones") or []
        same = next((r for r in revs if r["desde"] == desde), None)
        others = [r for r in revs if r["desde"] != desde]
        merged = {**(same or {}), **rev}      # a revision in the same month keeps its other field
        fe_srv.update(fe["id"], {"revisiones": sorted(others + [merged], key=lambda r: r["desde"])})
        st.rerun()


def _history_rows(fe):
    start = str(fe.get("fecha_inicio"))[:7]
    monto, acc = fe.get("monto", 0.0), fe.get("account_id")
    rows = [{"Desde": start, "Importe": format_currency(monto), "Variación": "", "Cuenta": acc_label_for(acc)}]
    for r in sorted(fe.get("revisiones") or [], key=lambda r: r["desde"]):
        var = ""
        if r.get("monto") is not None:
            var = f"{((r['monto'] - monto) / monto) * 100:+.1f} %" if monto else ""
            monto = r["monto"]
        acc_changed = r.get("account_id") is not None and r["account_id"] != acc
        if r.get("account_id") is not None:
            acc = r["account_id"]
        rows.append({"Desde": r["desde"], "Importe": format_currency(monto), "Variación": var,
                     "Cuenta": f"→ {acc_label_for(acc)}" if acc_changed else acc_label_for(acc)})
    return rows


def _is_finished(fe, current_m) -> bool:
    return bool(fe.get("fecha_fin")) and str(fe["fecha_fin"])[:7] < current_m


st.divider()
st.subheader("All Fixed Expenses Definition")
if all_fe:
    current_m = get_current_month()
    finished = [fe for fe in all_fe if _is_finished(fe, current_m)]
    show_finished = st.toggle(f"Mostrar finalizados ({len(finished)})", value=False) if finished else False
    visible = [fe for fe in all_fe if show_finished or not _is_finished(fe, current_m)]
    for fe in sorted(visible, key=lambda f: (_is_finished(f, current_m), f.get("nombre", ""))):
        with st.container(border=True):
            c1, c2, c3, c4, c5, c6 = st.columns([3, 2, 3, 1.6, 1, 1])
            c1.write(f"**{fe['nombre']}**" + (" · *finalizado*" if _is_finished(fe, current_m) else ""))
            c1.caption(acc_label_for(fixed_account_for_month(fe, current_m)))
            revs = fe.get("revisiones") or []
            c2.write(format_currency(fixed_amount_for_month(fe, current_m)))
            if revs:
                c2.caption(f"Inicial {format_currency(fe.get('monto', 0.0))} · {len(revs)} cambio(s)")

            start_d = str(fe.get('fecha_inicio'))[:10]
            end_d = str(fe.get('fecha_fin'))[:10] if fe.get('fecha_fin') else 'Ongoing'
            c3.write(f"Period: {start_d} to {end_d}")

            if c4.button("Cambiar importe/cuenta", key=f"chg_fe_{fe['id']}"):
                change_dialog(fe)
            if c5.button("Edit", key=f"edit_fe_{fe['id']}"):
                edit_fe_dialog(fe, acc_options)
            if c6.button("Delete", key=f"del_fe_{fe['id']}"):
                delete_fe_dialog(fe)

            if revs:
                with st.expander("Historial"):
                    st.dataframe(_history_rows(fe), hide_index=True, width="stretch")
                    for r in sorted(revs, key=lambda r: r["desde"]):
                        if st.button(f"Quitar cambio de {r['desde']}", key=f"rmrev_{fe['id']}_{r['desde']}"):
                            fe_srv.update(fe["id"], {"revisiones": [x for x in revs if x["desde"] != r["desde"]]})
                            st.rerun()
    if not visible:
        st.info("Todos los gastos fijos están finalizados.")
else:
    st.info("No fixed expenses defined.")
