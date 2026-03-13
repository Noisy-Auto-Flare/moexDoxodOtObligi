import requests
import structlog
from typing import Dict, Any, List, Optional
from diskcache import Cache
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from .config import config
from .exceptions import DataFetchError

logger = structlog.get_logger(__name__)
cache = Cache(".iss_cache")

class DataFetcher:
    """Клиент для получения данных из MOEX ISS."""
    
    def __init__(self):
        self.session = requests.Session()
        retry_strategy = Retry(
            total=config.RETRY_COUNT,
            backoff_factor=config.RETRY_BACKOFF,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retry_strategy))

    def _get(self, url: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Вспомогательный метод для GET-запросов к ISS."""
        params.update({
            "iss.json": "extended",
            "iss.meta": "off",
            "limit": "unlimited",
            "lang": "ru"
        })
        try:
            response = self.session.get(url, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
            # В режиме extended данные приходят как список словарей в ключе [1]
            # [0] - описание колонок, [1] - данные
            return data
        except Exception as e:
            logger.error("iss_request_failed", url=url, error=str(e))
            raise DataFetchError(f"Ошибка при запросе к MOEX ISS: {e}")

    def get_security_info(self, secid: str) -> List[Dict[str, Any]]:
        """Получает общую информацию о бумаге (включая boards)."""
        url = f"{config.ISS_BASE_URL}/securities/{secid}.json"
        return self._get(url, {})

    def get_market_data(self, secid: str, board: str) -> List[Dict[str, Any]]:
        """Получает рыночные данные (securities + marketdata) по бумаге."""
        url = f"{config.ISS_BASE_URL}/engines/stock/markets/bonds/boards/{board}/securities/{secid}.json"
        return self._get(url, {"iss.only": "securities,marketdata"})

    def get_bondization(self, secid: str) -> List[Dict[str, Any]]:
        """Получает данные о купонах и амортизациях."""
        url = f"{config.ISS_BASE_URL}/securities/{secid}/bondization.json"
        return self._get(url, {"iss.only": "coupons,amortizations"})

    def auto_detect_board(self, secid: str) -> str:
        """Автоматически определяет активный режим торгов для бумаги."""
        data = self.get_security_info(secid)
        # Ищем блок 'boards'
        boards_block = None
        for block in data:
            if "boards" in block:
                boards_block = block["boards"]
                break
        
        if not boards_block:
            raise DataFetchError(f"Не удалось найти информацию о режимах торгов для {secid}")
        
        active_boards = {b["boardid"] for b in boards_block if b.get("is_traded") == 1}
        
        for board in config.BOARD_PRIORITY:
            if board in active_boards:
                return board
        
        if active_boards:
            # Если нет в приоритете, берем первый попавшийся активный
            return list(active_boards)[0]
            
        raise DataFetchError(f"Не найден активный режим торгов для {secid}")
