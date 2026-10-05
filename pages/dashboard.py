"""
Dashboard: answers four questions with the engine's own logic (main account).
  1. How will this month close?          (projected vs real, carry-over, deficit)
  2. What is still to be paid?            (fixed expenses, card debt, reimbursements, loans)
  3. Am I on pace with my budgets?        (linear end-of-month forecast)
  4. Where am I heading?                  (closing result: past = real, future = projected)
"""
from calendar import monthrange
from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from services.finance_core import FinanceCore, add_months
from services.finance_engine import (
    _calculate_raw_category_expenses,
    calculate_credit_outstanding,
    calculate_real_balance,
    get_active_budgets,
    get_month_summary,
    get_min_managed_month,
    get_pending_obligations,
)
from services.firestore_service import FirestoreService, clear_firestore_read_caches
from utils.date_utils import get_current_month
from utils.money_utils import format_currency

st.title("📊 Dashboard")
if st.button("🔄 Refresh Data"):
    clear_firestore_read_caches()
    st.rerun()

accounts = FirestoreService("accounts").get_all()
categories = {c["id"]: c["nombre"] for c in FirestoreService("categories").get_all()}
acc_name = {a["id"]: a.get("nombre", "Cuenta") for a in accounts}
main = next((a for a in accounts if a.get("is_main")), None)
if not main:
    st.warning("Marca una cuenta como principal en **Configuration → Accounts** para ver el dashboard.")
    st.stop()

today = date.today()
cur = get_current_month()
summary = get_month_summary(cur)
carry = summary["remaining_from_previous_month"]
projected = summary["resultado_proyectado"]
pre_abs = summary["resultado_proyectado_pre_absorcion"]
obligations = get_pending_obligations(cur)
pending_total = sum(o["monto"] for o in obligations)

# ---------------------------------------------------------------- 1. This month
st.subheader(f"Este mes ({cur})")
k1, k2, k3, k4 = st.columns(4)
k1.metric("Cierre previsto", format_currency(projected),
          help="Resultado proyectado de la cuenta principal: lo que te quedará a fin de mes "
               "si gastas todos los presupuestos y pagas lo pendiente.")
k2.metric("Ahorro previsto del mes", format_currency(projected - carry),
          delta=f"sobre {format_currency(carry)} arrastrados", delta_color="off",
          help="Lo que este mes suma (o resta) a lo que traías del anterior.")
k3.metric("Real hoy", format_currency(summary["resultado_real"]),
          help="Dinero que realmente ha entrado menos lo que ha salido, más el arrastre.")
k4.metric("Pendiente de pagar", format_currency(pending_total))

if pre_abs < 0:
    covered = projected - pre_abs
    st.error(
        f"Con todos los presupuestos gastados cerrarías en **{format_currency(pre_abs)}**. "
        f"El proyectado lo compensa asumiendo que dejas de gastar **{format_currency(covered)}** "
        "de presupuesto. Eso no es ahorro: es gasto que tienes que recortar de verdad."
    )

total_cash = sum(calculate_real_balance(a["id"], cur) for a in accounts)
total_card = sum(calculate_credit_outstanding(a["id"], cur, False) for a in accounts)
st.caption(f"Saldo en cuentas: {format_currency(total_cash)}"
           + (f" · deuda de tarjeta: {format_currency(-total_card)} → neto {format_currency(total_cash - total_card)}"
              if total_card else ""))

# ---------------------------------------------------------------- 2. Pending
st.divider()
st.subheader("Pendiente este mes")
if obligations:
    df = pd.DataFrame([{
        "Tipo": o["tipo"], "Concepto": o["concepto"],
        "Cuenta": acc_name.get(o["account_id"], "—"), "Importe": o["monto"],
    } for o in sorted(obligations, key=lambda o: -o["monto"])])
    st.dataframe(df.assign(Importe=df["Importe"].map(format_currency)), hide_index=True, width="stretch")
    st.caption("Se gestiona en Fixed Expenses (pagos) y en Monthly View (tarjeta y reembolsos).")
else:
    st.success("Nada pendiente este mes.")

