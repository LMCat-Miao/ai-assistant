"""
实验用混合检索：Dense（BGE+Chroma）+ Sparse（BM25）+ RRF 融合。

- 只读 Chroma（get / query），不写入
- 不修改生产 retrieve_knowledge
- BM25 语料来自 Chroma 已存 documents，与向量库 ID 对齐
"""

from __future__ import annotations

import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.rag.vector_store import VectorStore
from app.services.rag_ingestion_service import get_embedding_model


DEFAULT_CANDIDATE_K = 20
DEFAULT_RRF_K = 60
DEFAULT_TOP_K = 3

# RRF 同分打破策略（不改变 RRF 公式本身）
RRF_TIE_BREAK_DENSE_FIRST = "dense_first"
RRF_TIE_BREAK_BM25 = "bm25_tiebreak"
DEFAULT_RRF_TIE_BREAK = RRF_TIE_BREAK_DENSE_FIRST
_MISSING_RANK = 10**9

# 中文：连续汉字切成重叠 bigram；英文/数字保留为整词。
_CJK_CHAR = re.compile(r"[\u4e00-\u9fff]")
_LATIN_WORD = re.compile(r"[A-Za-z0-9_]+", re.UNICODE)
_TOKEN_SPLIT = re.compile(
    r"([\u4e00-\u9fff]+|[A-Za-z0-9_]+)",
    re.UNICODE,
)


def build_chroma_where(
    user_id: str,
    filename: str | None = None,
) -> dict[str, Any]:
    """与生产 retrieve_knowledge 一致的 metadata 过滤。"""

    if not user_id:
        raise ValueError("用户 ID 不能为空。")

    if filename:
        return {
            "$and": [
                {"user_id": {"$eq": str(user_id)}},
                {"source": {"$eq": filename}},
            ]
        }
    return {"user_id": {"$eq": str(user_id)}}


def tokenize_for_bm25(text: str) -> list[str]:
    """实验用中文分词：汉字重叠 bigram + 拉丁整词（小写）。

    局限：无 jieba 词表，专名/多字词依赖字符 bigram 共现，
    对同义改写弱于语义向量；空格分词对中文不够用，故不采用。
    """

    if not text:
        return []

    tokens: list[str] = []
    for part in _TOKEN_SPLIT.findall(text):
        if _CJK_CHAR.search(part):
            chars = list(part)
            if len(chars) == 1:
                tokens.append(chars[0])
            else:
                tokens.extend(chars[i] + chars[i + 1] for i in range(len(chars) - 1))
        else:
            word = part.lower()
            if word:
                tokens.append(word)
    return tokens


@dataclass
class CorpusChunk:
    id: str
    document: str
    metadata: dict[str, Any]


