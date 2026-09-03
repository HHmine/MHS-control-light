from miio import Device
from dotenv import load_dotenv
import time
import os

load_dotenv()

# ========== 配置信息 ==========
DEVICE_IP = os.getenv("BEDSIDE_LAMP_IP")
DEVICE_TOKEN = os.getenv("BEDSIDE_LAMP_TOKEN")

# ========== 创建设备对象 ==========
lamp = Device(ip=DEVICE_IP, token=DEVICE_TOKEN)

# ========== 定义一些便捷函数 ==========
def set_power(on: bool):
    """开/关灯"""
    cmd = "on" if on else "off"
    lamp.send("set_power", [cmd])
    time.sleep(0.3)

def set_brightness(value: int):
    """设置亮度 (1~100)"""
    lamp.send("set_bright", [value])
    time.sleep(0.3)

def set_ct(value: int):
    """设置色温 (1700~6500 K)"""
    lamp.send("set_ct_abx", [value])
    time.sleep(0.3)

def set_rgb(rgb_dec: int):
    """设置RGB颜色 (十进制数值，如红色=16711680)"""
    lamp.send("set_rgb", [rgb_dec])
    time.sleep(0.3)



# ========== 执行控制序列 ==========
print("1. 开灯")
set_power(True)

print("2. 设置亮度为80%")
set_brightness(80)

print("3. 设置色温为3000K（暖黄光）")
set_ct(3000)

print("4. 等待2秒，然后切换为红色")
time.sleep(2)
set_rgb(16711680)    # 红色

print("5. 再等2秒，关灯")
time.sleep(2)
set_power(False)

print("所有指令执行完毕！")

# # 尝试查询电源、亮度、色温
# try:
#     status = lamp.send("get_prop", ["power", "bright", "ct"])
#     print("查询成功:", status)
# except Exception as e:
#     print("查询失败:", e)

# try:
#     lamp.send("set_power", ["on"])
#     print("开灯成功")
# except Exception as e:
#     print("开灯失败:", e)