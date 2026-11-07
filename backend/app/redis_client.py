"""
Redis 客户端（同步 redis-py）。

仅作为临时数据存储（如未来邮箱验证码），不替代 MySQL 或 Chroma。
模块 import 时不发起网络连接；由 lifespan 显式 init / close。
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from redis import Redis
from redis.exceptions import RedisError


logger = logging.getLogger(__name__)

# backend/ 根目录（与 database.py 一致，不依赖进程 cwd）
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_ENV_PATH = _BACKEND_ROOT / ".env"

_DEFAULT_REDIS_URL = "redis://127.0.0.1:6379/0"

# 进程内单例；未初始化或初始化失败时为 None
_redis_client: Redis | None = None


def _load_redis_url() -> str:
    """从 backend/.env 读取 REDIS_URL（不打印完整 URL 中的密码部分）。"""

    load_dotenv(_ENV_PATH)
    raw = os.getenv("REDIS_URL", _DEFAULT_REDIS_URL)
    url = (raw or "").strip() or _DEFAULT_REDIS_URL
    return url


def init_redis() -> bool:
    """
    创建并 ping 校验 Redis 客户端，成功则写入进程单例。

    返回 True 表示可用；失败时记录错误日志、清理半成品客户端，返回 False。
    不向调用方抛出异常（由 lifespan 决定是否继续启动）。
    """

    global _redis_client

    if _redis_client is not None:
        try:
            _redis_client.ping()
            logger.info("Redis 客户端已存在且 ping 成功，复用单例")
            return True
        except RedisError as exc:
            logger.warning("已有 Redis 客户端 ping 失败，将重建：%s", exc)
            _safe_close_client(_redis_client)
            _redis_client = None

    client: Redis | None = None
    try:
        url = _load_redis_url()
        # decode_responses=True：验证码等场景直接使用 str
        client = Redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        client.ping()
    except (RedisError, OSError, ValueError) as exc:
        logger.error(
            "Redis 初始化失败，应用将继续启动（登录 / MySQL / RAG 不受影响）：%s",
            exc,
        )
        if client is not None:
            _safe_close_client(client)
        _redis_client = None
        return False

    _redis_client = client
    logger.info("Redis 连接成功（单例已就绪）")
    return True


def get_redis() -> Redis | None:
    """
    获取进程内 Redis 单例。

    未初始化或初始化失败时返回 None；不在此处新建连接。
    """

    return _redis_client


def close_redis() -> None:
    """关闭 Redis 客户端并清空单例；可安全重复调用。"""

    global _redis_client

    client = _redis_client
    _redis_client = None
    if client is None:
        return

    _safe_close_client(client)
    logger.info("Redis 客户端已关闭")


def _safe_close_client(client: Redis) -> None:
    """关闭单个客户端；异常只记日志，不向外抛出。"""

    try:
        client.close()
    except Exception as exc:  # noqa: BLE001 — 关闭阶段必须吞掉，避免阻断 MySQL dispose
        logger.warning("关闭 Redis 客户端时出错（已忽略）：%s", exc)
