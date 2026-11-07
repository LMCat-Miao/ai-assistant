"""
用户表 Repository：查询与创建用户（SQLAlchemy Core + MySQL）。
"""

from __future__ import annotations

from sqlalchemy import text

from app.database import get_connection


def _normalize_email(email: str) -> str:
    return email.strip().lower()


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


def get_user_by_email(email: str) -> dict | None:
    """按邮箱查询用户；不存在返回 None。邮箱先 strip + lower。"""

    normalized = _normalize_email(email)
    if not normalized:
        return None

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
                WHERE email = :email
                """
            ),
            {"email": normalized},
        ).mappings().first()

        if row is None:
            return None
        return dict(row)


def create_user(
    username: str,
    password_hash: str,
    user_id: int | None = None,
    email: str | None = None,
) -> int:
    """
    创建用户。

    若指定 user_id（如 admin=1），则按固定主键插入；
    否则使用自增 ID。
    email 默认 None（写入 NULL），兼容管理员 seed 与旧调用方；
    传入 email 时会 strip + lower 后写入。
    不修改已有用户；唯一约束冲突时回滚并向上抛出。
    """

    normalized_email: str | None = None
    if email is not None:
        normalized_email = _normalize_email(email) or None

    with get_connection() as conn:
        try:
            if user_id is not None:
                result = conn.execute(
                    text(
                        """
                        INSERT INTO users (id, username, password_hash, email)
                        VALUES (:id, :username, :password_hash, :email)
                        """
                    ),
                    {
                        "id": user_id,
                        "username": username,
                        "password_hash": password_hash,
                        "email": normalized_email,
                    },
                )
            else:
                result = conn.execute(
                    text(
                        """
                        INSERT INTO users (username, password_hash, email)
                        VALUES (:username, :password_hash, :email)
                        """
                    ),
                    {
                        "username": username,
                        "password_hash": password_hash,
                        "email": normalized_email,
                    },
                )

            conn.commit()
            return int(result.lastrowid)
        except Exception:
            conn.rollback()
            raise
