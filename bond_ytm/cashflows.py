from datetime import date, timedelta
from typing import List, Optional, Dict, Any
import structlog
from .models import BondMarketData, Coupon, Amortization, CashFlow
from .config import config

logger = structlog.get_logger(__name__)

class CashFlowBuilder:
    """Класс для построения потоков платежей облигации."""

    @staticmethod
    def build(
        market_data: BondMarketData, 
        coupons: List[Coupon], 
        amortizations: List[Amortization],
        calc_date: date
    ) -> List[CashFlow]:
        """
        Строит полный список денежных потоков после calc_date.
        """
        flows: List[CashFlow] = []
        current_face = market_data.facevalue
        year_basis = config.DEFAULT_YEAR_BASIS
        
        # 1. Сортируем купоны и амортизации по дате
        coupons = sorted(coupons, key=lambda x: x.coupondate)
        amortizations = sorted(amortizations, key=lambda x: x.amortdate)
        
        # 2. Обработка амортизаций (pro-rata для неизвестных значений)
        future_amorts = [a for a in amortizations if a.amortdate > calc_date]
        
        # Если амортизаций нет совсем, а matdate есть - добавляем финальное погашение
        if not future_amorts and market_data.matdate and market_data.matdate > calc_date:
            future_amorts = [Amortization(
                amortdate=market_data.matdate, 
                facevalue=market_data.facevalue,
                value=market_data.facevalue
            )]
        
        # Распределение непогашенного номинала между амортизациями с неизвестным value
        total_known_amort = sum(a.value for a in future_amorts if a.value is not None)
        unknown_amorts = [a for a in future_amorts if a.value is None]
        
        if unknown_amorts:
            remaining_to_amortize = current_face - total_known_amort
            amort_per_date = remaining_to_amortize / len(unknown_amorts)
            for a in future_amorts:
                if a.value is None:
                    a.value = amort_per_date

        # 3. Обработка купонной ставки (Formula 14)
        cp_percent = market_data.couponpercent
        
        # Если ставка неизвестна, но есть НКД - вычисляем по Формуле 14
        if cp_percent is None and market_data.accruedint > 0:
            # tc – число дней от даты начала купона до даты расчетов
            # Если prevdate нет, пробуем найти начало текущего купона
            prev_coupon_date = market_data.prevdate
            if not prev_coupon_date and market_data.nextcoupon and market_data.couponperiod:
                prev_coupon_date = market_data.nextcoupon - timedelta(days=market_data.couponperiod)
            
            if prev_coupon_date:
                t_passed = (calc_date - prev_coupon_date).days
                if t_passed > 0:
                    # Cp = (A * 100 * YearBasis) / (N * t_passed)
                    cp_percent = (market_data.accruedint * 100 * year_basis) / (market_data.facevalue * t_passed)
                    logger.info("cp_calculated_from_ai", cp=cp_percent, secid=market_data.secid)

        # 4. Фильтруем будущие купоны
        future_coupons = [c for c in coupons if c.coupondate > calc_date]
        
        # Особый случай: Бессрочные (Perpetual)
        if market_data.matdate is None:
            end_date = calc_date + timedelta(days=365 * config.PERPETUAL_YEARS_AHEAD)
            if future_coupons:
                last_c = future_coupons[-1]
                current_d = last_c.coupondate
                period = market_data.couponperiod or 182
                # Используем последнюю известную ставку или вычисленную cp_percent
                effective_cp = cp_percent if cp_percent is not None else (last_c.valueprc if last_c.valueprc else None)
                
                while current_d < end_date:
                    current_d += timedelta(days=period)
                    # Вычисляем размер купона по Формуле 13
                    val = None
                    if effective_cp is not None:
                        # Ci = (Cp * Ni * period / YearBasis) / 100
                        val = (effective_cp * current_face * period / year_basis) / 100
                        
                    future_coupons.append(Coupon(
                        coupondate=current_d,
                        value=val,
                        valueprc=effective_cp,
                        facevalue=current_face
                    ))

        # 5. Сборка CashFlows
        all_dates = sorted(list({c.coupondate for c in future_coupons} | {a.amortdate for a in future_amorts}))
        
        for d in all_dates:
            c_obj = next((c for c in future_coupons if c.coupondate == d), None)
            a_obj = next((a for a in future_amorts if a.amortdate == d), None)
            
            coupon_val = 0.0
            if c_obj:
                if c_obj.value is not None:
                    coupon_val = c_obj.value
                elif cp_percent is not None:
                    # Формула 13: Ci = (Cp * Ni * ti / YearBasis) / 100
                    # ti здесь - длительность купонного периода
                    # Ищем начало этого купона
                    prev_c_date = next((c.coupondate for c in reversed(coupons) if c.coupondate < d), market_data.prevdate)
                    if not prev_c_date and market_data.couponperiod:
                        prev_c_date = d - timedelta(days=market_data.couponperiod)
                    
                    if prev_c_date:
                        t_i = (d - prev_c_date).days
                        coupon_val = (cp_percent * current_face * t_i / year_basis) / 100

            amort_val = a_obj.value if a_obj and a_obj.value is not None else 0.0
            
            if (coupon_val and coupon_val > 0) or (amort_val and amort_val > 0):
                flows.append(CashFlow(
                    date=d,
                    amount=float(coupon_val) + float(amort_val),
                    is_coupon=coupon_val > 0 if coupon_val else False,
                    is_amortization=amort_val > 0,
                    remaining_face_value=current_face
                ))
            
            if amort_val:
                current_face = max(0.0, current_face - amort_val)

        return flows
