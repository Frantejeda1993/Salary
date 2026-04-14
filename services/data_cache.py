import streamlit as st

from services.firestore_service import FirestoreService


@st.cache_data(ttl=120, show_spinner=False)
def load_all_data() -> dict:
    """Fetches every collection once per cache window."""
    return {
        "accounts": FirestoreService("accounts").get_all(),
        "banks": FirestoreService("banks").get_all(),
        "salaries": FirestoreService("salaries").get_all(),
        "overtimes": FirestoreService("overtimes").get_all(),
        "expenses": FirestoreService("expenses").get_all(),
        "incomes": FirestoreService("incomes").get_all(),
        "transfers": FirestoreService("transfers").get_all(),
        "categories": FirestoreService("categories").get_all(),
        "budgets": FirestoreService("budgets").get_all(),
        "fixed_expenses": FirestoreService("fixed_expenses").get_all(),
        "fixed_expense_instances": FirestoreService("fixed_expense_instances").get_all(),
        "monthly_account_snapshots": FirestoreService("monthly_account_snapshots").get_all(),
    }


def clear_data_cache():
    load_all_data.clear()
