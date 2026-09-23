"""DHT11 温湿度驱动（Raspberry Pi）。

用轻量 dht11 库（szazo 版）读取，依赖少、装得快、稳。
DHT11 是单根数据线协议（非 I2C）。BCM 编号：GPIO4 = 物理 pin 7。

规格：温度 0~50°C ±2°C；湿度 20~90%RH ±5%；最快 1Hz（建议 ≥2s，config 已 2s）。

接线（3 脚模块）：
  VCC  -> Pi pin 1 (3.3V)        # 千万别接 pin 2/4（5V）
  DATA -> Pi pin 7 (GPIO4)       # BCM 编号 4，可在 config 的 gpio_pin 改
  GND  -> Pi pin 6 (GND)
裸 DHT11（4 脚）需在 DATA 与 VCC 之间外接 4.7k~10k 上拉电阻。

依赖（仅 Raspberry Pi 需要，Windows 用模拟器可忽略）：
  pip install dht11 RPi.GPIO

注意：实例化需要 Pi 真机环境；Windows 上 import 本模块不会报错，
但 DHT11Driver() 会失败——这是预期行为。
"""
import time


class DHT11Driver:
    def __init__(self, gpio_pin: int = 4, max_retries: int = 10):
        # 延迟导入：Windows 上 import 本模块可用，实例化才需要 Pi 环境
        import RPi.GPIO as GPIO
        from dht11 import DHT11 as _DHT11

        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        self._gpio = GPIO
        self.dht = _DHT11(gpio_pin)  # BCM 编号；GPIO4 = 物理 pin 7
        self.max_retries = max_retries

    def read_sample(self) -> tuple[float, float]:
        # DHT11 经常一次读失败，多次重试
        last_err = None
        for _ in range(self.max_retries):
            try:
                r = self.dht.read()
                # r.is_valid 但温湿度同时为 0 是 szazo 库常见的"假成功"读数
                # (全零数据帧也能过校验)，室内不可能 temp=0 且 hum=0，跳过重试
                if r.is_valid and not (r.temperature == 0 and r.humidity == 0):
                    return round(float(r.temperature), 1), round(float(r.humidity), 1)
                last_err = f"error_code={r.error_code}" if not r.is_valid else "zero reading"
            except Exception as e:
                last_err = e
            time.sleep(0.5)
        raise RuntimeError(
            f"DHT11 read failed after {self.max_retries} retries: {last_err}"
        )

    def close(self):
        try:
            self._gpio.cleanup()
        except Exception:
            pass
