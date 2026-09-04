from app.services.tokenizer_service import (
    transformers_tokenizer,
    raw_tokenizer,
    count_tokens,
    count_chat_tokens,
    apply_chat_template,
)


print("=" * 60)
print("1. Tokenizer 基本信息")
print("=" * 60)

print("Transformers Tokenizer：")
print(type(transformers_tokenizer))

print("Raw Tokenizer：")
print(type(raw_tokenizer))


# ============================================================
# 2. 普通 Content Token
# ============================================================

print("\n" + "=" * 60)
print("2. 测试普通 Content Token")
print("=" * 60)

text = "你好"

print("Content：")
print(text)

encoding = raw_tokenizer.encode(text)

print("Token IDs：")
print(encoding.ids)

print("Token 数量：")
print(len(encoding.ids))


# ============================================================
# 3. Chat Message
# ============================================================

print("\n" + "=" * 60)
print("3. 测试 Chat Message")
print("=" * 60)

messages = [
    {
        "role": "user",
        "content": "你好",
    }
]

print("Messages：")
print(messages)


# ============================================================
# 4. Chat Template
# ============================================================

print("\n" + "=" * 60)
print("4. 应用 Chat Template")
print("=" * 60)

formatted_text = apply_chat_template(messages)

print("Chat Template：")
print(formatted_text)


# ============================================================
# 5. Chat Template Token
# ============================================================

print("\n" + "=" * 60)
print("5. 计算 Chat Template Token")
print("=" * 60)

chat_encoding = raw_tokenizer.encode(formatted_text)

print("Chat Token IDs：")
print(chat_encoding.ids)

print("Chat Token 数量：")
print(len(chat_encoding.ids))


# ============================================================
# 6. 使用 service
# ============================================================

print("\n" + "=" * 60)
print("6. 使用 Tokenizer Service")
print("=" * 60)

print("Content Token：")
print(count_tokens("你好"))

print("Chat Token：")
print(count_chat_tokens(messages))