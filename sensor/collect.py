"""PiHumMonitor 采集端主循环：读传感器 -> POST 到服务器。

用法（在项目根目录）：
    python sensor/collect.py

配置见 config.yaml：
    sensor.mode           simulator | real
    sensor.sample_interval 采样间隔（秒）
    server.url            目标服务器
    server.token          POST 鉴权 token（与服务器 config 一致）

失败容忍：POST 失败时写本地 data/buffer.jsonl，下次成功后自动重传。
"""
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)  # 允许直接 import 同目录的 sensor_simulator / sht30_driver

DEFAULT_CONFIG = os.path.join(PROJECT_ROOT, "config.yaml")


def load_config(path: str = DEFAULT_CONFIG):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def make_sensor(cfg):
    mode = cfg["sensor"]["mode"]
    if mode == "real":
        from sht30_driver import SHT30Driver

        return SHT30Driver(cfg["sensor"].get("i2c_bus", 1), cfg["sensor"].get("i2c_addr", 0x44))
    if mode == "dht11":
        from dht11_driver import DHT11Driver

        return DHT11Driver(cfg["sensor"].get("gpio_pin", 4))
    if mode == "simulator":
        from sensor_simulator import SensorSimulator

        return SensorSimulator()
    raise ValueError(f"unknown sensor mode: {mode}")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def post(server_url: str, token: str, payload: dict):
    return requests.post(
        f"{server_url}/api/readings",
        json=payload,
        headers={"X-API-Token": token},
        timeout=5,
    )


def flush_buffer(buffer_path: Path, server_url: str, token: str, log):
    """重传本地缓冲文件中的数据；成功的丢弃，失败的保留。"""
    if not buffer_path.exists():
        return
    lines = [l for l in buffer_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    if not lines:
        buffer_path.unlink(missing_ok=True)
        return
    remaining = []
    for line in lines:
        payload = json.loads(line)
        try:
            r = post(server_url, token, payload)
            r.raise_for_status()
        except Exception:
            remaining.append(line)
    if remaining:
        buffer_path.write_text("\n".join(remaining) + "\n", encoding="utf-8")
        log.info("buffer: %d entries still pending", len(remaining))
    else:
        buffer_path.unlink(missing_ok=True)


def main():
    cfg = load_config()
    log_level = cfg.get("logging", {}).get("level", "INFO")
    logging.basicConfig(level=log_level, format="%(asctime)s [%(levelname)s] %(message)s")
    log = logging.getLogger("collect")

    sensor = make_sensor(cfg)
    server_url = cfg["server"]["url"].rstrip("/")
    token = cfg["server"]["token"]
    interval = int(cfg["sensor"].get("sample_interval", 30))
    buffer_path = Path(PROJECT_ROOT) / "data" / "buffer.jsonl"
    buffer_path.parent.mkdir(parents=True, exist_ok=True)

    log.info(
        "collector started: mode=%s interval=%ss server=%s",
        cfg["sensor"]["mode"], interval, server_url,
    )
    while True:
        try:
            temp, hum = sensor.read_sample()
        except Exception as e:
            log.error("sensor read failed: %s", e)
            time.sleep(interval)
            continue

        payload = {"timestamp": now_iso(), "temperature": temp, "humidity": hum}
        try:
            r = post(server_url, token, payload)
            r.raise_for_status()
            log.info("posted: %.2f°C  %.2f%%RH", temp, hum)
            flush_buffer(buffer_path, server_url, token, log)
        except Exception as e:
            log.warning("post failed (%s), buffering locally", e)
            with open(buffer_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload) + "\n")
        time.sleep(interval)


if __name__ == "__main__":
    main()
