"""API 数据模型（Pydantic v2）。"""
from pydantic import BaseModel


class ReadingIn(BaseModel):
    # ISO8601 时间戳；为空时服务端用当前 UTC 时间
    timestamp: str | None = None
    temperature: float
    humidity: float


class ReadingOut(BaseModel):
    id: int
    ts: str
    temperature: float
    humidity: float


class StatsOut(BaseModel):
    range: str
    count: int
    temp_min: float | None = None
    temp_max: float | None = None
    temp_avg: float | None = None
    hum_min: float | None = None
    hum_max: float | None = None
    hum_avg: float | None = None
