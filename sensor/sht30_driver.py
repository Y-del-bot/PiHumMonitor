"""SHT30 I2C 驱动（Raspberry Pi）。

实现单次测量模式：
  1. 发命令 0x2C 0x06（高重复性，clock stretching 禁用）
  2. 等约 20ms 完成测量
  3. 读 6 字节 = [温度MSB, 温度LSB, 温度CRC, 湿度MSB, 湿度LSB, 湿度CRC]
  4. CRC-8 校验（多项式 0x31，初值 0xFF）
  5. 按 datasheet 公式换算：
       温度(°C) = -45 + 175 * raw / 65535
       湿度(%RH) = 100 * raw / 65535

注意：
  - 仅在 Raspberry Pi（已启用 I2C：sudo raspi-config -> Interface Options -> I2C）
    上可用；I2C bus 1 对应 GPIO2(SDA)/GPIO3(SCL)，物理 pin 3/5。
  - 用 i2cdetect -y 1 应看到 0x44（ADDR->GND）或 0x45（ADDR->VDD）。
  - Windows 上 import 本模块不会失败（smbus2 延迟到实例化时才导入），
    但实例化 SHT30Driver() 会因缺少 /dev/i2c-* 报错——这是预期行为。
"""
import time


class SHT30Driver:
    def __init__(self, i2c_bus: int = 1, i2c_addr: int = 0x44):
        # 延迟导入：Windows 上无 smbus2 时 import 本模块仍可用
        from smbus2 import SMBus

        self.bus = SMBus(i2c_bus)
        self.addr = i2c_addr

    @staticmethod
    def _crc8(data: bytes) -> int:
        crc = 0xFF
        for b in data:
            crc ^= b
            for _ in range(8):
                if crc & 0x80:
                    crc = (crc << 1) ^ 0x31
                else:
                    crc <<= 1
        return crc & 0xFF

    def read_sample(self) -> tuple[float, float]:
        from smbus2 import i2c_msg

        # 发测量命令
        write = i2c_msg.write(self.addr, [0x2C, 0x06])
        self.bus.i2c_rdwr(write)
        time.sleep(0.02)  # 测量需 ~15ms

        # 读 6 字节结果
        read = i2c_msg.read(self.addr, 6)
        self.bus.i2c_rdwr(read)
        data = list(read)
        if len(data) != 6:
            raise IOError(f"SHT30 expected 6 bytes, got {len(data)}")

        # CRC 校验
        if self._crc8(bytes(data[0:2])) != data[2] or self._crc8(bytes(data[3:5])) != data[5]:
            raise ValueError("SHT30 CRC mismatch")

        temp_raw = (data[0] << 8) | data[1]
        hum_raw = (data[3] << 8) | data[4]
        temperature = -45.0 + 175.0 * temp_raw / 65535.0
        humidity = 100.0 * hum_raw / 65535.0
        return round(temperature, 2), round(humidity, 2)

    def close(self):
        try:
            self.bus.close()
        except Exception:
            pass
