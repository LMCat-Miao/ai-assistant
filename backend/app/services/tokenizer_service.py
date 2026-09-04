from pathlib import Path

import transformers
from tokenizers import Tokenizer


# ============================================================
# 1. 获取 backend 目录
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent.parent


# ============================================================
# 2. DeepSeek V4 Tokenizer 路径
# ============================================================

TOKENIZER_DIR = (
    BASE_DIR
    / "tokenizer"
    / "deepseek_v4_tokenizer"
)

TOKENIZER_PATH = TOKENIZER_DIR / "tokenizer.json"


# ============================================================
# 3. Transformers Tokenizer
# ============================================================

transformers_tokenizer = transformers.AutoTokenizer.from_pretrained(
    TOKENIZER_DIR,
    trust_remote_code=True,
)


# ============================================================
# 4. Raw Tokenizer
#
# 直接读取官方 tokenizer.json
# 用于真正的 Token 计算
# ============================================================

raw_tokenizer = Tokenizer.from_file(
    str(TOKENIZER_PATH)
)


# ============================================================
# 5. 计算普通文本 Token
# ============================================================

def count_tokens(text: str) -> int:
    """
    计算普通文本的 Token 数量。

    直接使用 DeepSeek 官方 tokenizer.json
    避免 Transformers LlamaTokenizer 中文兼容问题。
    """

    encoding = raw_tokenizer.encode(text)

    return len(encoding.ids)


# ============================================================
# 6. 获取 Chat Template
# ============================================================

def apply_chat_template(
    messages: list[dict],
) -> str:
    """
    将 messages 转换成模型实际使用的 Chat Template 文本。

    这里只负责格式化，不负责 Token 计算。
    """

    return transformers_tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
    )


# ============================================================
# 7. 计算 Chat Token
# ============================================================

def count_chat_tokens(
    messages: list[dict],
) -> int:
    """
    计算完整 Chat Template 处理后的 Token 数量。
    """

    formatted_text = apply_chat_template(messages)

    encoding = raw_tokenizer.encode(formatted_text)

    return len(encoding.ids)