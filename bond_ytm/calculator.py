from datetime import date
import structlog
from typing import Optional, List
from .fetcher import DataFetcher
from .models import BondMarketData, Coupon, Amortization, CalculationResult, CashFlow
from .cashflows import CashFlowBuilder
from .solver import YTMSolver
from .config import config
from .exceptions import (
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

    def _calculate_ytm(self, flows: List[CashFlow], dirty_price: float, calc_date: date, mat_date: Optional[date], year_basis: int) -> Optional[float]:
        """Вспомогательный метод для выбора формулы и расчёта доходности."""
        if not flows or dirty_price <= 0:
            return None
            
        # Обновляем базис в солвере перед расчетом
        self.solver.basis = year_basis
        
        next_coupon_date = flows[0].date
        if is_last_period(calc_date, next_coupon_date, mat_date):
            return self.solver.solve_simple(dirty_price, flows, calc_date)
        return self.solver.solve(dirty_price, flows, calc_date)

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
            
            # Извлекаем данные из securities и marketdata
            securities_block = next((b["securities"] for b in raw_market_data if "securities" in b), [])
            marketdata_block = next((b["marketdata"] for b in raw_market_data if "marketdata" in b), [])
            
            if not securities_block:
                raise NoMarketDataError(f"Не удалось получить данные securities для {secid} на {board}")
            
            # Объединяем данные (приоритет у marketdata для BID/OFFER)
            m_data_dict = securities_block[0].copy()
            if marketdata_block:
                m_data_dict.update(marketdata_block[0])
            
            m_data = BondMarketData(**m_data_dict)
            
            # 3. Валидация возможности расчёта (особые случаи МОЭКС)
            if m_data.status != 'A':
                return CalculationResult(secid=secid, dirty_price=0, accrued_interest=0, error_reason="Бумага не в активном статусе")
            
            # Проверка НКД (если не рассчитывается - доходность не считается)
            if m_data.accruedint is None:
                return CalculationResult(secid=secid, dirty_price=0, accrued_interest=0, error_reason="НКД не рассчитывается для данной бумаги")

            # Проверка ОФЗ с особыми формулами НКД (8 и 9)
            # Обычно это ОФЗ-ИН (инфляционные) и старые ОФЗ-ПК (переменный купон)
            # В данных ISS это можно определить по SECTYPE или паттерну в названии
            if m_data.sectype in ['3', '4'] or (m_data.shortname and ("ОФЗ-ИН" in m_data.shortname or "ОФЗ-ПК" in m_data.shortname)):
                logger.warning("unsupported_ofz_formula", secid=secid, sectype=m_data.sectype)
                return CalculationResult(secid=secid, dirty_price=0, accrued_interest=0, error_reason="ОФЗ с формулами НКД 8 или 9 не поддерживаются")

            # Режим Д (Облигации Д — Режим основных торгов)
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

            # 6. Определение цен и расчёт доходностей
            effective_nominal = nominal if nominal is not None else m_data.facevalue
            year_basis = m_data.yearbasis or config.DEFAULT_YEAR_BASIS
            
            # Основная доходность (по цене закрытия или переданной цене)
            current_price = price if price is not None else m_data.price
            ytm = None
            dirty_price = 0.0
            if current_price:
                dirty_price = (current_price * effective_nominal / 100.0) + (m_data.accruedint or 0.0)
                ytm = self._calculate_ytm(flows, dirty_price, calc_date, m_data.matdate, year_basis)

            # Доходность по BID (покупка)
            ytm_bid = None
            if m_data.bid:
                dirty_bid = (m_data.bid * effective_nominal / 100.0) + (m_data.accruedint or 0.0)
                ytm_bid = self._calculate_ytm(flows, dirty_bid, calc_date, m_data.matdate, year_basis)

            # Доходность по OFFER (продажа)
            ytm_offer = None
            if m_data.offer:
                dirty_offer = (m_data.offer * effective_nominal / 100.0) + (m_data.accruedint or 0.0)
                ytm_offer = self._calculate_ytm(flows, dirty_offer, calc_date, m_data.matdate, year_basis)

            # Если цена не задана и нет рыночной цены, но есть bid/offer
            if not current_price:
                if ytm_bid: ytm = ytm_bid
                elif ytm_offer: ytm = ytm_offer

            warning = None
            if flows and is_last_period(calc_date, flows[0].date, m_data.matdate):
                warning = "Использована формула простой доходности (последний период)"

            return CalculationResult(
                secid=secid,
                ytm_percent=ytm,
                ytm_bid_percent=ytm_bid,
                ytm_offer_percent=ytm_offer,
                dirty_price=round(dirty_price, 4),
                accrued_interest=m_data.accruedint or 0.0,
                cashflows=flows,
                year_basis=year_basis,
                coupon_rate_calculated=m_data.couponpercent,
                warning=warning
            )

        except (DataFetchError, NoMarketDataError) as e:
            logger.error("calculation_fetch_error", secid=secid, error=str(e))
            return CalculationResult(secid=secid, dirty_price=0, accrued_interest=0, error_reason=str(e))
        except Exception as e:
            logger.exception("unexpected_calculation_error", secid=secid, error=str(e))
            return CalculationResult(secid=secid, dirty_price=0, accrued_interest=0, error_reason=f"Внутренняя ошибка: {e}")
