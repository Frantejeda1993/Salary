"""
Streamlit-facing finance API.

All business logic lives in services.finance_core (pure, tested). This module
only wires it to the cached Firestore data and the real clock, and caches the
results with st.cache_data. Function names/signatures are kept so the pages
and the cache invalidation in firestore_service keep working unchanged.
"""
import streamlit as st

from services.data_cache import load_all_data
from services.finance_core import FinanceCore, MIN_MANAGED_MONTH  # noqa: F401 (re-export)
from utils.date_utils import get_current_month


def _core() -> FinanceCore:
    return FinanceCore(load_all_data(), get_current_month())


_cached = st.cache_data(ttl=120, show_spinner=False)


@_cached
def calculate_salary_net(salary_id: str, month: str) -> float:
    return _core().salary_net(salary_id, month)


@_cached
def get_active_budgets(month: str) -> list:
    return _core().active_budgets(month)


@_cached
def get_fixed_expenses_for_month(month: str) -> list:
    return _core().fixed_expenses_for_month(month)


@_cached
def calculate_category_spending(month: str, account_id: str = None) -> dict:
    return _core().category_spending(month, account_id)


@_cached
def _calculate_raw_category_expenses(month: str, account_id: str | None = None) -> dict:
    return _core().raw_category_expenses(month, account_id)


@_cached
def get_pending_loans_for_account(account_id: str, month: str = None) -> list:
    return _core().pending_loans_for_account(account_id, month)


@_cached
def get_propio_expenses_by_account(month: str, main_account_id: str) -> dict:
    return _core().propio_expenses_by_account(month, main_account_id)


@_cached
def calculate_month_real_result(account_id: str, month: str) -> float:
    return _core().month_real_result(account_id, month)


@_cached
def calculate_month_projected_result(account_id: str, month: str, remaining_from_previous_month: float = 0.0) -> dict:
    return _core().month_projected_result(account_id, month, remaining_from_previous_month)


@_cached
def get_remaining_from_previous_month(month: str, main_account_id: str) -> float:
    return _core().remaining_from_previous_month(month, main_account_id)


@_cached
def _get_account_historical_salary_incomes(account_id: str, up_to_month: str = None) -> float:
    return _core().historical_salary_incomes(account_id, up_to_month)


@_cached
def calculate_real_balance(account_id: str, month: str | None = None) -> float:
    return _core().real_balance(account_id, month)


@_cached
def calculate_projected_balance(account_id: str, month: str | None = None) -> dict:
    return _core().projected_balance(account_id, month)


@_cached
def get_month_summary(month: str) -> dict:
    return _core().month_summary(month)


@_cached
def get_credit_groups() -> list:
    return _core().credit_groups()


@_cached
def calculate_credit_outstanding(account_id: str, month: str, reserved_only: bool = True) -> float:
    return _core().credit_outstanding(account_id, month, reserved_only)


@_cached
def get_salary_breakdown(salary_id: str, month: str) -> dict:
    return _core().salary_breakdown(salary_id, month)


@_cached
def get_pending_obligations(month: str) -> list:
    return _core().pending_obligations(month)


@_cached
def get_pending_loans_impact(account_id: str) -> dict:
    return _core().pending_loans_impact(account_id)
