# PiHumMonitor 软件设计方案

## Context（背景与目标）

硬件待齐（SHT30 I2C 模块未到货），需要先开发软件部分，待硬件到位后无缝切换到真实传感器。

业务目标（来自录音任务）：
1. 读取设备采集的数据
2. 写入服务器
3. 部署为网站
4. 投放到公网，供老板访问查看

硬件：Raspberry Pi Model B+（40-pin GPIO，I2C bus 1 = GPIO2/3）+ SHT30 I2C 温湿度模块（地址 0x44）。

软件需在硬件未到时即可开发、调试、演示；硬件到位后只改一个配置开关即可切到真实数据。

## 整体架构

```
┌──────────────────────┐   HTTP POST (JSON)    ┌─────────────────────────┐
│  Raspberry Pi B+     │ ───────────────────> │  服务器（后端 + 前端）   │
│  - 采集脚本           │                       │  - FastAPI + SQLite      │
│  - SHT30 驱动 / 模拟  │ <────────────────── │  - 静态前端（HTML/JS）    │
│  每 30s 一次          │   GET /api/readings   │  - 公网入口（反向代理）  │
└──────────────────────┘                       └─────────────────────────┘
                                                          │
                                                          ▼
                                                 老板浏览器访问公网域名
```

设计要点：
- **采集与展示解耦**：Pi 只负责读传感器并 POST 数据，服务器负责存储与展示。这样 Pi 断网时数据采集可缓存重传；公网访问稳定（不依赖家庭网络）。
- **统一数据契约**：真实驱动和模拟器都实现同一个 `read_sample()` 接口，通过 `config.yaml` 切换。
- **可本地开发**：服务器、前端、模拟采集脚本都可在当前 Windows 开发机上跑起来，不依赖 Pi。

## 部署选项（需用户确认其一）

### 选项 A（推荐）：服务器部署在云 VPS，Pi 推送数据
- 后端 + 前端 + SQLite 部署在云 VPS（阿里云/腾讯云轻量服务器均可）
- Pi 跑采集脚本，通过 HTTPS POST 把数据推到 VPS
- 老板直接访问 VPS 公网 IP/域名
- 优点：公网稳定、Pi 离线不影响老板查看历史数据、运维简单
- 需要：一台云 VPS（最低 1 核 1G 即可）

### 选项 B：Pi 自托管 + 反向隧道
- 后端 + 前端 + SQLite 都跑在 Pi 上
- 用 frp 或 Cloudflare Tunnel 把 Pi 本地端口暴露到公网
- 优点：无云服务器成本
- 缺点：依赖家庭网络稳定性，Pi 重启即断

> 本方案文件结构两种选项通用，仅部署步骤不同。

## 技术栈

| 层 | 技术 | 理由 |
|---|---|---|
| 采集（Pi 端） | Python 3 + `smbus2` | Pi 原生支持，SHT30 I2C 读写简单 |
| 后端 | Python 3 + FastAPI + Uvicorn | 轻量、自带 OpenAPI 文档、异步 |
| 存储 | SQLite | 单文件、零运维、数据量小（30s/条≈100万条/年） |
| 前端 | 原生 HTML + JS + Chart.js | 无构建步骤、易部署、图表足够 |
| 反向代理（部署） | Nginx（选项 A）或 frp/Cloudflare Tunnel（选项 B） | 标准方案 |

## 项目文件结构

```
PiHumMonitor/
├── config.yaml              # 全局配置（采样间隔、服务器 URL、传感器模式等）
├── sensor/                  # Pi 端采集
│   ├── sht30_driver.py      # 真实 SHT30 驱动（smbus2）
│   ├── sensor_simulator.py  # SHT30 模拟器（硬件未到时用）
│   └── collect.py           # 采集主循环：读 → POST 到服务器
├── server/                  # 后端
│   ├── main.py              # FastAPI 应用（API + 静态前端托管）
│   ├── database.py          # SQLite 初始化与查询
│   ├── models.py            # Pydantic 模型
│   └── requirements.txt     # fastapi, uvicorn, pydantic
├── frontend/                # 前端
│   ├── index.html           # 单页：实时值 + 24h 折线图
│   ├── app.js               # 轮询 /api/readings，渲染 Chart.js
│   └── style.css            # 简洁样式
└── .trae/
    └── documents/
        └── PiHumMonitor-软件设计方案.md   # 本文件
```

> 不会主动创建 README 等额外文档，除非用户明确要求。

## 关键模块设计

### 1. 传感器驱动接口（统一契约）