class BM25Index:
    """轻量 Okapi BM25（实验内实现，不依赖 rank_bm25）。"""

    def __init__(
        self,
        corpus_tokens: list[list[str]],
        *,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        self.k1 = k1
        self.b = b
        self.corpus_tokens = corpus_tokens
        self.doc_count = len(corpus_tokens)
        self.doc_len = [len(doc) for doc in corpus_tokens]
        self.avgdl = (
            sum(self.doc_len) / self.doc_count if self.doc_count else 0.0
        )

        self.df: dict[str, int] = {}
        for doc in corpus_tokens:
            for term in set(doc):
                self.df[term] = self.df.get(term, 0) + 1

        self.idf: dict[str, float] = {}
        for term, freq in self.df.items():
            # 标准 BM25 idf，避免负值：log(1 + (N - n + 0.5)/(n + 0.5))
            self.idf[term] = math.log(
                1.0 + (self.doc_count - freq + 0.5) / (freq + 0.5)
            )

    def score_document(self, query_tokens: list[str], doc_index: int) -> float:
        if self.doc_count == 0 or not query_tokens:
            return 0.0

        doc = self.corpus_tokens[doc_index]
        if not doc:
            return 0.0

        tf: dict[str, int] = {}
        for term in doc:
            tf[term] = tf.get(term, 0) + 1

        score = 0.0
        dl = self.doc_len[doc_index]
        for term in query_tokens:
            if term not in tf:
                continue
            idf = self.idf.get(term, 0.0)
            freq = tf[term]
            denom = freq + self.k1 * (
                1.0 - self.b + self.b * dl / self.avgdl
            )
            score += idf * (freq * (self.k1 + 1.0) / denom)
        return score

    def ranked_indices(
        self,
        query_tokens: list[str],
        *,
        top_k: int,
    ) -> list[tuple[int, float]]:
        if self.doc_count == 0 or top_k < 1 or not query_tokens:
            return []

        scored = [
            (index, self.score_document(query_tokens, index))
            for index in range(self.doc_count)
        ]
        scored.sort(key=lambda item: item[1], reverse=True)
        # 仅保留正分，避免全零噪声占满候选
        positive = [item for item in scored if item[1] > 0.0]
        return positive[:top_k]


def reciprocal_rank_fusion(
    ranked_id_lists: list[list[str]],
    *,
    k: int = DEFAULT_RRF_K,
    tie_break: str = DEFAULT_RRF_TIE_BREAK,
    dense_rank_by_id: dict[str, int] | None = None,
    bm25_rank_by_id: dict[str, int] | None = None,
) -> list[tuple[str, float]]:
    """按文档 ID 融合多路排名。缺失的一路不贡献分数。

    tie_break:
      - dense_first: 分数相同时保持首次出现顺序（先扫 dense 列表，与 v1 行为一致）
      - bm25_tiebreak: 分数相同时优先更小的 bm25_rank；仍缺则用 dense_rank，再用 id
    """

    if k < 0:
        raise ValueError("rrf_k 必须大于等于 0")
    if tie_break not in {
        RRF_TIE_BREAK_DENSE_FIRST,
        RRF_TIE_BREAK_BM25,
    }:
        raise ValueError(
            f"未知 tie_break={tie_break!r}；"
            f"可选 {RRF_TIE_BREAK_DENSE_FIRST!r} / {RRF_TIE_BREAK_BM25!r}"
        )

    scores: dict[str, float] = {}
    insertion_order: dict[str, int] = {}
    for ranked_ids in ranked_id_lists:
        seen: set[str] = set()
        for rank, doc_id in enumerate(ranked_ids, start=1):
            if not doc_id or doc_id in seen:
                continue
            seen.add(doc_id)
            if doc_id not in insertion_order:
                insertion_order[doc_id] = len(insertion_order)
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)

    dense_rank_by_id = dense_rank_by_id or {}
    bm25_rank_by_id = bm25_rank_by_id or {}

    def sort_key(item: tuple[str, float]) -> tuple:
        doc_id, score = item
        # 主键：分数降序 → 用负分做升序比较
        if tie_break == RRF_TIE_BREAK_BM25:
            bm25_rank = bm25_rank_by_id.get(doc_id)
            dense_rank = dense_rank_by_id.get(doc_id)
            return (
                -score,
                bm25_rank if bm25_rank is not None else _MISSING_RANK,
                dense_rank if dense_rank is not None else _MISSING_RANK,
                doc_id,
            )
        # dense_first：与 v1 稳定排序等价——同分按首次插入顺序
        return (
            -score,
            insertion_order.get(doc_id, _MISSING_RANK),
            doc_id,
        )

    return sorted(scores.items(), key=sort_key)


def load_corpus_from_chroma(
    store: VectorStore,
    *,
    user_id: str,
    filename: str | None = None,
) -> list[CorpusChunk]:
    """只读加载与过滤条件一致的 Chroma 文档。"""

    where = build_chroma_where(user_id, filename)
    rows = store.get_chunks(where=where, include=["documents", "metadatas"])
    chunks: list[CorpusChunk] = []
    for doc_id, document, metadata in zip(
        rows.get("ids") or [],
        rows.get("documents") or [],
        rows.get("metadatas") or [],
    ):
        if not doc_id:
            continue
        meta = metadata if isinstance(metadata, dict) else {}
        chunks.append(
            CorpusChunk(
                id=str(doc_id),
                document=str(document or ""),
                metadata=meta,
            )
        )
    return chunks