# ---------------------------------------------------------------- 3. Budget pace
st.divider()
st.subheader("Ritmo de presupuestos")
days = monthrange(today.year, today.month)[1]
budgets = get_active_budgets(cur)
if budgets:
    st.caption(f"Día {today.day} de {days}: llevas el {today.day / days:.0%} del mes.")
    icon = {"ok": "🟢", "por encima del ritmo": "🟠", "excedido": "🔴"}
    for b in sorted(budgets, key=lambda b: categories.get(b["categoria_id"], "")):
        used = max(_calculate_raw_category_expenses(cur, b["account_id"]).get(b["categoria_id"], 0.0), 0.0)
        pace = FinanceCore.budget_pace(used, b["monto"], today.day, days)
        c1, c2 = st.columns([3, 2])
        c1.write(f"{icon[pace['status']]} **{categories.get(b['categoria_id'], '?')}** · "
                 f"{format_currency(used)} de {format_currency(b['monto'])}")
        c1.progress(min(pace["used_pct"], 1.0))
        if pace["status"] == "ok":
            c2.caption(f"A este ritmo: {format_currency(pace['forecast'])}. Margen {format_currency(b['monto'] - used)}.")
        elif pace["status"] == "por encima del ritmo":
            per_day = (b["monto"] - used) / max(days - today.day, 1)
            c2.caption(f"A este ritmo acabarías en {format_currency(pace['forecast'])}. "
                       f"Para no pasarte: máx. {format_currency(per_day)}/día.")
        else:
            c2.caption(f"Excedido en {format_currency(used - b['monto'])}: sale directamente del cierre previsto.")
else:
    st.info("No hay presupuestos activos este mes.")

# ---------------------------------------------------------------- 4. Trajectory
st.divider()
st.subheader("Hacia dónde vas")
start = max(add_months(cur, -6), add_months(get_min_managed_month(), 1))
months = [add_months(start, i) for i in range(0, 13) if add_months(start, i) <= add_months(cur, 6)]
rows = []
for m in months:
    s = get_month_summary(m)
    closing = s["resultado_real"] if m < cur else s["resultado_proyectado"]
    rows.append({"Mes": m, "Cierre": closing, "Variación": closing - s["remaining_from_previous_month"],
                 "Tipo": "Real" if m < cur else "Proyectado"})
traj = pd.DataFrame(rows)

fig = go.Figure()
fig.add_bar(x=traj["Mes"], y=traj["Variación"], name="Ahorro del mes",
            marker_color=["#21c354" if v >= 0 else "#ff4b4b" for v in traj["Variación"]],
            marker_pattern_shape=["" if t == "Real" else "/" for t in traj["Tipo"]])
fig.add_scatter(x=traj["Mes"], y=traj["Cierre"], name="Cierre acumulado", mode="lines+markers",
                line=dict(width=3))
if cur in months:
    fig.add_vline(x=months.index(cur) - 0.5, line_dash="dot", opacity=0.5)
fig.update_layout(height=380, margin=dict(l=10, r=10, t=10, b=10), legend=dict(orientation="h"),
                  yaxis_tickformat=",.0f")
st.plotly_chart(fig, width="stretch")
st.caption("Barras lisas = real (meses cerrados). Rayadas = proyectado. La línea es lo que acumulas al cierre de cada mes.")

future = traj[traj["Tipo"] == "Proyectado"]
neg = future[future["Cierre"] < 0]
if not neg.empty:
    st.error(f"El cierre proyectado pasa a negativo en **{neg.iloc[0]['Mes']}** "
             f"({format_currency(neg.iloc[0]['Cierre'])}).")
elif not future.empty:
    last = future.iloc[-1]
    st.info(f"Si todo sigue igual, en **{last['Mes']}** cerrarás con **{format_currency(last['Cierre'])}**.")

# ---------------------------------------------------------------- 5. Category deviation
st.divider()
st.subheader("Gasto por categoría vs. media de los 3 meses anteriores")
def _spend(month):
    tot = {}
    for a in accounts:
        for cat, v in _calculate_raw_category_expenses(month, a["id"]).items():
            tot[cat] = tot.get(cat, 0.0) + v
    return tot
now = _spend(cur)
prev = [_spend(add_months(cur, -i)) for i in (1, 2, 3)]
cats = set(now) | set().union(*prev)
dev = []
for c in cats:
    avg = sum(p.get(c, 0.0) for p in prev) / 3
    dev.append({"Categoría": categories.get(c, "Sin categoría"), "Este mes": now.get(c, 0.0), "Media 3m": avg})
if dev:
    dev = pd.DataFrame(dev).sort_values("Este mes", ascending=False)
    fig2 = go.Figure()
    fig2.add_bar(y=dev["Categoría"], x=dev["Media 3m"], name="Media 3 meses", orientation="h", opacity=0.45)
    fig2.add_bar(y=dev["Categoría"], x=dev["Este mes"], name=f"{cur} (hasta hoy)", orientation="h")
    fig2.update_layout(barmode="overlay", height=max(220, 40 * len(dev)), margin=dict(l=10, r=10, t=10, b=10),
                       legend=dict(orientation="h"), yaxis=dict(autorange="reversed"))
    st.plotly_chart(fig2, width="stretch")
    st.caption("Ojo: el mes en curso está incompleto; compáralo con el ritmo de arriba, no con el total.")
else:
    st.info("Aún no hay gastos registrados.")
