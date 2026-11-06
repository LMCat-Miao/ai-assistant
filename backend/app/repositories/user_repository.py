"""
用户表 Repository：查询与创建用户（SQLAlchemy Core + MySQL）。
"""

from __future__ import annotations

from sqlalchemy import text

from app.database import get_connection


def get_user_by_username(username: str) -> dict | None:
    """按用户名查询用户；不存在返回 None。"""

    with get_connection() as conn:
        row = conn.execute(
            text(
                """
                SELECT
                    id,
                    username,
                    password_hash,
                    created_at
                FROM users
                WHERE username = :username
                """
            ),
            {"username": username},
        ).mappings().first()

        if row is None:
            return None
        return dict(row)


def get_user_by_id(user_id: int) -> dict | None:
    """按 ID 查询用户。"""

    with get_connection() as conn:
        row = conn.execute(
            text(
                """
                SELECT
                    id,
                    username,
                    password_hash,
                    created_at
                FROM users
                WHERE id = :user_id
                """
            ),
            {"user_id": user_id},
        ).mappings().first()

        if row is None:
            return None
        return dict(row)


def create_user(
    username: str,
    password_hash: str,
    user_id: int | None = None,
) -> int:
    """
    创建用户。

    若指定 user_id（如 admin=1），则按固定主键插入；
    否则使用自增 ID。
    不写入 email（保持 NULL），不修改已有用户。
    """

    with get_connection() as conn:
        if user_id is not None:
            result = conn.execute(
                text(
                    """
                    INSERT INTO users (id, username, password_hash)
                    VALUES (:id, :username, :password_hash)
                    """
                ),
                {
                    "id": user_id,
                    "username": username,
                    "password_hash": password_hash,
                },
            )
        else:
            result = conn.execute(
                text(
                    """
                    INSERT INTO users (username, password_hash)
                    VALUES (:username, :password_hash)
                    """
                ),
                {
                    "username": username,
                    "password_hash": password_hash,
                },
            )

        conn.commit()
        return int(result.lastrowid)