def _dense_rank_list(
    store: VectorStore,
    *,
    query: str,
    user_id: str,
    filename: str | None,
    candidate_k: int,
) -> tuple[list[str], dict[str, dict[str, Any]]]:
    """返回 (按 dense 排名的 id 列表, id -> 检索记录)。"""

    model = get_embedding_model()
    query_embedding = model.encode(
        query,
        normalize_embeddings=True,
        show_progress_bar=False,
    ).tolist()

    where = build_chroma_where(user_id, filename)
    raw = store.search(
        query_embedding=query_embedding,
        top_k=candidate_k,
        where=where,
    )

    ranked_ids: list[str] = []
    by_id: dict[str, dict[str, Any]] = {}
    for item in raw:
        doc_id = str(item.get("id") or "")
        if not doc_id or doc_id in by_id:
            continue
        ranked_ids.append(doc_id)
        meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        by_id[doc_id] = {
            "id": doc_id,
            "content": str(item.get("document") or ""),
            "source": meta.get("source"),
            "page": meta.get("page"),
            "distance": item.get("distance"),
            "metadata": meta,
        }
    return ranked_ids, by_id


def _bm25_rank_list(
    corpus: list[CorpusChunk],
    *,
    query: str,
    candidate_k: int,
) -> tuple[list[str], dict[str, dict[str, Any]], BM25Index | None]:
    if not corpus:
        return [], {}, None

    tokenized = [tokenize_for_bm25(chunk.document) for chunk in corpus]
    index = BM25Index(tokenized)
    query_tokens = tokenize_for_bm25(query)
    ranked = index.ranked_indices(query_tokens, top_k=candidate_k)

    ranked_ids: list[str] = []
    by_id: dict[str, dict[str, Any]] = {}
    for doc_index, score in ranked:
        chunk = corpus[doc_index]
        if chunk.id in by_id:
            continue
        ranked_ids.append(chunk.id)
        by_id[chunk.id] = {
            "id": chunk.id,
            "content": chunk.document,
            "source": chunk.metadata.get("source"),
            "page": chunk.metadata.get("page"),
            "distance": None,
            "bm25_score": score,
            "metadata": chunk.metadata,
        }
    return ranked_ids, by_id, index


