from datetime import date
from typing import Optional
from enum import Enum

class DayCountBasis(Enum):
    ACT_ACT = "ACT_ACT"  # 365/366
    THIRTY_360 = "30/360"
    THIRTY_E_360 = "30E/360"
    THIRTY_EP_360 = "30E+/360"

def date_diff_days(d1: date, d2: date, basis: DayCountBasis = DayCountBasis.ACT_ACT) -> int:
    """Возвращает разницу между двумя датами в днях согласно выбранному базису."""
    if basis == DayCountBasis.ACT_ACT:
        return (d1 - d2).days

    # Базисы 30/360
    y1, m1, d1_val = d2.year, d2.month, d2.day
    y2, m2, d2_val = d1.year, d1.month, d1.day

    if basis == DayCountBasis.THIRTY_360:
        if d1_val == 31:
            d1_val = 30
        if d2_val == 31 and d1_val >= 30:
            d2_val = 30
    elif basis == DayCountBasis.THIRTY_E_360:
        if d1_val == 31:
            d1_val = 30
        if d2_val == 31:
            d2_val = 30
    elif basis == DayCountBasis.THIRTY_EP_360:
        if d1_val == 31:
            d1_val = 30
        if d2_val == 31:
            d2_val = 1
            m2 += 1
            if m2 > 12:
                m2 = 1
                y2 += 1

    return (d2_val - d1_val) + 30 * (m2 - m1) + 360 * (y2 - y1)

def is_last_period(calc_date: date, next_coupon_date: date, mat_date: Optional[date]) -> bool:
    """Проверка, является ли текущий период последним перед погашением."""
    if mat_date is None:
        return False
    return next_coupon_date >= mat_date or (mat_date - calc_date).days <= 365
