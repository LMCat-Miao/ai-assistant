from app.services.tokenizer_service import TOKENIZER_DIR
from transformers import AutoTokenizer


print("=" * 60)
print("1. 强制使用 Fast Tokenizer")
print("=" * 60)

tokenizer = AutoTokenizer.from_pretrained(
    TOKENIZER_DIR,
    trust_remote_code=True,
    use_fast=True,
)

print("Tokenizer 类型：")
print(type(tokenizer))

print("\nTokenizer class：")
print(tokenizer.__class__.__name__)


print("\n" + "=" * 60)
print("2. 测试中文")
print("=" * 60)

text = "你好"

result = tokenizer(
    text,
    add_special_tokens=False,
)

print("文本：")
print(text)

print("\ninput_ids：")
print(result["input_ids"])

print("\nToken 数量：")
print(len(result["input_ids"]))


print("\n" + "=" * 60)
print("3. 测试英文")
print("=" * 60)

text = "Hello!"

result = tokenizer(
    text,
    add_special_tokens=False,
)

print("文本：")
print(text)

print("\ninput_ids：")
print(result["input_ids"])

print("\nToken 数量：")
print(len(result["input_ids"]))