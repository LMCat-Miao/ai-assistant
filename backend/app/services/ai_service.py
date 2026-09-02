import os

from openai import OpenAI
from dotenv import load_dotenv


# 加载 .env 环境变量
load_dotenv()


# AI 配置
AI_API_KEY = os.getenv("AI_API_KEY")
AI_BASE_URL = os.getenv("AI_BASE_URL")
AI_MODEL = os.getenv("AI_MODEL")


# 创建 OpenAI 客户端
client = OpenAI(
    api_key=AI_API_KEY,
    base_url=AI_BASE_URL,
)


def chat_with_ai(message: str) -> str:
    """
    普通 AI 对话
    """
    response = client.chat.completions.create(
        model=AI_MODEL,
        messages=[
            {
                "role": "user",
                "content": message,
            }
        ],
    )

    return response.choices[0].message.content or ""


def chat_with_ai_stream(message: str):
    """
    AI 流式对话

    AI 每生成一部分内容，
    就通过 yield 返回一部分。
    """

    response = client.chat.completions.create(
        model=AI_MODEL,
        messages=[
            {
                "role": "user",
                "content": message,
            }
        ],
        stream=True,
    )

    # 不断获取 AI 返回的数据块
    for chunk in response:

        # 当前数据块中的文本
        content = chunk.choices[0].delta.content

        # 有内容才返回
        if content:
            yield content