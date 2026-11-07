"""
注册邮箱验证码服务（Redis）。

- 明文验证码仅返回给上层（供 SMTP 使用），不写入 Redis、不打生产日志。
- Redis 中仅存 HMAC 摘要与 attempts。
- 校验与回滚使用 Lua，保证原子性。
"""

from __future__ import annotations

import hmac
import logging
import os
import secrets
import uuid
from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from pathlib import Path
from typing import Final

from dotenv import load_dotenv
from redis import Redis
from redis.exceptions import RedisError

from app.redis_client import get_redis


logger = logging.getLogger(__name__)

# ----- 常量（TTL / 次数 / Key 前缀）-----
CODE_TTL_SECONDS: Final[int] = 300
COOLDOWN_TTL_SECONDS: Final[int] = 60
MAX_ATTEMPTS: Final[int] = 5
KEY_PREFIX: Final[str] = "ai_assistant:register"
HMAC_ENV_NAME: Final[str] = "EMAIL_CODE_HMAC_SECRET"

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_ENV_PATH = _BACKEND_ROOT / ".env"


# ----- 业务异常 -----


class EmailCodeError(Exception):
    """验证码业务异常基类。"""


class RedisUnavailableError(EmailCodeError):
    """Redis 客户端不可用（未初始化或已关闭）。"""


class EmailCodeConfigError(EmailCodeError):
    """缺少或无效的 HMAC 配置。"""


class CooldownActiveError(EmailCodeError):
    """同一邮箱仍在发送冷却中。"""

    def __init__(self, email: str, retry_after: int | None = None) -> None:
        self.email = email
        self.retry_after = retry_after
        super().__init__(f"发送过于频繁: {email}")


# ----- 结果类型 -----


class VerifyStatus(str, Enum):
    OK = "ok"
    EXPIRED = "expired"
    INVALID = "invalid"
    EXHAUSTED = "exhausted"


@dataclass(frozen=True)
class IssuedCode:
    """发码成功结果：明文 code 仅供上层发信，禁止记入日志。"""

    email: str
    code: str
    request_id: str
    expires_in: int = CODE_TTL_SECONDS


@dataclass(frozen=True)
class VerifyResult:
    status: VerifyStatus
    attempts: int = 0


# ----- Lua：原子写入验证码 Hash + TTL -----
# 原子性保证：HSET 与 EXPIRE 在同一 EVAL 内执行；脚本成功则二者同时生效，
# 脚本失败则 Redis 不提交部分写，不会留下「有 Hash 无 TTL」的间隙状态。
# KEYS[1] 必须等于 ARGV[1]（本邮箱 code key）。
_STORE_CODE_LUA = """
local code_key = KEYS[1]
local expected_key = ARGV[1]
local code_hash = ARGV[2]
local attempts = ARGV[3]
local request_id = ARGV[4]
local ttl = tonumber(ARGV[5])

if code_key ~= expected_key then
  return {'key_mismatch', '0'}
end

if (not ttl) or ttl < 1 then
  return {'error', 'bad_ttl'}
end

redis.call(
  'HSET',
  code_key,
  'code_hash', code_hash,
  'attempts', attempts,
  'request_id', request_id
)
redis.call('EXPIRE', code_key, ttl)
local remain = redis.call('TTL', code_key)
return {'ok', tostring(remain)}
"""

# ----- Lua：原子校验并消费 -----
# 原子性保证：
# 1) 读取 code_hash / attempts 与比对、删除在同一 EVAL 内完成，避免 TOCTOU；
# 2) 成功路径 DEL 后同码无法再次成功；
# 3) KEYS[1] 必须等于 ARGV[3]（Python 预计算的本邮箱 code key），防止误操作其它邮箱。
_VERIFY_LUA = """

local code_key = KEYS[1]
local submitted_hash = ARGV[1]
local max_attempts = tonumber(ARGV[2])
local expected_key = ARGV[3]

if code_key ~= expected_key then
  return {'key_mismatch', '0'}
end

local fields = redis.call('HMGET', code_key, 'code_hash', 'attempts')
local stored_hash = fields[1]
local attempts = tonumber(fields[2] or '0')

if (not stored_hash) then
  return {'expired', '0'}
end

if stored_hash == submitted_hash then
  redis.call('DEL', code_key)
  return {'ok', tostring(attempts)}
end

attempts = attempts + 1
if attempts >= max_attempts then
  redis.call('DEL', code_key)
  return {'exhausted', tostring(attempts)}
end

redis.call('HSET', code_key, 'attempts', tostring(attempts))
return {'invalid', tostring(attempts)}
"""

