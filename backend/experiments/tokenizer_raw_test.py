from pathlib import Path
from tokenizers import Tokenizer


# ============================================================
# 1. 获取项目根目录
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent


# ============================================================
# 2. 获取 DeepSeek V4 Tokenizer 路径
# ============================================================

TOKENIZER_DIR = (
    BASE_DIR
    / "tokenizer"
    / "deepseek_v4_tokenizer"
)

TOKENIZER_PATH = TOKENIZER_DIR / "tokenizer.json"


# ============================================================
# 3. 检查 tokenizer.json 是否存在
# ============================================================

print("=" * 60)
print("Tokenizer 路径检查")
print("=" * 60)

print("Tokenizer 路径：")
print(TOKENIZER_PATH)

print()

print("文件是否存在：")
print(TOKENIZER_PATH.exists())


# ============================================================
# 4. 加载 tokenizer.json
# ============================================================

tokenizer = Tokenizer.from_file(
    str(TOKENIZER_PATH)
)


# ============================================================
# 5. 测试中文
# ============================================================

text = "你好"

encoding = tokenizer.encode(text)

print()
print("=" * 60)
print("1. 中文 Token 测试")
print("=" * 60)

print("文本：")
print(text)

print()

print("Token IDs：")
print(encoding.ids)

print()

print("Token 数量：")
print(len(encoding.ids))

print()

print("Tokens：")
print(encoding.tokens)


# ============================================================
# 6. 测试英文
# ============================================================

text = "Hello!"

encoding = tokenizer.encode(text)

print()
print("=" * 60)
print("2. 英文 Token 测试")
print("=" * 60)

print("文本：")
print(text)

print()

print("Token IDs：")
print(encoding.ids)

print()

print("Token 数量：")
print(len(encoding.ids))

print()

print("Tokens：")
print(encoding.tokens)