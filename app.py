import streamlit as st

st.set_page_config(
    page_title="Personal Finance App",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Navigation
pages = {
    "Overview": [
        st.Page("pages/dashboard.py", title="Dashboard", icon="📊"),
        st.Page("pages/monthly_view.py", title="Monthly View", icon="📅", default=True),
    ],
    "Transactions": [
        st.Page("pages/transactions.py", title="Expenses & Income", icon="💸"),
        st.Page("pages/transfers.py", title="Transfers", icon="🔄"),
    ],
    "Planning": [
        st.Page("pages/budgets.py", title="Budgets", icon="🎯"),
        st.Page("pages/fixed_expenses.py", title="Fixed Expenses", icon="📆"),
        st.Page("pages/salaries.py", title="Salaries", icon="💼"),
    ],
    "Configuration": [
        st.Page("pages/banks.py", title="Banks", icon="🏦"),
        st.Page("pages/accounts.py", title="Accounts", icon="💳"),
        st.Page("pages/categories.py", title="Categories", icon="📁"),
    ]
}

pg = st.navigation(pages)
pg.run()
