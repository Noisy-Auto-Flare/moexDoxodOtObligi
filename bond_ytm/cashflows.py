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
        
        Обрабатывает:
        - Амортизацию (изменение номинала)
        - Неизвестные купоны (pro-rata)
        - Бессрочные облигации
        - Погашение номинала в конце срока
        """
        flows: List[CashFlow] = []
        current_face = market_data.facevalue
        
        # 1. Сортируем купоны и амортизации по дате
        coupons = sorted(coupons, key=lambda x: x.coupondate)
        amortizations = sorted(amortizations, key=lambda x: x.amortdate)
        
        # Фильтруем будущие платежи
        future_coupons = [c for c in coupons if c.coupondate > calc_date]
        future_amorts = [a for a in amortizations if a.amortdate > calc_date]
        
        # 2. Обработка бессрочных облигаций (Perpetual)
        # Если matdate нет, считаем "сегодня + 10 лет"
        if market_data.matdate is None:
            logger.info("perpetual_bond_detected", secid=market_data.secid)
            end_date = calc_date + timedelta(days=365 * config.PERPETUAL_YEARS_AHEAD)
            
            # Если купонов не хватает, дублируем последний известный
            if future_coupons:
                last_c = future_coupons[-1]
                current_d = last_c.coupondate
                period = market_data.couponperiod or 182
                while current_d < end_date:
                    current_d += timedelta(days=period)
                    future_coupons.append(Coupon(
                        coupondate=current_d,
                        value=last_c.value,
                        facevalue=last_c.facevalue
                    ))
        
        # 3. Собираем CashFlows
        # Объединяем все уникальные даты будущих платежей
        all_dates = sorted(list({c.coupondate for c in future_coupons} | {a.amortdate for a in future_amorts}))
        
        # Если амортизаций нет, а matdate есть — добавляем погашение в matdate
        if not future_amorts and market_data.matdate and market_data.matdate > calc_date:
            if market_data.matdate not in all_dates:
                all_dates.append(market_data.matdate)
                all_dates.sort()

        for d in all_dates:
            # Ищем купон на эту дату
            coupon_val = 0.0
            c_obj = next((c for c in future_coupons if c.coupondate == d), None)
            
            if c_obj:
                if c_obj.value is not None:
                    coupon_val = c_obj.value
                elif market_data.couponvalue is not None:
                    # Формула 13: Ci = Cp * (Ni / Np) - pro-rata по номиналу
                    # Где Cp - последний известный купон, Np - номинал на дату Cp
                    coupon_val = market_data.couponvalue * (current_face / market_data.facevalue)
                else:
                    # Если вообще нет данных о купоне, но есть НКД — можно вычислить Cp по (14)
                    # В данном упрощении считаем 0, если данных совсем нет.
                    pass

            # Ищем амортизацию на эту дату
            amort_val = 0.0
            a_obj = next((a for a in future_amorts if a.amortdate == d), None)
            
            if a_obj:
                amort_val = a_obj.value or 0.0
            elif d == market_data.matdate:
                # Погашение остатка номинала в дату погашения
                amort_val = current_face

            if coupon_val > 0 or amort_val > 0:
                flows.append(CashFlow(
                    date=d,
                    amount=coupon_val + amort_val,
                    is_coupon=coupon_val > 0,
                    is_amortization=amort_val > 0,
                    remaining_face_value=current_face
                ))
            
            # Уменьшаем текущий номинал после амортизации
            current_face = max(0.0, current_face - amort_val)

        return flows
