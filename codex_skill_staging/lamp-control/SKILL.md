---
name: lamp-control
description: Control and inspect the user's physical bedside lamp through the local lamp-control MCP server. Use when the user asks to turn the lamp on or off, change brightness or color temperature, check its state, or diagnose the lamp gateway.
metadata:
  short-description: Safely control, query, and diagnose the physical bedside lamp through MCP
---

# Lamp Control

Use the `lamp-control` MCP tools for the physical bedside lamp. Never construct shell
commands, run the legacy scripts, create another agent, or connect directly to the
lamp. The device gateway and its configured `direct` or `aurea` execution mode are
the source of execution behavior.

## Available tools

- `get_lamp_gateway_health`: check gateway availability and backend; read-only.
- `get_lamp_state`: read the current physical lamp state; read-only.
- `control_lamp`: change power, brightness, and/or color temperature.

## Tool rules

- “开灯” / “打开小灯” → `control_lamp(power=true)`.
- “关灯” / “关闭小灯” → `control_lamp(power=false)`.
- Brightness requests pass only `brightness`, as an integer from 1 to 100.
- Color-temperature requests pass only `color_temperature`, as an integer from 1700 to 6500 K.
- If the user requests multiple changes, pass only those explicitly requested.
- Do not send `null`, `0`, or invented values for omitted fields.
- For status questions, call `get_lamp_state`; do not answer from memory.
- After a successful control call, use the returned state as the source of truth and do not issue a redundant state query.
- If a tool fails, report the failure and do not claim that the lamp changed.
- Do not expose or call administrator-only fault-injection endpoints. Their state is intentionally hidden from the agent.
- Do not fall back to shell commands when MCP or the gateway is unavailable; tell the user which service must be checked.

## Response style

Respond concisely in Chinese. State the actual returned state, for example:
“小灯已打开，当前亮度 40%，色温 3000K。” Do not expose credentials,
internal tokens, or raw debug metadata.
