from app.database import get_db


def create_message(
    conversation_id: int,
    role: str,
    content: str,
):
    """
    创建一条聊天消息。
    """

    db = get_db()

    try:
        cursor = db.execute(
            """
            INSERT INTO messages (
                conversation_id,
                role,
                content
            )
            VALUES (?, ?, ?)
            """,
            (
                conversation_id,
                role,
                content,
            ),
        )

        db.commit()

        return cursor.lastrowid

    finally:
        db.close()
def get_messages_by_conversation(
    conversation_id: int,
):
    """
    获取指定会话的全部消息。

    按创建时间正序返回，
    保证聊天顺序正确。
    """

    db = get_db()

    try:
        cursor = db.execute(
            """
            SELECT
                id,
                conversation_id,
                role,
                content,
                created_at
            FROM messages
            WHERE conversation_id = ?
            ORDER BY id ASC
            """,
            (conversation_id,),
        )

        rows = cursor.fetchall()

        return [dict(row) for row in rows]

    finally:
        db.close()