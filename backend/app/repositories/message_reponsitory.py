"""
消息表 Repository：创建与按会话查询（SQLAlchemy Core + MySQL）。

说明：
- 本模块按 conversation_id 读写；用户归属校验由调用方
  （conversations / messages API、chat_service）先执行 get_conversation。
- citations_json 以文本形式存取（与 MySQL MEDIUMTEXT 一致），不改列类型。
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text

from app.database import get_connection


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

    with get_connection() as conn:
        result = conn.execute(
            text(
                """
                INSERT INTO messages (
                    conversation_id,
                    role,
                    content,
                    citations_json
                )
                VALUES (
                    :conversation_id,
                    :role,
                    :content,
                    :citations_json
                )
                """
            ),
            {
                "conversation_id": conversation_id,
                "role": role,
                "content": content,
                "citations_json": _serialize_citations(citations),
            },
        )
        conn.commit()
        return int(result.lastrowid)


def get_messages_by_conversation(
    conversation_id: int,
):
    """
    获取指定会话的全部消息。

    按创建时间正序返回（ORDER BY id ASC），
    保证聊天顺序正确。
    """

    with get_connection() as conn:
        rows = conn.execute(
            text(
                """
                SELECT
                    id,
                    conversation_id,
                    role,
                    content,
                    created_at,
                    citations_json
                FROM messages
                WHERE conversation_id = :conversation_id
                ORDER BY id ASC
                """
            ),
            {"conversation_id": conversation_id},
        ).mappings().all()

        messages: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["citations"] = _parse_citations_json(
                item.pop("citations_json", None)
            )
            messages.append(item)

        return messages
