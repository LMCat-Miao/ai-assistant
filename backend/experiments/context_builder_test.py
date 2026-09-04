from app.services.context_builder import build_context
from app.services.context_manager import calculate_messages_tokens


messages = [
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
    {
        "role": "assistant",
        "content": "Composition API 是 Vue3 提供的一套组织组件逻辑的 API。",
    },
    {
        "role": "user",
        "content": "那 ref 和 reactive 有什么区别？",
    },
]


context = build_context(messages)


print("=" * 60)
print("最终 Context")
print("=" * 60)

for message in context:
    print()
    print("Role:", message["role"])
    print("Content:")
    print(message["content"])


print()
print("=" * 60)
print("Context Token")
print("=" * 60)

print(
    calculate_messages_tokens(context)
)