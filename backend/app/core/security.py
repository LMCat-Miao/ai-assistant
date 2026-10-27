from datetime import datetime, timedelta, timezone
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import HTTPException, status
from jose import jwt
from jose.exceptions import JWTError


# 与 ai_service 一致：从 backend/.env 加载，避免仅依赖进程 cwd。
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_BACKEND_ROOT / ".env")


ALGORITHM = "HS256"

ACCESS_TOKEN_EXPIRE_MINUTES = 60

# 明显不安全的占位 / 模板值：禁止静默当作生产密钥使用。
# 长度校验不能证明随机性；此处仅拦截已知弱口令与文档示例串。
_INSECURE_JWT_SECRET_PLACEHOLDERS = frozenset(
    {
        "",
        "your-super-secret-key",
        "changeme",
        "secret",
        "jwt-secret",
        "JWT_SECRET_KEY",
        "replace-with-a-long-random-secret-at-least-32-chars",
        "replace-with-a-long-random-secret-at-least-32-chars!",
        "a-very-secret-key-that-is-long-enough-32",
        "please-change-me-to-a-random-secret-key",
        "example-jwt-secret-key-do-not-use-this",
        "super-secret-key-change-me-immediately",
        "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        "00000000000000000000000000000000",
        "12345678901234567890123456789012",
    }
)


def _load_jwt_secret_key() -> str:
    """从环境变量读取 JWT 签名密钥；缺失或不安全时立即失败。"""

    raw = os.getenv("JWT_SECRET_KEY")
    if raw is None:
        raise RuntimeError(
            "缺少环境变量 JWT_SECRET_KEY。"
            "请在 backend/.env 中配置足够长的随机密钥，"
            "不要使用代码中的默认值。"
        )

    secret = raw.strip()
    if secret.lower() in {p.lower() for p in _INSECURE_JWT_SECRET_PLACEHOLDERS}:
        raise RuntimeError(
            "JWT_SECRET_KEY 仍是不安全的占位值。"
            "请替换为足够长的随机字符串后再启动服务。"
        )

    if len(secret) < 32:
        raise RuntimeError(
            "JWT_SECRET_KEY 长度过短（至少 32 个字符）。"
            "请使用更强的随机密钥。"
        )

    return secret


# 签发与校验共用同一来源；模块导入时校验配置，避免带着弱密钥启动。
SECRET_KEY = _load_jwt_secret_key()


def create_access_token(data: dict):
    to_encode = data.copy()

    expire = datetime.now(timezone.utc) + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )

    to_encode.update({
        "exp": expire
    })

    encoded_jwt = jwt.encode(
        to_encode,
        SECRET_KEY,
        algorithm=ALGORITHM
    )

    return encoded_jwt


def verify_access_token(token: str):
    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )
        return payload

    except JWTError:
        # ExpiredSignatureError / JWTClaimsError 等均为 JWTError 子类
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 无效或已过期",
        )
