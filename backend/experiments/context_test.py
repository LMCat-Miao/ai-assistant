from app.services.context_manager import (
    calculate_messages_tokens,
    trim_messages_by_tokens,
)


messages = [
    {
        "role": "user",
        "content": "你好，我正在学习 Vue。"
    },
    {
        "role": "assistant",
        "content": "很好，Vue 是一个渐进式 JavaScript 框架。"
    },
    {
        "role": "user",
        "content": "什么是 Pinia？"
    },
    {
        "role": "assistant",
        "content": "Pinia 是 Vue 官方推荐的状态管理库。"
    },
    {
        "role": "user",
        "content": "什么是 Axios？"
    },
]


print("原始消息：")
for message in messages:
    print(message)


total_tokens = calculate_messages_tokens(messages)

print("\n原始 Token 数：")
print(total_tokens)


max_tokens = 50

trimmed_messages = trim_messages_by_tokens(
    messages,
    max_tokens,
)


print("\n裁剪后的消息：")

for message in trimmed_messages:
    print(message)


print("\n裁剪后的 Token 数：")

print(
    calculate_messages_tokens(trimmed_messages)
)