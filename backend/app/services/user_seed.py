"""
用户种子 / 迁移辅助：可重复执行，不覆盖已有密码。
"""

from __future__ import annotations

from app.core.password import hash_password
from app.repositories.user_repository import create_user, get_user_by_username


# 与历史硬编码账号兼容：首次迁移时写入 id=1
ADMIN_USER_ID = 1
ADMIN_USERNAME = "admin"
# 仅用于「首次」创建 admin；已存在则绝不覆盖
ADMIN_DEFAULT_PASSWORD = "123456"


def ensure_admin_user() -> str:
    """
    确保 admin 用户存在且 id=1。

    - 若 username=admin 已存在：跳过，不改密码。
    - 若不存在：插入 id=1，密码为历史默认 123456 的 bcrypt 哈希。

    返回说明字符串，便于日志打印。
    """

    existing = get_user_by_username(ADMIN_USERNAME)
    if existing is not None:
        return (
            f"admin 已存在（id={existing['id']}），跳过迁移，不覆盖密码"
        )

    password_hash = hash_password(ADMIN_DEFAULT_PASSWORD)
    created_id = create_user(
        username=ADMIN_USERNAME,
        password_hash=password_hash,
        user_id=ADMIN_USER_ID,
    )
    return (
        f"已创建 admin（id={created_id}），"
        f"初始密码与历史硬编码一致（仅首次）"
    )
