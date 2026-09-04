from app.services.context_manager import (
    calculate_messages_tokens,
    trim_messages_by_tokens,
    MAX_INPUT_TOKENS,
)


messages = [
    {
        "role": "user",
        "content": "你好，我想学习 Vue3",
    },
    {
        "role": "assistant",
        "content": "当然可以，我可以帮助你学习 Vue3。",
    },
    {
        "role": "user",
        "content": "什么是 Composition API？",
    },
    {
        "role": "assistant",
        "content": "Composition API 是 Vue3 提供的一套组织组件逻辑的 API。",
    },
    {
        "role": "user",
        "content": "那 ref 和 reactive 有什么区别？",
    },
    {
        "role": "assistant",
        "content": "ref 和 reactive 都可以创建响应式数据，但使用方式和适用场景不同。",
    },
    {
        "role": "user",
        "content": "请给我一个实际开发中的例子。",
    },
]


print("=" * 60)
print("原始消息")
print("=" * 60)

for message in messages:
    print(message["role"], ":", message["content"])


original_tokens = calculate_messages_tokens(messages)

print()
print("原始 Token：", original_tokens)


max_tokens = MAX_INPUT_TOKENS


trimmed_messages = trim_messages_by_tokens(
    messages,
    max_tokens=max_tokens,
)


print()
print("=" * 60)
print("裁剪之后")
print("=" * 60)

for message in trimmed_messages:
    print(message["role"], ":", message["content"])


trimmed_tokens = calculate_messages_tokens(
    trimmed_messages
)

print()
print("裁剪后 Token：", trimmed_tokens)

print()
print("原始消息数量：", len(messages))
print("裁剪后消息数量：", len(trimmed_messages))