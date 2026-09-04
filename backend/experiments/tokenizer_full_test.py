from pathlib import Path
from tokenizers import Tokenizer


# ============================================================
# 1. 定位 Tokenizer
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

TOKENIZER_PATH = (
    BASE_DIR
    / "tokenizer"
    / "deepseek_v4_tokenizer"
    / "tokenizer.json"
)


print("=" * 60)
print("Tokenizer 完整测试")
print("=" * 60)

print("Tokenizer 路径：")
print(TOKENIZER_PATH)

print()

print("文件是否存在：")
print(TOKENIZER_PATH.exists())


# ============================================================
# 2. 加载 Tokenizer
# ============================================================

tokenizer = Tokenizer.from_file(
    str(TOKENIZER_PATH)
)


# ============================================================
# 3. 测试文本
# ============================================================

test_texts = [
    "你好",

    "Hello!",

    "人工智能正在改变软件开发的方式。",

    "你好，我正在学习 Vue3 和 FastAPI。",

    "Vue3 + TypeScript + FastAPI",

    "Promise、async/await、Axios",

    "def hello():\n    print('Hello World')",

    "# AI 学习助手\n\n这是一个基于 Vue3 和 FastAPI 开发的 AI 项目。",

    "请解释一下什么是 Token？",
]


# ============================================================
# 4. 开始测试
# ============================================================

for index, text in enumerate(test_texts, start=1):

    encoding = tokenizer.encode(text)

    print()
    print("=" * 60)
    print(f"测试 {index}")
    print("=" * 60)

    print("原始文本：")
    print(text)

    print()

    print("字符数量：")
    print(len(text))

    print()

    print("Token IDs：")
    print(encoding.ids)

    print()

    print("Token 数量：")
    print(len(encoding.ids))

    print()

    print("Tokens：")
    print(encoding.tokens)