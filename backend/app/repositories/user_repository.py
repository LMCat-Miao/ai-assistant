"""
用户表 Repository：查询与创建用户。
"""

from app.database import get_db


def get_user_by_username(username: str) -> dict | None:
    """按用户名查询用户；不存在返回 None。"""

    db = get_db()

    try:
        cursor = db.execute(
            """
            SELECT
                id,
                username,
                password_hash,
                created_at
            FROM users
            WHERE username = ?
            """,
            (username,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return dict(row)
    finally:
        db.close()


def get_user_by_id(user_id: int) -> dict | None:
    """按 ID 查询用户。"""

    db = get_db()

    try:
        cursor = db.execute(
            """
            SELECT
                id,
                username,
                password_hash,
                created_at
            FROM users
            WHERE id = ?
            """,
            (user_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return dict(row)
    finally:
        db.close()


def create_user(
    username: str,
    password_hash: str,
    user_id: int | None = None,
) -> int:
    """
    创建用户。

    若指定 user_id（如 admin=1），则按固定主键插入；
    否则使用自增 ID。
    """

    db = get_db()

    try:
        if user_id is not None:
            cursor = db.execute(
                """
                INSERT INTO users (id, username, password_hash)
                VALUES (?, ?, ?)
                """,
                (user_id, username, password_hash),
            )
        else:
            cursor = db.execute(
                """
                INSERT INTO users (username, password_hash)
                VALUES (?, ?)
                """,
                (username, password_hash),
            )

        db.commit()
        return int(cursor.lastrowid)
    finally:
        db.close()