`sensor/sht30_driver.py` 与 `sensor/sensor_simulator.py` 都实现：

```python
class SensorBase:
    def read_sample(self) -> tuple[float, float]:
        """返回 (temperature_c, humidity_pct)"""
```

- **真实驱动**：用 `smbus2.SMBus(1)`，发命令 `0x2C 0x06`，等 20ms，读 6 字节，做 CRC-8（poly 0x31）校验，按公式换算。
- **模拟器**：以 22 °C / 55 %RH 为基准做平滑随机游走（每步 ±0.2，越界回弹），让前端图表看起来真实。

`config.yaml` 里 `sensor.mode: simulator | real` 决定 `collect.py` 实例化哪个。

### 2. 采集脚本 `sensor/collect.py`

```python
# 伪代码
while True:
    temp, hum = sensor.read_sample()
    payload = {"timestamp": now_iso(), "temperature": temp, "humidity": hum}
    try:
        requests.post(f"{server_url}/api/readings", json=payload, timeout=5)
    except Exception:
        # 失败时写本地缓存文件，下次成功后重传（可选增强）
        buffer.append(payload)
    sleep(sample_interval)
```

- 采样间隔默认 30s（可配置）
- 失败容忍：POST 失败写本地 JSONL 缓冲，下次成功后批量重传

### 3. 后端 `server/main.py`（FastAPI）

API：
- `POST /api/readings` — 接收一条数据，写库（带简单 token 校验防伪）
- `GET /api/readings?range=24h&limit=2000` — 返回历史数据
- `GET /api/latest` — 返回最新一条
- `GET /api/stats?range=24h` — min/max/avg 聚合

静态托管：FastAPI `StaticFiles` 挂载 `frontend/` 到 `/`。

### 4. 数据库 `server/database.py`

SQLite 单表：
```sql
CREATE TABLE readings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,          -- ISO8601 UTC
  temperature REAL NOT NULL,
  humidity REAL NOT NULL
);
CREATE INDEX idx_readings_ts ON readings(ts);
```

### 5. 前端 `frontend/index.html`

- 顶部大字号显示当前温度/湿度 + 更新时间
- 下方 Chart.js 双轴折线图，默认 24h，可切 1h/6h/7d
- 每 30s 自动 `fetch('/api/latest')` 刷新当前值；图表每 5min 拉一次历史

## 开发顺序（硬件未到时的迭代路径）

1. **后端骨架**：FastAPI + SQLite + 三个 GET + POST，本地 uvicorn 跑通
2. **前端**：HTML + Chart.js，本地浏览器连后端看图表
3. **模拟器**：写 `sensor_simulator.py`，跑 `collect.py` 推数据到本地后端，前端实时动起来 → 完整链路打通
4. **真实驱动**：写 `sht30_driver.py`（按 SHT30 datasheet 命令/CRC/换算），但暂不接硬件
5. **部署文档化**：等硬件到，把 `config.yaml` 切 `real`，部署到 Pi + 云 VPS

## 验证方式（端到端）

在当前 Windows 开发机上：
1. `pip install -r server/requirements.txt`
2. `uvicorn server.main:app --reload` 启动后端
3. 浏览器打开 `http://127.0.0.1:8000` 看前端
4. 另开终端 `python sensor/collect.py`（默认 `mode: simulator`，服务器指向本地）推数据
5. 前端应在 30s 内出现新数据点，图表持续更新

硬件到位后（在 Pi 上）：
1. Pi 上 `sudo raspi-config` 启用 I2C
2. `i2cdetect -y 1` 应看到 0x44
3. 改 `config.yaml`：`sensor.mode: real`，`server.url` 指向云 VPS
4. `python sensor/collect.py` 启动采集

## 需用户确认的关键点

1. **部署选项**：选 A（云 VPS，推荐）还是 B（Pi 自托管 + 隧道）？影响最终部署步骤。
2. **云 VPS**：是否已有？若有，提供 IP/域名与 SSH 方式（部署阶段用）。
3. **鉴权**：老板访问是否需要登录？（可加一个简单 token 或 basic auth）
4. **技术栈**：Python FastAPI + SQLite + 原生 HTML/Chart.js 是否 OK？有无偏好（如 Vue/React）？
5. **展示需求**：单传感器、实时值 + 历史图表是否满足？需要报警阈值吗？

> 如无特别反馈，将按"选项 A + 无登录（内网/简单 token）+ 上述技术栈 + 实时+24h 图表"的默认开始实现。
