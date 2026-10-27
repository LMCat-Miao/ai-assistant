"""
用户种子 / 迁移辅助：可重复执行，不覆盖已有密码。
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from app.core.password import hash_password
from app.repositories.user_repository import create_user, get_user_by_username


# 与历史账号兼容：首次迁移时写入 id=1
ADMIN_USER_ID = 1
ADMIN_USERNAME = "admin"

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_BACKEND_ROOT / ".env")


def ensure_admin_user() -> str:
    """
    确保 admin 用户存在且优先使用 id=1。

    - 若 username=admin 已存在：跳过，绝不改密码（现有账号可继续登录）。
    - 若不存在：仅当环境变量 ADMIN_INITIAL_PASSWORD 已设置时创建；
      源码中不再包含弱默认口令。
    """

    existing = get_user_by_username(ADMIN_USERNAME)
    if existing is not None:
        return (
            f"admin 已存在（id={existing['id']}），跳过迁移，不覆盖密码"
        )

    password = os.getenv("ADMIN_INITIAL_PASSWORD", "").strip()
    if not password:
        raise RuntimeError(
            "数据库中尚无 admin 用户，且未设置 ADMIN_INITIAL_PASSWORD。"
            "请在 backend/.env 中设置首次管理员密码后再启动；"
            "若 admin 已存在则无需该变量，也不会覆盖现有密码。"
        )

    # 拒绝把常见弱口令写进新库（已有账号不受影响）。
    if password in {"123456", "password", "admin", "admin123"}:
        raise RuntimeError(
            "ADMIN_INITIAL_PASSWORD 过于弱，请更换为更强的初始密码。"
        )

    password_hash = hash_password(password)
    created_id = create_user(
        username=ADMIN_USERNAME,
        password_hash=password_hash,
        user_id=ADMIN_USER_ID,
    )
    return (
        f"已创建 admin（id={created_id}），"
        f"初始密码来自环境变量 ADMIN_INITIAL_PASSWORD（仅首次）"
    )
