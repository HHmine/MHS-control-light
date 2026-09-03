---
name: lamp-control
description: Control and inspect the user's physical bedside lamp through JiuwenSwarm MCP tools. Use this skill whenever the user asks to turn the lamp on or off, change brightness, change color temperature, check lamp status, or diagnose the lamp gateway. Always use the MCP result as the source of truth.
compatibility: Requires the lamp-control MCP server and the local device gateway at http://127.0.0.1:8000.
---

# Lamp Control

Use the dedicated `lamp-control` MCP server. Do not construct shell commands, run
`lamp_gateway.py`, create another Agent, or connect directly to the physical lamp.

## MCP tools

- `get_lamp_gateway_health`: check whether the gateway is available and identify its backend.
- `get_lamp_state`: read the physical lamp state without changing it.
- `control_lamp`: change power, brightness, and/or color temperature.

## Decision rules

- To turn the lamp on, call `control_lamp` with only `power: true`.
- To turn the lamp off, call `control_lamp` with only `power: false`.
- For brightness, pass only `brightness` unless the user explicitly requests another change.
- For color temperature, pass only `color_temperature` unless the user explicitly requests another change.
- Brightness must be an integer from 1 through 100.
- Color temperature must be an integer from 1700 through 6500 K.
- Never use `0`, `null`, or an invented value for an omitted control.
- For a status question, call `get_lamp_state`; never answer from conversation memory.
- After a successful `control_lamp` call, use its returned state and end the turn. Do not call
  `get_lamp_state` again because the control response already contains verified device state.
- If an MCP tool reports an error, report that error and do not claim the device changed state.
- Do not fall back to shell or the legacy script when MCP is unavailable. Tell the user that the
  `lamp-control` MCP server or device gateway must be started or checked.

## Response style

Keep normal responses concise and in Chinese. State what actually changed using the MCP result,
for example: `小灯已打开，当前亮度 40%，色温 3000K。`

Do not expose credentials, internal request metadata, or raw debug dumps.
