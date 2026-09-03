"""使用 openJiuwen 调用小灯 Skill 的命令行 Agent。"""
from __future__ import annotations

import asyncio
import json
import os
import time
import uuid

from dotenv import load_dotenv

load_dotenv()

from openjiuwen.core.foundation.llm import BaseModelInfo, ModelConfig
from openjiuwen.core.single_agent.legacy.config import LegacyReActAgentConfig
from openjiuwen.core.single_agent.legacy.react_agent import LegacyReActAgent

from tools.lamp_tools import LAMP_TOOLS


def _message_value(message: object, key: str) -> object:
    if isinstance(message, dict):
        return message.get(key)
    return getattr(message, key, None)


def _content_to_text(content: object) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            else:
                text = _message_value(item, "text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts).strip()
    return ""


def format_agent_output(result: object) -> str:
    """提取最后一条有效的助手回复，隐藏调用轨迹和元数据。"""
    output = result.get("output") if isinstance(result, dict) else result
    if isinstance(output, str):
        return output.strip()

    messages = output if isinstance(output, (list, tuple)) else []
    for message in reversed(messages):
        if _message_value(message, "role") != "assistant":
            continue
        content = _content_to_text(_message_value(message, "content"))
        if content:
            return content

    if isinstance(result, dict):
        return json.dumps(result, ensure_ascii=False, indent=2, default=str)
    return str(result)


def build_agent() -> LegacyReActAgent:
    model_info = BaseModelInfo(
        api_key=os.getenv("API_KEY", ""),
        api_base=os.getenv("API_BASE", "https://api.openai.com/v1"),
        model=os.getenv("MODEL_NAME", "gpt-4o-mini"),
        temperature=0.2,
        top_p=0.8,
    )
    config = LegacyReActAgentConfig(
        id="lamp-agent",
        version="0.1.0",
        description="通过 Tool 查询和控制米家床头灯2的中文智能体。",
        model=ModelConfig(
            model_provider=os.getenv("MODEL_PROVIDER", "openai"),
            model_info=model_info,
        ),
        prompt_template=[
            {
                "role": "system",
                "content": (
                    "你是中文智能家居助手，可以通过工具操作米家床头灯2。"
                    "查询状态时调用 get_lamp_state；开关、亮度或色温控制时调用 control_lamp。"
                    "用户只要求开灯或关灯时，只传 power 参数，不要传 brightness 或 color_temperature。"
                    "亮度必须是 1 到 100 的整数，色温必须是 1700 到 6500 K 的整数。"
                    "用户未指定的可选参数必须省略，禁止使用 0 表示未设置。"
                    "只有工具返回成功后才可声称操作完成，并用中文如实说明结果。"
                ),
            }
        ],
    )
    return LegacyReActAgent(agent_config=config, tools=LAMP_TOOLS)


async def main() -> None:
    if not os.getenv("API_KEY"):
        raise RuntimeError(".env 中缺少 API_KEY")

    agent = build_agent()
    conversation_id = f"lamp-demo-{uuid.uuid4().hex[:8]}"
    print("小灯 AI Agent 已启动。输入 exit、quit 或 退出可结束。")
    while True:
        text = input("你：").strip()
        if text.lower() in {"exit", "quit", "退出"}:
            break
        if not text:
            continue
        try:
            started_at = time.perf_counter()
            result = await agent.invoke(
                {"query": text, "conversation_id": conversation_id}
            )
            elapsed_ms = (time.perf_counter() - started_at) * 1000
            print(f"\nAgent（本轮耗时 {elapsed_ms:.1f} ms）：{format_agent_output(result)}\n")
        except Exception as exc:
            print("Agent 执行失败：" + str(exc))


if __name__ == "__main__":
    asyncio.run(main())
