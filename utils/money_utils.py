def format_currency(amount: float) -> str:
    """Formats a float as a currency string in European format (e.g., 1.234,56 €)."""
    s = f"{amount:,.2f}"
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{s} €"

def format_percentage(amount: float) -> str:
    """Formats a float as a percentage string (e.g., 12,34 %)."""
    s = f"{amount:,.2f}"
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{s} %"
