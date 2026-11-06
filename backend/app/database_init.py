"""
应用启动时的数据库安全检查（MySQL）。

不再创建 / 重建表，也不迁移数据。
仅验证连通性与业务表是否存在，然后执行可重复的 admin 种子逻辑。
"""

from __future__ import annotations

from sqlalchemy import text

from app.database import get_connection
from app.services.user_seed import ensure_admin_user


REQUIRED_TABLES = ("users", "conversations", "messages")
EXPECTED_DATABASE = "ai_assistant"


def init_database() -> None:
    """
    FastAPI 启动入口（函数名保持不变，供 main.py 调用）。

    1. 检查 MySQL 可连接且当前库为 ai_assistant
    2. 检查 users / conversations / messages 是否存在（缺失则报错，不建表）
    3. 调用 ensure_admin_user()（admin 已存在则跳过，不覆盖密码）
    """

    with get_connection() as conn:
        current_db = conn.execute(text("SELECT DATABASE()")).scalar_one()
        if current_db is None or str(current_db) != EXPECTED_DATABASE:
            raise RuntimeError(
                "当前连接的数据库不是 "
                f"{EXPECTED_DATABASE!r}，实际为 {current_db!r}。"
                "请检查 backend/.env 中的 MYSQL_DATABASE。"
            )

        print(f"✅ MySQL 连接成功，当前数据库：{current_db}")

        existing = {
            str(row[0])
            for row in conn.execute(
                text(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = :schema
                      AND table_type = 'BASE TABLE'
                    """
                ),
                {"schema": EXPECTED_DATABASE},
            )
        }

        # MySQL information_schema 在部分配置下可能返回大小写不一的表名
        existing_lower = {name.lower() for name in existing}
        missing = [
            name
            for name in REQUIRED_TABLES
            if name.lower() not in existing_lower
        ]
        if missing:
            raise RuntimeError(
                "MySQL 缺少业务表，拒绝启动（不会自动建表）："
                + ", ".join(missing)
                + "。请确认已完成建表与数据迁移。"
            )

        print(
            "✅ 数据库 ai_assistant 检查通过；"
            "users / conversations / messages 表检查通过"
        )

    # 表检查通过后再做 admin 种子（内部走 user_repository → MySQL）
    try:
        message = ensure_admin_user()
        print(f"✅ 用户初始化：{message}")
    except Exception as exc:
        # 明确失败，不静默忽略
        raise RuntimeError(
            f"用户种子 ensure_admin_user() 失败：{exc}"
        ) from exc
