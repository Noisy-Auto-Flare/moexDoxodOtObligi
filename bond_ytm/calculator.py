from datetime import date
import structlog
from typing import Optional, List, Dict, Any
from .fetcher import DataFetcher
from .models import BondMarketData, Coupon, Amortization, CalculationResult
from .cashflows import CashFlowBuilder
from .solver import YTMSolver
from .config import config
from .exceptions import (
    BondYTMError, 
    UnsupportedBondError, 
    NoMarketDataError,
    DataFetchError
)
from .utils import is_last_period

logger = structlog.get_logger(__name__)

class BondYieldCalculator:
    """Главный фасад для расчёта доходности облигаций МОЭКС."""

    def __init__(self, fetcher: Optional[DataFetcher] = None):
        self.fetcher = fetcher or DataFetcher()
        self.solver = YTMSolver(config.DEFAULT_YEAR_BASIS)

    def calculate(
        self, 
        secid: str, 
        board: Optional[str] = None, 
        calc_date: Optional[date] = None,
        price: Optional[float] = None,
        nominal: Optional[float] = None
    ) -> CalculationResult:
        """
        Основной метод расчёта доходности.
        
        Args:
            secid: Код бумаги (ISIN или SECID)
            board: Режим торгов (опционально, автоопределение если не задан)
            calc_date: Дата расчёта (по умолчанию сегодня)
            price: Чистая цена в % от номинала (опционально, берется из ISS если не задано)
            nominal: Номинал бумаги (опционально)
            
        Returns:
            CalculationResult: Объект с результатом расчёта или причиной ошибки
        """
        calc_date = calc_date or date.today()
        
        try:
            # 1. Автоопределение режима торгов
            if not board:
                board = self.fetcher.auto_detect_board(secid)
                logger.info("board_detected", secid=secid, board=board)
            
            # 2. Получение рыночных данных
            raw_market_data = self.fetcher.get_market_data(secid, board)
            if not raw_market_data or len(raw_market_data) < 2 or not raw_market_data[1].get("securities"):
                raise NoMarketDataError(f"Не удалось получить рыночные данные для {secid} на {board}")
            
            m_data_dict = raw_market_data[1]["securities"][0]
            m_data = BondMarketData(**m_data_dict)
            
            # 3. Валидация возможности расчёта (особые случаи МОЭКС)
            if m_data.status != 'A':
                return CalculationResult(secid=secid, dirty_price=0, accrued_interest=0, error_reason="Бумага не в активном статусе")
            
            # Режим Д (Облигации Д — Режим основных торгов) - часто не поддерживается в стандартных расчётах
            if board.startswith("TQOD") or board.startswith("TQUD"):
                 return CalculationResult(secid=secid, dirty_price=0, accrued_interest=0, error_reason="Режим торгов 'Облигации Д' не поддерживается")

            # 4. Получение данных о купонах и амортизациях
            bondization_data = self.fetcher.get_bondization(secid)
            coupons_list = bondization_data[1].get("coupons", [])
            amorts_list = bondization_data[1].get("amortizations", [])
            
            coupons = [Coupon(**c) for c in coupons_list]
            amortizations = [Amortization(**a) for a in amorts_list]

            # 5. Построение потоков платежей
            flows = CashFlowBuilder.build(m_data, coupons, amortizations, calc_date)
            
            if not flows:
                 # Если нет купонов и нет НКД - не считаем
                 if m_data.accruedint == 0 and not coupons:
                     return CalculationResult(secid=secid, dirty_price=0, accrued_interest=0, error_reason="Отсутствуют будущие потоки и НКД")
                 return CalculationResult(secid=secid, dirty_price=0, accrued_interest=0, error_reason="Нет будущих денежных потоков")

            # 6. Определение цены
            current_price = price if price is not None else m_data.price
            if current_price is None:
                return CalculationResult(secid=secid, dirty_price=0, accrued_interest=0, error_reason="Отсутствует цена для расчёта")

            # Грязная цена = (Чистая цена % * Номинал / 100) + НКД
            # Если номинал передан пользователем - используем его, иначе из ISS
            effective_nominal = nominal if nominal is not None else m_data.facevalue
            dirty_price = (current_price * effective_nominal / 100.0) + m_data.accruedint
            
            # 7. Расчёт доходности
            # Если до погашения менее года или это последний купон - простая доходность
            # В остальных случаях - сложная (YTM)
            next_coupon_date = flows[0].date
            if is_last_period(calc_date, next_coupon_date, m_data.matdate):
                ytm = self.solver.solve_simple(dirty_price, flows, calc_date)
                warning = "Использована формула простой доходности (последний период)"
            else:
                ytm = self.solver.solve(dirty_price, flows, calc_date)
                warning = None

            return CalculationResult(
                secid=secid,
                ytm_percent=ytm,
                dirty_price=round(dirty_price, 4),
                accrued_interest=m_data.accruedint,
                cashflows=flows,
                warning=warning
            )

        except (DataFetchError, NoMarketDataError) as e:
            logger.error("calculation_fetch_error", secid=secid, error=str(e))
            return CalculationResult(secid=secid, dirty_price=0, accrued_interest=0, error_reason=str(e))
        except Exception as e:
            logger.exception("unexpected_calculation_error", secid=secid, error=str(e))
            return CalculationResult(secid=secid, dirty_price=0, accrued_interest=0, error_reason=f"Внутренняя ошибка: {e}")
