"""PiHumMonitor FastAPI 服务端。

启动（项目根目录）：
    uvicorn server.main:app --reload --port 8000

提供 API：
    POST /api/readings     采集端推送一条数据（需 X-API-Token 头）
    GET  /api/latest       最新一条
    GET  /api/readings     历史数据（range=1h|6h|24h|7d，limit=）
    GET  /api/stats        区间统计
    GET  /api/health       健康检查
前端静态文件挂在 / 下。
"""
import os
from datetime import datetime, timezone
from pathlib import Path

import yaml
from fastapi import FastAPI, Header, HTTPException
from fastapi.staticfiles import StaticFiles

from server import database as db
from server import models

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = os.environ.get("PIHUM_CONFIG", str(PROJECT_ROOT / "config.yaml"))
DB_PATH = os.environ.get("PIHUM_DB", str(PROJECT_ROOT / "data" / "pihum.db"))
FRONTEND_DIR = PROJECT_ROOT / "frontend"

with open(CONFIG_PATH, encoding="utf-8") as f:
    CONFIG = yaml.safe_load(f)
# 空字符串表示关闭鉴权（仅开发用）；生产请设置非空 token
TOKEN = CONFIG.get("server", {}).get("token", "")

app = FastAPI(title="PiHumMonitor", version="1.0.0")
db.init_db(str(DB_PATH))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@app.get("/api/health")
def health():
    return {"ok": True}


@app.post("/api/readings")
def post_reading(
    reading: models.ReadingIn,
    x_api_token: str = Header(default="", alias="X-API-Token"),
):
    # token 非空时校验；为空则视为关闭鉴权
    if TOKEN and x_api_token != TOKEN:
        raise HTTPException(status_code=401, detail="invalid or missing token")
    ts = reading.timestamp or _now_iso()
    rid = db.insert_reading(str(DB_PATH), ts, reading.temperature, reading.humidity)
    return {"ok": True, "id": rid}


@app.get("/api/latest")
def latest():
    row = db.get_latest(str(DB_PATH))
    if not row:
        raise HTTPException(status_code=404, detail="no data yet")
    return row


@app.get("/api/readings")
def readings(range: str = "24h", limit: int = 2000):
    if limit < 1 or limit > 20000:
        limit = 2000
    since = db.parse_range(range)
    return db.get_readings(str(DB_PATH), since, limit)


@app.get("/api/stats")
def stats(range: str = "24h"):
    since = db.parse_range(range)
    s = db.get_stats(str(DB_PATH), since) or {}
    return {"range": range, **s}


# 静态前端：必须挂在所有 API 路由之后，否则会拦截 /api/*
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
