import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

from services.finance_engine import (
    calculate_real_balance, 
    calculate_projected_balance,
    get_month_summary,
    get_active_budgets,
    calculate_category_spending
)
from services.firestore_service import FirestoreService
from utils.date_utils import get_month_options, get_current_month
from utils.money_utils import format_currency

st.title("📊 Financial Dashboard")

acc_srv = FirestoreService("accounts")
cat_srv = FirestoreService("categories")
accounts = acc_srv.get_all()

# --- TOP METRICS ---
total_real = sum(calculate_real_balance(a['id']) for a in accounts) if accounts else 0.0
total_proj = sum(calculate_projected_balance(a['id'])['resultado'] for a in accounts) if accounts else 0.0

col1, col2 = st.columns(2)
with col1:
    st.info(f"### Total Real Balance\n# {format_currency(total_real)}")
with col2:
    st.success(f"### Total Projected Balance\n# {format_currency(total_proj)}")
    
st.divider()

current_m = get_current_month()
st.subheader(f"Current Month Snapshot ({current_m})")

summary = get_month_summary(current_m)

# --- MONTHLY BUDGETS ---
st.write("#### Budgets Tracker")
budgets = get_active_budgets(current_m)
spending = calculate_category_spending(current_m)
categories = {c['id']: c['nombre'] for c in cat_srv.get_all()}

if budgets:
    for b in budgets:
        cat_name = categories.get(b['categoria_id'], 'Unknown')
        presupuesto = b['monto']
        gastado = spending.get(b['categoria_id'], 0.0)
        
        ratio = gastado / presupuesto if presupuesto > 0 else 0
        ratio_clamped = min(ratio, 1.0)
        
        # Color based on ratio
        if ratio > 1:
            color = "red"
            st.error(f"🚨 **{cat_name}** exceeded! Spent: {format_currency(gastado)} of {format_currency(presupuesto)}")
        elif ratio > 0.8:
            color = "orange"
            st.warning(f"⚠️ **{cat_name}** is close to limit. Spent: {format_currency(gastado)} of {format_currency(presupuesto)}")
        else:
            color = "green"
            st.write(f"**{cat_name}**: Spent {format_currency(gastado)} of {format_currency(presupuesto)}")
            
        st.progress(ratio_clamped)
else:
    st.info("No active budgets for this month.")

st.divider()

# --- CHARTS ---
col_c1, col_c2 = st.columns(2)

with col_c1:
    st.write("#### Spending by Category (Current Month)")
    if sum(spending.values()) > 0:
        spend_data = []
        for cat_id, val in spending.items():
            if val > 0:
                spend_data.append({"Category": categories.get(cat_id, "Unknown"), "Amount": val})
        df_spend = pd.DataFrame(spend_data)
        fig_pie = px.pie(df_spend, names="Category", values="Amount", hole=0.4)
        st.plotly_chart(fig_pie, use_container_width=True)
    else:
        st.write("No spending recorded this month.")

with col_c2:
    st.write("#### 6-Month Cash Flow Overview")
    months_opts = get_month_options()
    # Get last 6 months up to current
    idx = months_opts.index(current_m)
    last_6 = months_opts[max(0, idx-5):idx+1]
    
    flow_data = []
    for m in last_6:
        s = get_month_summary(m)
        total_in = s['ingreso_total'] + s['ingresos_extra']
        total_out = s['gastos_reales'] + s['gastos_fijos']
        flow_data.append({"Month": m, "Type": "Income", "Amount": total_in})
        flow_data.append({"Month": m, "Type": "Expense", "Amount": total_out})
        
    df_flow = pd.DataFrame(flow_data)
    fig_bar = px.bar(df_flow, x="Month", y="Amount", color="Type", barmode="group",
                    color_discrete_map={"Income": "green", "Expense": "red"})
    st.plotly_chart(fig_bar, use_container_width=True)
