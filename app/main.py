from __future__ import annotations
from typing import NamedTuple, List, Dict, Optional, Tuple

class Config(NamedTuple):
    principal: float
    periods: int
    rate: float
    late_fee_percent: float
    daily_mora_rate: float
    default_after_missed: int
    days_in_period: int = 30

class State(NamedTuple):
    t: int
    principal: float
    overdue: float
    status: str
    missed: int

class Decision(NamedTuple):
    will_pay: bool
    delay_days: int
    extra: float

def price_payment(pv: float, i: float, n:int) -> float:
    if n <= 0: 
        raise ValueError("Periodos deve ser maior que 0.")
    if i == 0: 
        return pv / n
    f = (i * (1+i)**n) / ((1+i)**n -1)
    return pv * f

def fees_period(principal: float, rate: float) -> float:
    return principal * rate

def charges_late(parcela: int, atraso_dias: int, multa: float, mora_dia: float) -> float:
    if atraso_dias <= 0: 
        return 0.0
    return parcela * multa + parcela * mora_dia * atraso_dias

def mora_late(vencido: float, mora_dia: float, dias: int) -> float:
    return 0.0 if vencido <= 0 else vencido * mora_dia * dias

