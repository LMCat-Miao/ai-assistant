"""
会话表 Repository：创建 / 查询 / 更新 / 删除（SQLAlchemy Core + MySQL）。

所有按会话 id 的读改删均同时校验 user_id，防止跨用户操作。
"""

from __future__ import annotations

from sqlalchemy import text

from app.database import get_connection, get_engine


def create_conversation(
    user_id: int,
    title: str,
):
    """
    创建一个新的会话。
    """

    with get_connection() as conn:
        result = conn.execute(
            text(
                """
                INSERT INTO conversations (
                    user_id,
                    title
                )
                VALUES (
                    :user_id,
                    :title
                )
                """
            ),
            {
                "user_id": user_id,
                "title": title,
            },
        )
        conn.commit()
        return int(result.lastrowid)


def get_conversations_by_user(
    user_id: int,
):
    """
    获取当前用户的所有会话。
    """

    with get_connection() as conn:
        rows = conn.execute(
            text(
                """
                SELECT
                    id,
                    user_id,
                    title,
                    created_at,
                    updated_at
                FROM conversations
                WHERE user_id = :user_id
                ORDER BY updated_at DESC
                """
            ),
            {"user_id": user_id},
        ).mappings().all()

        return [dict(row) for row in rows]


def get_conversation(
    conversation_id: int,
    user_id: int,
):
    """
    获取当前用户指定的会话。
    """

    with get_connection() as conn:
        row = conn.execute(
            text(
                """
                SELECT
                    id,
                    user_id,
                    title,
                    created_at,
                    updated_at
                FROM conversations
                WHERE id = :conversation_id
                  AND user_id = :user_id
                """
            ),
            {
                "conversation_id": conversation_id,
                "user_id": user_id,
            },
        ).mappings().first()

        if row is None:
            return None

        return dict(row)


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

    with get_engine().begin() as conn:
        # 1. 归属校验（与 get_conversation 一致）
        owned = conn.execute(
            text(
                """
                SELECT id
                FROM conversations
                WHERE id = :conversation_id
                  AND user_id = :user_id
                """
            ),
            {
                "conversation_id": conversation_id,
                "user_id": user_id,
            },
        ).first()

        if owned is None:
            return False

        # 2. 先删消息，再删会话（同一事务；begin() 结束时自动提交）
        conn.execute(
            text(
                """
                DELETE FROM messages
                WHERE conversation_id = :conversation_id
                """
            ),
            {"conversation_id": conversation_id},
        )

        conn.execute(
            text(
                """
                DELETE FROM conversations
                WHERE id = :conversation_id
                  AND user_id = :user_id
                """
            ),
            {
                "conversation_id": conversation_id,
                "user_id": user_id,
            },
        )

        return True


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

    with get_connection() as conn:
        result = conn.execute(
            text(
                """
                UPDATE conversations
                SET title = :title,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :conversation_id
                  AND user_id = :user_id
                """
            ),
            {
                "title": title,
                "conversation_id": conversation_id,
                "user_id": user_id,
            },
        )
        conn.commit()
        return result.rowcount > 0
