class BondYTMError(Exception):
    """Базовое исключение для пакета."""
    pass

class DataFetchError(BondYTMError):
    """Ошибка при получении данных из ISS MOEX."""
    pass

class CalculationError(BondYTMError):
    """Ошибка при расчёте доходности."""
    pass

class UnsupportedBondError(BondYTMError):
    """Тип облигации не поддерживается (например, ОФЗ по формулам 8/9)."""
    pass

class NoMarketDataError(BondYTMError):
    """Отсутствуют рыночные данные для расчёта."""
    pass
