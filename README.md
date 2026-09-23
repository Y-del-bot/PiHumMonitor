# PiHumMonitor — 树莓派温湿度监测系统

基于 Raspberry Pi + DHT11 的实时空气温湿度监测系统：传感器采集 → 本地服务器存储 → 网页图表展示，支持局域网直连与公网隧道访问。

## 系统架构

```
[DHT11 传感器] --单总线--> [树莓派采集端] --HTTP+JSON--> [FastAPI 服务器] --HTTP--> [浏览器图表]
                            (每2秒采样)                  (SQLite存储)          (实时+历史)
                                                                      ↑
                                                        [cloudflared 隧道] --HTTPS--> 公网访问
```

## 功能特性

- 实时温度 / 湿度数值 + 更新时间展示
- 历史双轴折线图（温度 / 湿度），支持 1h / 6h / 24h / 7d 区间切换
- 区间统计（最小值 / 最大值 / 平均值）
- 采集端断网自动本地缓冲，网络恢复后补传，不丢数据
- 模拟器与真实传感器一键切换（配置文件），硬件未就绪也能开发调试

## 硬件清单

| 硬件 | 说明 |
|---|---|
| Raspberry Pi 3 Model B+ | 也可用其他带 GPIO 的树莓派型号 |
| DHT11 温湿度模块 | 三引脚模块版（自带上拉电阻） |
| 母对母杜邦线 | 3 根 |

### 接线（Pi 引脚从 USB 口朝下、左上角为第 1 脚数起）

| DHT11 引脚 | Pi 物理针脚 | 说明 |
|---|---|---|
| VCC | 第 1 脚 | 3.3V（⚠️ 勿接第 2/4 脚 5V） |
| DATA | 第 7 脚 | GPIO4（BCM 编号 4） |
| GND | 第 6 脚 | 地线 |

## 快速开始

### 1. 安装（树莓派上）

```bash
cd ~/PiHumMonitor
python3 -m venv venv
source venv/bin/activate
sudo apt install -y libgpiod2 i2c-tools
pip install -r server/requirements.txt -r sensor/requirements.txt
```

> Debian 13 (Trixie) 系统若提示找不到 `libgpiod2`，用 `apt-cache search gpiod` 查实际包名（可能为 `libgpiod2t64`）。

### 2. 配置

编辑 `config.yaml`：

```yaml
sensor:
  mode: "dht11"        # dht11=真实传感器 / simulator=模拟器（无硬件时用）
  gpio_pin: 4          # DATA 线接的 BCM 引脚号
server:
  url: "http://127.0.0.1:8000"
  token: "change-me-please"   # POST 鉴权令牌，公网部署前务必修改
```

### 3. 启动

```bash
# 终端 1：后端服务器
python -m uvicorn server.main:app --host 0.0.0.0 --port 8000

# 终端 2：采集端
python sensor/collect.py
```

浏览器访问 `http://<树莓派IP>:8000` 即可查看实时温湿度与历史曲线。

## API 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/readings` | 上报一条温湿度数据（需 `X-API-Token` 请求头） |
| GET | `/api/latest` | 最新一条数据 |
| GET | `/api/readings?hours=24` | 历史数据（可指定小时数） |
| GET | `/api/stats?hours=24` | 区间统计（min/max/avg） |

## 公网访问（cloudflared 隧道）

无公网 IP 也能让外网访问，利用 Cloudflare Tunnel 由树莓派主动外连：

```bash
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm
chmod +x cloudflared-linux-arm
sudo mv cloudflared-linux-arm /usr/local/bin/cloudflared
cloudflared tunnel --url http://localhost:8000
```

启动后终端会显示一个 `https://xxxx.trycloudflare.com` 公网网址，任何设备打开即可查看（免费版网址随机，重启会变）。

## 项目结构

```
PiHumMonitor/
├── config.yaml              # 全局配置（采样间隔 / 传感器模式 / 服务器地址 / token）
├── server/                  # FastAPI 后端
│   ├── main.py              # API 路由 + 静态页面托管
│   ├── database.py          # SQLite 存储层
│   └── models.py            # Pydantic 数据模型
├── frontend/                # 网页前端（Chart.js 本地化，无外部依赖）
├── sensor/                  # 采集端
│   ├── dht11_driver.py      # DHT11 驱动（含无效读数过滤与重试）
│   ├── sht30_driver.py      # SHT30 驱动（预留，I2C）
│   ├── sensor_simulator.py  # 模拟数据源
│   └── collect.py           # 采集主循环（断网缓冲重传）
└── deploy/
    └── setup-pi.sh          # 一键部署脚本
```

## 传输协议说明

| 链路 | 协议 |
|---|---|
| DHT11 → Pi | 单总线自定义时序协议（40 位数据：湿度16位 + 温度16位 + 校验8位） |
| 采集端 → 服务器 | HTTP/1.1 + JSON over TCP（本机回环） |
| 浏览器 → 服务器 | HTTP 轮询（30s 实时值 / 按需历史） |
| 公网访问 | HTTPS（TLS）+ Cloudflare Tunnel（QUIC，失败回退 HTTP/2） |
| 远程管理 | SSH（TCP 22） |
