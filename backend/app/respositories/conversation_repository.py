from app.database import get_db


def create_conversation(
    user_id: int,
    title: str,
):
    """
    创建一个新的会话。
    """

    db = get_db()

    try:
        cursor = db.execute(
            """
            INSERT INTO conversations (
                user_id,
                title
            )
            VALUES (?, ?)
            """,
            (
                user_id,
                title,
            ),
        )

        db.commit()

        return cursor.lastrowid

    finally:
        db.close()


def get_conversations_by_user(
    user_id: int,
):
    """
    获取当前用户的所有会话。
    """

    db = get_db()

    try:
        cursor = db.execute(
            """
            SELECT
                id,
                user_id,
                title,
                created_at,
                updated_at
            FROM conversations
            WHERE user_id = ?
            ORDER BY updated_at DESC
            """,
            (user_id,),
        )

        rows = cursor.fetchall()

        return [dict(row) for row in rows]

    finally:
        db.close()


def get_conversation(
    conversation_id: int,
    user_id: int,
):
    """
    获取当前用户指定的会话。
    """

    db = get_db()

    try:
        cursor = db.execute(
            """
            SELECT
                id,
                user_id,
                title,
                created_at,
                updated_at
            FROM conversations
            WHERE id = ?
              AND user_id = ?
            """,
            (
                conversation_id,
                user_id,
            ),
        )

        row = cursor.fetchone()

        if row is None:
            return None

        return dict(row)

    finally:
        db.close()


def delete_conversation(
    conversation_id: int,
    user_id: int,
):
    """
    删除当前用户指定的会话。
    """

    db = get_db()

    try:
        cursor = db.execute(
            """
            DELETE FROM conversations
            WHERE id = ?
              AND user_id = ?
            """,
            (
                conversation_id,
                user_id,
            ),
        )

        db.commit()

        return cursor.rowcount > 0

    finally:
        db.close()