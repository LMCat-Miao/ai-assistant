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
) -> bool:
    """
    删除当前用户指定的会话，并清理关联消息。

    在同一连接、同一事务中完成：
    1. 确认会话属于当前用户
    2. 删除该会话下的全部 messages
    3. 删除 conversations 记录

    任一失败则 rollback，避免只删了一半。

    返回：
        True  删除成功
        False 会话不存在或不属于该用户
    """

    db = get_db()

    try:
        # 1. 归属校验（与 get_conversation 一致）
        cursor = db.execute(
            """
            SELECT id
            FROM conversations
            WHERE id = ?
              AND user_id = ?
            """,
            (
                conversation_id,
                user_id,
            ),
        )

        if cursor.fetchone() is None:
            return False

        # 2. 先删消息，再删会话（同一事务）
        db.execute(
            """
            DELETE FROM messages
            WHERE conversation_id = ?
            """,
            (conversation_id,),
        )

        db.execute(
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
        return True

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


def update_conversation_title(
    conversation_id: int,
    user_id: int,
    title: str,
) -> bool:
    """
    更新当前用户指定会话的标题，并刷新 updated_at。

    返回：
        True  更新成功
        False 会话不存在或不属于该用户
    """

    db = get_db()

    try:
        cursor = db.execute(
            """
            UPDATE conversations
            SET title = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
              AND user_id = ?
            """,
            (
                title,
                conversation_id,
                user_id,
            ),
        )

        db.commit()
        return cursor.rowcount > 0

    finally:
        db.close()
