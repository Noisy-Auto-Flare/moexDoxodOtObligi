from datetime import date
from typing import List, Optional, Any
from pydantic import BaseModel, Field, ConfigDict, field_validator

def parse_moex_date(v: Any) -> Optional[date]:
    """Вспомогательная функция для обработки дат MOEX (0000-00-00 -> None)."""
    if v == "0000-00-00" or v is None:
        return None
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v))
    except (ValueError, TypeError):
        return None

class BondMarketData(BaseModel):
    """Модель рыночных данных облигации из ISS MOEX."""
    model_config = ConfigDict(populate_by_name=True)

    secid: str = Field(alias="SECID")
    boardid: str = Field(alias="BOARDID")
    shortname: Optional[str] = Field(None, alias="SHORTNAME")
    price: Optional[float] = Field(None, alias="PREVPRICE")
    accruedint: Optional[float] = Field(None, alias="ACCRUEDINT")
    bid: Optional[float] = Field(None, alias="BID")
    offer: Optional[float] = Field(None, alias="OFFER")
    couponvalue: Optional[float] = Field(None, alias="COUPONVALUE")
    couponpercent: Optional[float] = Field(None, alias="COUPONPERCENT")
    nextcoupon: Optional[date] = Field(None, alias="NEXTCOUPON")
    prevdate: Optional[date] = Field(None, alias="PREVDATE")
    matdate: Optional[date] = Field(None, alias="MATDATE")
    offerdate: Optional[date] = Field(None, alias="OFFERDATE")
    buybackdate: Optional[date] = Field(None, alias="BUYBACKDATE")
    lotsize: int = Field(default=1, alias="LOTSIZE")
    facevalue: float = Field(alias="FACEVALUE")
    decimals: int = Field(default=2, alias="DECIMALS")
    couponperiod: Optional[int] = Field(None, alias="COUPONPERIOD")
    currencyid: str = Field(default="SUR", alias="CURRENCYID")
    status: str = Field(default="A", alias="STATUS")
    sectype: Optional[str] = Field(None, alias="SECTYPE")

    @field_validator("matdate", "offerdate", "buybackdate", mode="before")
    @classmethod
    def validate_dates(cls, v: Any) -> Optional[date]:
        return parse_moex_date(v)

class Coupon(BaseModel):
    """Модель купонной выплаты."""
    model_config = ConfigDict(populate_by_name=True)

    isin: Optional[str] = None
    name: Optional[str] = None
    coupondate: date
    recorddate: Optional[date] = None
    startdate: Optional[date] = None
    facevalue: float
    value: Optional[float] = None
    valueprc: Optional[float] = None

    @field_validator("coupondate", "recorddate", "startdate", mode="before")
    @classmethod
    def validate_dates(cls, v: Any) -> Optional[date]:
        return parse_moex_date(v)

class Amortization(BaseModel):
    """Модель амортизации номинала."""
    model_config = ConfigDict(populate_by_name=True)

    isin: Optional[str] = None
    amortdate: date
    facevalue: float
    value: Optional[float] = None
    valueprc: Optional[float] = None

    @field_validator("amortdate", mode="before")
    @classmethod
    def validate_dates(cls, v: Any) -> Optional[date]:
        return parse_moex_date(v)

class CashFlow(BaseModel):
    """Модель денежного потока для расчёта YTM."""
    date: date
    amount: float
    is_coupon: bool
    is_amortization: bool
    remaining_face_value: float

class CalculationResult(BaseModel):
    """Результат расчёта доходности."""
    secid: str
    ytm_percent: Optional[float] = None
    ytm_bid_percent: Optional[float] = None
    ytm_offer_percent: Optional[float] = None
    dirty_price: float
    accrued_interest: float
    cashflows: List[CashFlow] = []
    warning: Optional[str] = None
    error_reason: Optional[str] = None
