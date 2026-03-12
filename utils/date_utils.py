from datetime import datetime, date
from dateutil.relativedelta import relativedelta

def get_current_month() -> str:
    """Returns the current month in YYYY-MM format."""
    return datetime.now().strftime("%Y-%m")

def format_month(dt: date) -> str:
    """Formats a date to YYYY-MM format."""
    return dt.strftime("%Y-%m")

def get_month_options() -> list:
    """Returns a list of month options around the current date."""
    current = datetime.now()
    months = []
    # 6 months back, 12 months forward
    start = current - relativedelta(months=6)
    for i in range(19):
        dt = start + relativedelta(months=i)
        months.append(dt.strftime("%Y-%m"))
    return months

def parse_month(month_str: str) -> date:
    """Parses a YYYY-MM string into a date object (first day of the month)."""
    return datetime.strptime(month_str, "%Y-%m").date()

def is_active_in_month(fecha_inicio: date, fecha_fin: date, month_str: str) -> bool:
    """Checks if a given date range overlaps with a specific month."""
    if not fecha_inicio:
        return False
        
    month_date = parse_month(month_str)
    
    # Check if start date is before or strictly in the same month
    start_is_valid = (fecha_inicio.year < month_date.year) or \
                     (fecha_inicio.year == month_date.year and fecha_inicio.month <= month_date.month)
                     
    if not start_is_valid:
        return False
        
    if fecha_fin is None:
        return True
        
    # Check if end date is after or strictly in the same month
    end_is_valid = (fecha_fin.year > month_date.year) or \
                   (fecha_fin.year == month_date.year and fecha_fin.month >= month_date.month)
                   
    return end_is_valid