# ----- Lua：按 request_id 回滚本请求的 code + cooldown -----
# 仅当 Hash.request_id / cooldown 值等于 ARGV[1] 时才删除，不影响其它并发请求。
_CANCEL_LUA = """
local code_key = KEYS[1]
local cooldown_key = KEYS[2]
local request_id = ARGV[1]
local expected_code_key = ARGV[2]
local expected_cooldown_key = ARGV[3]

if code_key ~= expected_code_key or cooldown_key ~= expected_cooldown_key then
  return {0, 0, 'key_mismatch'}
end

local deleted_code = 0
local rid = redis.call('HGET', code_key, 'request_id')
if rid and rid == request_id then
  redis.call('DEL', code_key)
  deleted_code = 1
end

local deleted_cooldown = 0
local cd = redis.call('GET', cooldown_key)
if cd and cd == request_id then
  redis.call('DEL', cooldown_key)
  deleted_cooldown = 1
end

return {deleted_code, deleted_cooldown, 'ok'}
"""


def generate_code() -> str:
    """使用 secrets 生成 6 位数字字符串（保留前导 0）。"""

    return f"{secrets.randbelow(1_000_000):06d}"


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _code_key(email: str) -> str:
    return f"{KEY_PREFIX}:code:{email}"


def _cooldown_key(email: str) -> str:
    return f"{KEY_PREFIX}:cooldown:{email}"


def _require_redis() -> Redis:
    client = get_redis()
    if client is None:
        raise RedisUnavailableError("Redis 不可用：客户端未初始化或初始化失败")
    return client


def _load_hmac_secret() -> str:
    """从 backend/.env 读取 HMAC 密钥；禁止硬编码。"""

    load_dotenv(_ENV_PATH)
    secret = (os.getenv(HMAC_ENV_NAME) or "").strip()
    if not secret:
        raise EmailCodeConfigError(
            f"缺少环境变量 {HMAC_ENV_NAME}，无法签发/校验邮箱验证码"
        )
    if len(secret) < 32:
        raise EmailCodeConfigError(
            f"{HMAC_ENV_NAME} 过短（至少 32 字符）"
        )
    return secret


def _hmac_code(secret: str, email: str, code: str) -> str:
    """对 email+code 做 HMAC-SHA256，摘要入库；密钥不进入 Redis。"""

    message = f"{email}\n{code}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), message, sha256).hexdigest()


def issue_code(email: str) -> IssuedCode:
    """
    签发注册验证码：冷却 SET NX EX 60，Hash 存 code_hash/attempts/request_id，TTL 300。

    返回明文 code 供上层发信；本函数不记录明文。
    """

    normalized = normalize_email(email)
    if not normalized:
        raise ValueError("email 不能为空")

    client = _require_redis()
    secret = _load_hmac_secret()
    request_id = uuid.uuid4().hex
    code = generate_code()
    code_hash = _hmac_code(secret, normalized, code)

    code_key = _code_key(normalized)
    cooldown_key = _cooldown_key(normalized)

    try:
        # 冷却：值为 request_id，便于 cancel 时只清本请求
        acquired = client.set(
            cooldown_key,
            request_id,
            nx=True,
            ex=COOLDOWN_TTL_SECONDS,
        )
        if not acquired:
            ttl = client.ttl(cooldown_key)
            retry_after = ttl if isinstance(ttl, int) and ttl > 0 else COOLDOWN_TTL_SECONDS
            raise CooldownActiveError(normalized, retry_after=retry_after)

        # Hash + TTL 必须在同一 Lua 原子单元内完成（修复 HSET/EXPIRE 两步间隙）
        raw = client.eval(
            _STORE_CODE_LUA,
            1,
            code_key,
            code_key,
            code_hash,
            "0",
            request_id,
            str(CODE_TTL_SECONDS),
        )
        if (
            not isinstance(raw, (list, tuple))
            or len(raw) < 2
            or str(raw[0]) != "ok"
        ):
            raise RedisError(f"验证码 Hash 原子写入失败: {raw!r}")
        remain_ttl = int(raw[1]) if str(raw[1]).lstrip("-").isdigit() else -1
        if remain_ttl < 1:
            # 脚本声称成功但未带上有效 TTL：主动回滚并失败，避免无过期 Key
            raise RedisError(
                f"验证码 Hash 写入后 TTL 无效: {remain_ttl}"
            )
    except CooldownActiveError:
        raise
    except RedisError:
        # 不吞掉 RedisError；若已占冷却则尝试按 request_id 回滚
        try:
            cancel_code_issue(normalized, request_id)
        except Exception:  # noqa: BLE001 — 回滚失败不掩盖原始 Redis 错误
            logger.exception("issue_code 失败后回滚 Redis 状态时出错")
        raise

    logger.info(
        "已签发注册验证码：email=%s request_id=%s expires_in=%s",
        normalized,
        request_id,
        CODE_TTL_SECONDS,
    )
    return IssuedCode(
        email=normalized,
        code=code,
        request_id=request_id,
        expires_in=CODE_TTL_SECONDS,
    )


