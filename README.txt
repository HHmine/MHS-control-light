# Agent Hardware Demo

## 使用方式

项目不再提供独立 Agent 对话网页 `/app`。设备管理员网页仍保留，用于直接控制设备、查看状态和选择黑盒故障：`http://127.0.0.1:8000/`。中文接口说明使用同一个页面：`http://127.0.0.1:8000/docs`。

自然语言交互可使用 JiuwenSwarm，或在 `.venv` 中运行 `python my_agent.py` 使用命令行 Agent。

## JiuwenSwarm 直接交互

JiuwenSwarm 使用 `lamp-control` Skill 和 `lamp_mcp_server.py` 提供的 MCP 工具。Skill 负责意图和调用规则，MCP Server 负责把结构化工具调用转发给设备网关；不再由 Agent 拼接并执行 `lamp_gateway.py` 命令。`my_agent.py` 继续保留用于独立命令行调试。

首次安装或重新注册 MCP 配置时执行：

```powershell
cd D:\AI\MHS\agent_demo
.\install_jiuwenswarm_mcp.ps1
```

安装脚本会先备份 JiuwenSwarm 的用户配置和旧版 `lamp-control` Skill，然后注册 MCP Server。安装后需要完整退出并重新打开 JiuwenSwarm。

使用 JiuwenSwarm 前，只需启动设备网关，不需要启动 `my_agent.py`。

模拟设备网关：

```powershell
cd D:\AI\MHS\agent_demo
$env:DEVICE_BACKEND = "simulated"
.\.venv\Scripts\python.exe run_device_gateway.py
```

真实 Yeelight 设备网关：

```powershell
cd D:\AI\MHS\agent_demo
$env:DEVICE_BACKEND = "yeelight"
.\.venv-miio\Scripts\python.exe run_device_gateway.py
```

MCP Server 由 JiuwenSwarm 按 `C:\Users\wangzhe\.jiuwenswarm\config\config.yaml` 中的 `mcp.servers` 配置自动启动，不需要再开一个 PowerShell 窗口。启动设备网关后，在 JiuwenSwarm 当前对话中直接输入“打开小灯”“把亮度调到 40%”或“查询小灯状态”。默认设备网关地址是 `http://127.0.0.1:8000`；如果网关使用其他端口，需要同步修改 MCP Server 的 `DEVICE_SERVICE_URL`。

`run_device_gateway.py` 启动 `device_gateway.api:app`，供 JiuwenSwarm、命令行 Agent 和设备管理员网页使用。

## 接口

- `GET /api/device/state`：读取实时状态
- `POST /api/device/control`：`{"power": true, "brightness": 80, "color_temperature": 4000}`
- `POST /api/faults/inject`：`{"fault": "offline"}`
- `POST /api/faults/clear`：清除故障
- `GET /api/real-faults/state`：查询真实设备的网关级故障状态
- `POST /api/real-faults/inject`：网页管理员注入 `{"fault":"block_power_on"}` 或 `{"fault":"block_power_off"}`
- `POST /api/real-faults/clear`：清除真实设备的网关级故障
- `GET /api/device/events`：SSE 实时事件流

支持故障：`offline`、`stuck_on`、`stuck_off`、`sensor_error`、`overheat`。

真实 Yeelight 后端额外支持网页管理员使用的黑盒故障：`block_power_on` 禁止开灯，`block_power_off` 禁止关灯。命中的控制请求不会发送到实体灯，但 HTTP 仍返回 200 和一份与请求一致的成功状态，使 Agent 不知道故障存在。后续单独查询设备状态会读取真实硬件，因此可以发现灯的实际状态没有改变。故障只显示在管理员网页，不会注册为 Agent/MCP 工具，也不会出现在普通健康检查或设备状态响应中；状态仅保存在网关进程内，重启网关会自动清除。

## Agent Skill

`tools/lamp_tools.py` 只向命令行 Agent 提供 `get_lamp_state` 和 `control_lamp`。所有故障注入能力仅保留在设备管理员网页和后端管理接口，不会注册为 Agent 或 MCP 工具。

## 真实设备

真实设备通过 `device_gateway/yeelight_adapter.py` 和 `python-miio` 接入；设备地址和令牌从 `.env` 读取。不要把 `.env` 提交或发送给其他人。
