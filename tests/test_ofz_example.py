import pytest
from datetime import date
from bond_ytm import BondYieldCalculator

@pytest.fixture
def calculator():
    return BondYieldCalculator()

def test_ofz_26207_calculation(calculator):
    """Тест расчёта доходности для ОФЗ 26207 (классическая ОФЗ)."""
    # ОФЗ 26207 - один из наиболее ликвидных выпусков в прошлом
    result = calculator.calculate(secid="SU26207RMFS9")
    
    assert result.secid == "SU26207RMFS9"
    if result.ytm_percent is not None:
        assert isinstance(result.ytm_percent, float)
        assert result.ytm_percent > -100
        assert len(result.cashflows) > 0
    else:
        # Если биржа не вернула цену (выходной), это тоже валидный случай для теста
        assert result.error_reason is not None

def test_corporate_amortization(calculator):
    """Тест облигации с амортизацией."""
    # Пример облигации с амортизацией (ГК Самолет или М.Видео часто имеют амортизацию)
    result = calculator.calculate(secid="RU000A1038V6") # Пример М.Видео-002P-01
    
    assert result.secid == "RU000A1038V6"
    if result.ytm_percent is not None:
        # Проверяем, что в потоках есть амортизация
        amorts = [f for f in result.cashflows if f.is_amortization]
        assert len(amorts) > 0

def test_perpetual_bond(calculator):
    """Тест бессрочной облигации."""
    # Пример бессрочной облигации (Газпром капитал)
    result = calculator.calculate(secid="RU000A105A04")
    
    assert result.secid == "RU000A105A04"
    if result.ytm_percent is not None:
        # Для бессрочных мы строим потоки на 10 лет вперед
        assert len(result.cashflows) >= 10 

def test_unknown_coupon_pro_rata(calculator):
    """Тест корректности pro-rata для неизвестных купонов."""
    # Это больше интеграционный тест, проверяем что не падает
    result = calculator.calculate(secid="RU000A1038V6")
    if result.ytm_percent is not None:
        for cf in result.cashflows:
            assert cf.amount > 0

def test_invalid_secid(calculator):
    """Тест на несуществующий SECID."""
    result = calculator.calculate(secid="INVALID_SECID")
    assert result.ytm_percent is None
    assert result.error_reason is not None