def _merge_records(
    *maps: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for mapping in maps:
        for doc_id, record in mapping.items():
            if doc_id not in merged:
                merged[doc_id] = dict(record)
            else:
                existing = merged[doc_id]
                for key, value in record.items():
                    if key == "distance" and existing.get("distance") is None:
                        existing["distance"] = value
                    elif key == "bm25_score" and "bm25_score" not in existing:
                        existing["bm25_score"] = value
                    elif key not in existing or existing[key] in (None, ""):
                        existing[key] = value
    return merged


def _attach_ranks(
    records: dict[str, dict[str, Any]],
    dense_ids: list[str],
    bm25_ids: list[str],
) -> None:
    dense_rank = {doc_id: rank for rank, doc_id in enumerate(dense_ids, start=1)}
    bm25_rank = {doc_id: rank for rank, doc_id in enumerate(bm25_ids, start=1)}
    for doc_id, record in records.items():
        record["dense_rank"] = dense_rank.get(doc_id)
        record["bm25_rank"] = bm25_rank.get(doc_id)


def _finalize_results(
    ordered_ids: list[str],
    records: dict[str, dict[str, Any]],
    *,
    top_k: int,
    rrf_scores: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for doc_id in ordered_ids:
        if not doc_id or doc_id in seen:
            continue
        seen.add(doc_id)
        record = records.get(doc_id)
        if not record:
            continue
        item = {
            "content": record.get("content") or "",
            "source": record.get("source"),
            "page": record.get("page"),
            "distance": record.get("distance"),
            "id": doc_id,
            "dense_rank": record.get("dense_rank"),
            "bm25_rank": record.get("bm25_rank"),
            "rrf_score": None if rrf_scores is None else rrf_scores.get(doc_id),
        }
        if "bm25_score" in record:
            item["bm25_score"] = record.get("bm25_score")
        results.append(item)
        if len(results) >= top_k:
            break
    return results


def retrieve_dense_only(
    query: str,
    user_id: str,
    *,
    top_k: int = DEFAULT_TOP_K,
    filename: str | None = None,
    candidate_k: int = DEFAULT_CANDIDATE_K,
    store: VectorStore | None = None,
) -> list[dict[str, Any]]:
    query = (query or "").strip()
    if not query:
        raise ValueError("检索问题不能为空。")
    if not 1 <= top_k <= 10:
        raise ValueError("top_k 必须在 1 到 10 之间。")
    if candidate_k < 1:
        raise ValueError("candidate_k 必须大于等于 1")

    store = store or VectorStore()
    dense_ids, dense_map = _dense_rank_list(
        store,
        query=query,
        user_id=str(user_id),
        filename=filename,
        candidate_k=max(candidate_k, top_k),
    )
    _attach_ranks(dense_map, dense_ids, [])
    return _finalize_results(dense_ids, dense_map, top_k=top_k, rrf_scores=None)


def retrieve_bm25_only(
    query: str,
    user_id: str,
    *,
    top_k: int = DEFAULT_TOP_K,
    filename: str | None = None,
    candidate_k: int = DEFAULT_CANDIDATE_K,
    store: VectorStore | None = None,
    corpus: list[CorpusChunk] | None = None,
) -> list[dict[str, Any]]:
    query = (query or "").strip()
    if not query:
        raise ValueError("检索问题不能为空。")
    if not 1 <= top_k <= 10:
        raise ValueError("top_k 必须在 1 到 10 之间。")
    if candidate_k < 1:
        raise ValueError("candidate_k 必须大于等于 1")

    store = store or VectorStore()
    if corpus is None:
        corpus = load_corpus_from_chroma(
            store,
            user_id=str(user_id),
            filename=filename,
        )
    bm25_ids, bm25_map, _ = _bm25_rank_list(
        corpus,
        query=query,
        candidate_k=max(candidate_k, top_k),
    )
    _attach_ranks(bm25_map, [], bm25_ids)
    return _finalize_results(bm25_ids, bm25_map, top_k=top_k, rrf_scores=None)


def retrieve_hybrid_rrf(
    query: str,
    user_id: str,
    *,
    top_k: int = DEFAULT_TOP_K,
    filename: str | None = None,
    candidate_k: int = DEFAULT_CANDIDATE_K,
    rrf_k: int = DEFAULT_RRF_K,
    rrf_tie_break: str = DEFAULT_RRF_TIE_BREAK,
    store: VectorStore | None = None,
    corpus: list[CorpusChunk] | None = None,
) -> list[dict[str, Any]]:
    """Dense + BM25，按 Chroma ID 做 RRF；单路缺失时仍可用另一路。"""

    query = (query or "").strip()
    if not query:
        raise ValueError("检索问题不能为空。")
    if not user_id:
        raise ValueError("用户 ID 不能为空。")
    if not 1 <= top_k <= 10:
        raise ValueError("top_k 必须在 1 到 10 之间。")
    if candidate_k < 1:
        raise ValueError("candidate_k 必须大于等于 1")
    if rrf_k < 0:
        raise ValueError("rrf_k 必须大于等于 0")

    store = store or VectorStore()
    pool = max(candidate_k, top_k)

    dense_ids, dense_map = _dense_rank_list(
        store,
        query=query,
        user_id=str(user_id),
        filename=filename,
        candidate_k=pool,
    )

    if corpus is None:
        corpus = load_corpus_from_chroma(
            store,
            user_id=str(user_id),
            filename=filename,
        )
    bm25_ids, bm25_map, _ = _bm25_rank_list(
        corpus,
        query=query,
        candidate_k=pool,
    )

    records = _merge_records(dense_map, bm25_map)
    # 补全仅出现在另一路、但语料里有的文档字段
    corpus_by_id = {chunk.id: chunk for chunk in corpus}
    for doc_id, record in list(records.items()):
        if doc_id in corpus_by_id:
            chunk = corpus_by_id[doc_id]
            if not record.get("content"):
                record["content"] = chunk.document
            if record.get("source") is None:
                record["source"] = chunk.metadata.get("source")
            if record.get("page") is None:
                record["page"] = chunk.metadata.get("page")

    _attach_ranks(records, dense_ids, bm25_ids)

    dense_rank_by_id = {
        doc_id: rank for rank, doc_id in enumerate(dense_ids, start=1)
    }
    bm25_rank_by_id = {
        doc_id: rank for rank, doc_id in enumerate(bm25_ids, start=1)
    }
    fused = reciprocal_rank_fusion(
        [dense_ids, bm25_ids],
        k=rrf_k,
        tie_break=rrf_tie_break,
        dense_rank_by_id=dense_rank_by_id,
        bm25_rank_by_id=bm25_rank_by_id,
    )
    rrf_scores = {doc_id: score for doc_id, score in fused}
    ordered_ids = [doc_id for doc_id, _ in fused]
    return _finalize_results(
        ordered_ids,
        records,
        top_k=top_k,
        rrf_scores=rrf_scores,
    )
