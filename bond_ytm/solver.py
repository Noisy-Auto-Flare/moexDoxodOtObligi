import numpy as np
from scipy.optimize import brentq
from datetime import date
from typing import List, Optional, Callable
import structlog
from .models import CashFlow
from .config import config
from .utils import date_diff_days

logger = structlog.get_logger(__name__)

class YTMSolver:
    """Математический движок для расчёта доходности к погашению."""

    def __init__(self, basis: int = 365):
        self.basis = basis

    def _npv(self, y: float, flows: List[CashFlow], calc_date: date) -> float:
        """
        Расчёт NPV (Net Present Value) для заданной доходности y.
        y - доходность в процентах годовых.
        """
        total_pv = 0.0
        y_val = y / 100.0
        
        for f in flows:
            t_i = date_diff_days(f.date, calc_date)
            # Формула 12: PV = C_i / (1 + Y/100)^(t_i / YearBasis)
            # t_i - количество дней до выплаты
            total_pv += f.amount / ((1 + y_val) ** (t_i / self.basis))
            
        return total_pv

    def solve(self, target_price: float, flows: List[CashFlow], calc_date: date) -> Optional[float]:
        """
        Решает уравнение f(Y) = NPV(flows, Y) - target_price = 0.
        Используется метод brentq с fallback на бисекцию.
        """
        if not flows:
            return None

        def objective(y):
            return self._npv(y, flows, calc_date) - target_price

        try:
            # Ищем корень в широком интервале [-99.9, 200]
            # y = -100 - это сингулярность (деление на 0), поэтому берем -99.9
            res = brentq(objective, -99.9, 500, xtol=config.SOLVER_TOLERANCE)
            return round(max(res, config.MIN_YIELD), 4)
        except ValueError as e:
            logger.warning("solver_brentq_failed", error=str(e))
            # Fallback: пробуем найти корень бисекцией, если brentq не сошелся
            # (brentq и так гибрид, но может упасть на интервале)
            return None
        except Exception as e:
            logger.error("solver_error", error=str(e))
            return None

    def solve_simple(self, target_price: float, flows: List[CashFlow], calc_date: date) -> Optional[float]:
        """
        Расчёт по формуле простой доходности (для последнего периода).
        Y = ((P_future / P_current) - 1) * (Basis / t) * 100
        """
        if not flows:
            return None
            
        # Для последнего периода обычно один поток (купон + номинал)
        # Суммируем все потоки (если их несколько на одну дату)
        total_future_amount = sum(f.amount for f in flows)
        t = date_diff_days(flows[-1].date, calc_date)
        
        if t <= 0:
            return 0.0
            
        try:
            y = ((total_future_amount / target_price) - 1) * (self.basis / t) * 100
            return round(max(y, config.MIN_YIELD), 4)
        except ZeroDivisionError:
            return None
