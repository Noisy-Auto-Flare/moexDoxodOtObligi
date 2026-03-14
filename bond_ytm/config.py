from dataclasses import dataclass, field
from typing import List, Tuple

@dataclass(frozen=True)
class AppConfig:
    """Конфигурация приложения."""
    ISS_BASE_URL: str = "https://iss.moex.com/iss"
    DEFAULT_YEAR_BASIS: int = 365
    RETRY_COUNT: int = 3
    RETRY_BACKOFF: float = 1.5
    CACHE_EXPIRE: int = 3600  # 1 час
    
    # Приоритет бордов для автоопределения
    BOARD_PRIORITY: Tuple[str, ...] = ("TQOB", "TQCB", "TQIR", "FQOB", "TQOD", "SU", "EQOB")
    
    # Пороговые значения
    MIN_YIELD: float = -100.0
    SOLVER_TOLERANCE: float = 1e-8
    
    # Округление купонов (до копеек)
    ROUND_CASHFLOWS: bool = True
    
    # Параметры для бессрочных облигаций
    PERPETUAL_YEARS_AHEAD: int = 10

config = AppConfig()
