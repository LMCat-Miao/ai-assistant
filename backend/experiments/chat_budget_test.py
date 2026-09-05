from app.services.context_manager import (
    calculate_chat_tokens,
    MAX_INPUT_TOKENS,
)


messages = [
    {
        "role": "system",
        "content": "你是一名专业的 AI 学习助手。",
    },
    {
        "role": "user",
        "content": "你好，我正在学习 Vue3。",
    },
    {
        "role": "assistant",
        "content": "很好，Vue3 是现代前端开发的重要技术。",
    },
    {
        "role": "user",
        "content": "什么是 Composition API？",
    },
]


print("=" * 60)
print("Chat Context Token Test")
print("=" * 60)


print("\nMessages：")

for message in messages:
    print(
        f"{message['role']}: "
        f"{message['content']}"
    )


tokens = calculate_chat_tokens(
    messages
)


print("\nChat Template Token：")
print(tokens)


print("\nMAX_INPUT_TOKENS：")
print(MAX_INPUT_TOKENS)


print("\n是否超过 Budget：")

if tokens > MAX_INPUT_TOKENS:
    print("❌ 超过 Token Budget")
else:
    print("✅ 没有超过 Token Budget")