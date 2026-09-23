"""SHT30 模拟器：硬件未到时用，生成平滑随机游走的温湿度数据。
以 22°C / 55%RH 为基准，每步小幅波动，越界回弹，让前端图表看起来真实。
"""
import random

class SensorSimulator:
    def __init__(self, temp0: float = 22.0, hum0: float = 55.0):
        self.temp = float(temp0)
        self.hum = float(hum0)

    def read_sample(self) -> tuple[float, float]:
        self.temp += random.uniform(-0.2, 0.2)
        self.hum += random.uniform(-0.4, 0.4)

        # 边界限制，越界回弹
        if self.temp < 10:
            self.temp = 10 + random.uniform(0, 1)
        if self.temp > 35:
            self.temp = 35 - random.uniform(0, 1)
        if self.hum < 20:
            self.hum = 20 + random.uniform(0, 2)
        if self.hum > 90:
            self.hum = 90 - random.uniform(0, 2)
        return round(self.temp, 2), round(self.hum, 2)
