import json
from typing import Any

from app.database import get_db


def _serialize_citations(
    citations: list[dict[str, Any]] | None,
) -> str | None:
    if not citations:
        return None
    return json.dumps(citations, ensure_ascii=False)


def _parse_citations_json(raw: Any) -> list[dict[str, Any]] | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, list):
        return raw
    if not isinstance(raw, str):
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if isinstance(data, list):
        return data
    return None


def create_message(
    conversation_id: int,
    role: str,
    content: str,
    citations: list[dict[str, Any]] | None = None,
):
    """
    创建一条聊天消息。

    citations:
        可选，RAG 检索到来源列表；普通聊天传 None。
    """

    db = get_db()

    try:
        cursor = db.execute(
            """
            INSERT INTO messages (
                conversation_id,
                role,
                content,
                citations_json
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                conversation_id,
                role,
                content,
                _serialize_citations(citations),
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
                created_at,
                citations_json
            FROM messages
            WHERE conversation_id = ?
            ORDER BY id ASC
            """,
            (conversation_id,),
        )

        rows = cursor.fetchall()
        messages: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["citations"] = _parse_citations_json(
                item.pop("citations_json", None)
            )
            messages.append(item)

        return messages

    finally:
        db.close()
