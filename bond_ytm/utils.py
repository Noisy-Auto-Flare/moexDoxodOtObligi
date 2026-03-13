from datetime import date
from typing import Optional

def date_diff_days(d1: date, d2: date) -> int:
    """Возвращает разницу между двумя датами в днях."""
    return (d1 - d2).days

def is_last_period(calc_date: date, next_coupon_date: date, mat_date: Optional[date]) -> bool:
    """Проверка, является ли текущий период последним перед погашением."""
    if mat_date is None:
        return False
    return next_coupon_date >= mat_date or (mat_date - calc_date).days <= 365
