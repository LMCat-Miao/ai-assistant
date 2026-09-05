from app.services.context_manager import (
    calculate_chat_tokens,
    trim_messages_by_budget,
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
        "content": "ref 和 reactive 都可以创建响应式数据。",
    },

    {
        "role": "user",
        "content": "请给我一个实际开发中的例子。",
    },
]


# ============================================================
# 设置一个比较小的 Budget
# ============================================================

MAX_TOKENS = 70


# ============================================================
# 原始 Context
# ============================================================

print("=" * 60)
print("原始 Context")
print("=" * 60)

for message in messages:
    print(
        f"{message['role']}: "
        f"{message['content']}"
    )


original_tokens = calculate_chat_tokens(
    messages
)

print("\n原始 Token：")
print(original_tokens)


# ============================================================
# 开始裁剪
# ============================================================

trimmed_messages = trim_messages_by_budget(
    messages,
    max_tokens=MAX_TOKENS,
)


# ============================================================
# 输出裁剪结果
# ============================================================

print("\n" + "=" * 60)
print("裁剪之后")
print("=" * 60)

for message in trimmed_messages:
    print(
        f"{message['role']}: "
        f"{message['content']}"
    )


trimmed_tokens = calculate_chat_tokens(
    trimmed_messages
)

print("\n裁剪后 Token：")
print(trimmed_tokens)


# ============================================================
# 检查结果
# ============================================================

print("\n" + "=" * 60)
print("检查结果")
print("=" * 60)

if trimmed_tokens <= MAX_TOKENS:
    print("✅ Context 没有超过 Token Budget")
else:
    print("❌ Context 仍然超过 Token Budget")