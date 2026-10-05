"""
Characterization test: the refactored core must reproduce the pre-refactor
engine (snapshot of finance_engine.py at PR #97) exactly, on 150 random datasets.
Once you've merged and checked the app, delete this file and tests/legacy/.
"""
import importlib.util, os, pytest
from tests.fixtures import random_dataset
from services.finance_core import FinanceCore

LEGACY = os.environ.get(
    "LEGACY_ENGINE", os.path.join(os.path.dirname(__file__), "legacy", "finance_engine_pr97.py")
)
pytestmark = pytest.mark.skipif(not os.path.exists(LEGACY), reason="legacy engine not provided")

MONTHS = [f"2026-{m:02d}" for m in range(1, 13)]


def _load_legacy():
    spec = importlib.util.spec_from_file_location("legacy_engine", LEGACY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _clear(mod):
    for name in dir(mod):
        fn = getattr(mod, name)
        if hasattr(fn, "clear") and callable(fn):
            fn.clear()


def _close(a, b):
    if isinstance(a, dict):
        # new code may add keys; every legacy key must match
        return set(b) <= set(a) and all(_close(a[k], b[k]) for k in b)
    if isinstance(a, list):
        return len(a) == len(b) and all(_close(x, y) for x, y in zip(a, b))
    if isinstance(a, float) or isinstance(b, float):
        return abs(a - b) < 1e-6
    return a == b


@pytest.mark.parametrize("seed", range(150))
def test_core_matches_legacy(seed):
    legacy = _load_legacy()
    data = random_dataset(seed)
    current = MONTHS[seed % 12]
    legacy.load_all_data = lambda: data
    legacy.get_current_month = lambda: current
    _clear(legacy)
    core = FinanceCore(data, current)
    for m in MONTHS:
        assert _close(core.month_summary(m), legacy.get_month_summary(m)), m
        for acc in ["main", "acc2", "acc3"]:
            assert _close(core.real_balance(acc, m), legacy.calculate_real_balance(acc, m))
            assert _close(core.projected_balance(acc, m), legacy.calculate_projected_balance(acc, m))
            assert _close(core.month_real_result(acc, m), legacy.calculate_month_real_result(acc, m))
            assert _close(core.month_projected_result(acc, m, 37.5),
                          legacy.calculate_month_projected_result(acc, m, 37.5))
        assert _close(core.propio_expenses_by_account(m, "main"), legacy.get_propio_expenses_by_account(m, "main"))
