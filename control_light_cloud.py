from mijiaAPI import mijiaAPI, mijiaDevice

# 1. 初始化并登录（首次运行会生成二维码，用米家App扫码）
api = mijiaAPI()
api.login()

# 2. 通过设备名称找到你的台灯（名称务必与米家App中显示的一致）
lamp = mijiaDevice(api, dev_name="test_lamp")  # 例如 "床头灯"

# 3. 发送指令
lamp.on = True                 # 开灯
lamp.brightness = 80           # 亮度 80%
# lamp.color_temperature = 3000  # 色温 3000K（如果支持）
# lamp.on = False                # 关灯

print("云端指令已发送，请观察台灯状态。")