def verify_and_consume_code(email: str, submitted_code: str) -> VerifyResult:
    """
    原子校验并消费验证码（Lua）。

    成功则删除 Hash；错误累计 attempts；满 5 次删除并使码失效。
    """

    normalized = normalize_email(email)
    submitted = (submitted_code or "").strip()
    if len(submitted) != 6 or not submitted.isdigit():
        # 格式错误也走同一校验路径（会计次或视为无效）
        pass

    client = _require_redis()
    secret = _load_hmac_secret()
    code_key = _code_key(normalized)
    submitted_hash = _hmac_code(secret, normalized, submitted)

    try:
        raw = client.eval(
            _VERIFY_LUA,
            1,
            code_key,
            submitted_hash,
            str(MAX_ATTEMPTS),
            code_key,
        )
    except RedisError:
        raise

    if not isinstance(raw, (list, tuple)) or len(raw) < 2:
        raise RedisError(f"验证码 Lua 返回异常: {raw!r}")

    status_raw = str(raw[0])
    attempts = int(raw[1]) if str(raw[1]).isdigit() else 0

    if status_raw == "key_mismatch":
        raise RedisError("验证码 Key 校验失败（key_mismatch）")
    if status_raw == "ok":
        return VerifyResult(status=VerifyStatus.OK, attempts=attempts)
    if status_raw == "expired":
        return VerifyResult(status=VerifyStatus.EXPIRED, attempts=0)
    if status_raw == "exhausted":
        return VerifyResult(status=VerifyStatus.EXHAUSTED, attempts=attempts)
    if status_raw == "invalid":
        return VerifyResult(status=VerifyStatus.INVALID, attempts=attempts)

    raise RedisError(f"未知验证状态: {status_raw}")


def cancel_code_issue(email: str, request_id: str) -> tuple[bool, bool]:
    """
    SMTP 失败回滚：仅删除属于该 request_id 的 code Hash 与 cooldown。

    返回 (deleted_code, deleted_cooldown)。
    """

    normalized = normalize_email(email)
    rid = (request_id or "").strip()
    if not rid:
        raise ValueError("request_id 不能为空")

    client = _require_redis()
    code_key = _code_key(normalized)
    cooldown_key = _cooldown_key(normalized)

    raw = client.eval(
        _CANCEL_LUA,
        2,
        code_key,
        cooldown_key,
        rid,
        code_key,
        cooldown_key,
    )
    if not isinstance(raw, (list, tuple)) or len(raw) < 2:
        raise RedisError(f"cancel Lua 返回异常: {raw!r}")

    if len(raw) >= 3 and str(raw[2]) == "key_mismatch":
        raise RedisError("cancel Key 校验失败（key_mismatch）")

    deleted_code = int(raw[0]) == 1
    deleted_cooldown = int(raw[1]) == 1
    logger.info(
        "cancel_code_issue：email=%s request_id=%s deleted_code=%s deleted_cooldown=%s",
        normalized,
        rid,
        deleted_code,
        deleted_cooldown,
    )
    return deleted_code, deleted_cooldown
