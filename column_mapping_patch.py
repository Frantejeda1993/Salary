"""
Reusable Streamlit form for resolving inventory input column mappings.
"""

from pathlib import Path
import json

import streamlit as st

from inventory_manager import ColumnMappingError


MARGIN_ALIASES_FILE = Path(".margin_column_aliases.json")
UNSELECTED_OPTION = "— seleccionar —"


def _load_margin_aliases() -> list[str]:
    if not MARGIN_ALIASES_FILE.exists():
        return []
    try:
        data = json.loads(MARGIN_ALIASES_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []
    return [str(item).strip() for item in data if str(item).strip()]


def _save_margin_aliases(aliases: list[str]) -> None:
    deduped = list(dict.fromkeys(alias.strip() for alias in aliases if alias.strip()))
    MARGIN_ALIASES_FILE.write_text(
        json.dumps(deduped, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def render_column_mapping_form(
    errors: list[ColumnMappingError],
    manager,
) -> bool:
    """
    Render the column-mapping resolution form.

    Shows one section per ColumnMappingError:
      - Already-resolved columns as read-only info.
      - Missing columns as selectboxes.
      - Available choices from each erring input's dataframe columns.

    Returns True if the form was submitted successfully and st.rerun() should
    be called by the caller.
    """
    st.warning(
        "⚠️ Algunas columnas no pudieron mapearse automáticamente. "
        "Revisa la asignación y haz clic en **Guardar y recalcular**."
    )

    with st.form("column_mapping_form"):
        all_selections: dict[str, dict[str, str]] = {}

        for cme in errors:
            st.subheader(f"📋 Input: {cme.input_name}")
            available_options = cme.available
            input_selections: dict[str, str] = dict(cme.resolved)

            if cme.resolved:
                st.markdown("**Columnas mapeadas automáticamente ✅**")
                for logical_name, actual_col in cme.resolved.items():
                    st.info(f"**{logical_name}** → `{actual_col}`")

            if cme.missing:
                st.markdown("**Columnas que necesitan asignación manual ⚠️**")
                for logical_name in cme.missing:
                    chosen = st.selectbox(
                        f"{logical_name}",
                        options=[UNSELECTED_OPTION, *available_options],
                        index=0,
                        key=f"mapping_{cme.input_name}_{logical_name}",
                    )
                    input_selections[logical_name] = chosen

            all_selections[cme.input_name] = input_selections
            st.divider()

        submitted = st.form_submit_button("💾 Guardar y recalcular", type="primary")

    if not submitted:
        return False

    still_missing = []
    errors_by_input = {cme.input_name: cme for cme in errors}
    for input_name, selections in all_selections.items():
        cme = errors_by_input[input_name]
        for logical_name in cme.missing:
            if selections.get(logical_name, UNSELECTED_OPTION) == UNSELECTED_OPTION:
                still_missing.append(f"{input_name} → {logical_name}")

    if still_missing:
        st.error("Debes seleccionar una columna para: " + ", ".join(still_missing))
        return False

    for input_name, selections in all_selections.items():
        overrides = st.session_state.setdefault("column_overrides", {}).setdefault(
            input_name, {}
        )
        overrides.update(
            {key: value for key, value in selections.items() if value != UNSELECTED_OPTION}
        )

        if input_name == "Ventas" and "Margen" in selections:
            margin_col = selections["Margen"]
            if margin_col and margin_col != UNSELECTED_OPTION:
                aliases = _load_margin_aliases()
                if margin_col not in aliases:
                    aliases.append(margin_col)
                    _save_margin_aliases(aliases)
                manager.set_extra_margin_aliases(_load_margin_aliases())

    return True
