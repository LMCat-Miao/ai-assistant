"""从检索结果构建可展示的知识库引用来源（非模型编造）。"""

from __future__ import annotations

from typing import Any, Literal


KnowledgeStatus = Literal["none", "hit", "empty"]

# 引用片段最大字符数，避免响应头过大。
MAX_SNIPPET_CHARS = 180


def build_citations_from_chunks(
    chunks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """将检索命中整理为引用列表。

    - 只使用检索结果中的 source / page / content / distance
    - 同一 filename + page 合并，保留最短距离与代表性片段
    - 不声称这些来源等于模型「实际使用」的证据对齐结果
    """

    merged: dict[tuple[str, int | None], dict[str, Any]] = {}

    for chunk in chunks:
        raw_source = chunk.get("source")
        if not isinstance(raw_source, str) or not raw_source.strip():
            # 缺少真实文件名时不伪造文件名，跳过该条引用展示。
            continue

        filename = raw_source.strip()
        page_raw = chunk.get("page")
        page: int | None
        try:
            page = int(page_raw) if page_raw is not None else None
        except (TypeError, ValueError):
            page = None

        content = str(chunk.get("content") or "").strip()
        snippet = content[:MAX_SNIPPET_CHARS]
        if len(content) > MAX_SNIPPET_CHARS:
            snippet = snippet.rstrip() + "…"

        distance_raw = chunk.get("distance")
        try:
            distance = float(distance_raw) if distance_raw is not None else None
        except (TypeError, ValueError):
            distance = None

        key = (filename, page)
        existing = merged.get(key)
        if existing is None:
            merged[key] = {
                "filename": filename,
                "page": page,
                "snippet": snippet,
                "distance": distance,
                "chunk_count": 1,
            }
            continue

        existing["chunk_count"] = int(existing.get("chunk_count") or 1) + 1
        # 保留更近的距离及对应片段（L2：越小越近）。
        prev_distance = existing.get("distance")
        if distance is not None and (
            prev_distance is None or distance < float(prev_distance)
        ):
            existing["distance"] = distance
            if snippet:
                existing["snippet"] = snippet

    citations = list(merged.values())
    citations.sort(
        key=lambda item: (
            float(item["distance"])
            if item.get("distance") is not None
            else 1e9,
            str(item.get("filename") or ""),
            item.get("page") if item.get("page") is not None else 10**9,
        )
    )
    return citations
