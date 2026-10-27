"""
混合检索实验评测入口（Dense / BM25 / Hybrid-RRF 对照）。

- 复用 evaluate_rag_retrieval.judge_hit 等命中规则，不改语义
- 只读 Chroma；输出独立带时间戳 JSON/CSV，不覆盖基线
- 不调用对话大模型
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS_DIR = Path(__file__).resolve().parent
for path in (str(EXPERIMENTS_DIR), str(BACKEND_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from evaluate_rag_retrieval import (  # noqa: E402
    is_labeled,
    judge_hit,
    load_cases,
    resolve_case_filename,
    summarize,
    truncate,
)
from hybrid_rrf_retrieve import (  # noqa: E402
    DEFAULT_CANDIDATE_K,
    DEFAULT_RRF_K,
    DEFAULT_RRF_TIE_BREAK,
    RRF_TIE_BREAK_BM25,
    RRF_TIE_BREAK_DENSE_FIRST,
    load_corpus_from_chroma,
    retrieve_bm25_only,
    retrieve_dense_only,
    retrieve_hybrid_rrf,
)
from app.rag.vector_store import VectorStore  # noqa: E402


DEFAULT_CASES = EXPERIMENTS_DIR / "rag_eval" / "eval_cases_v2.json"
DEFAULT_OUTPUT_DIR = EXPERIMENTS_DIR / "rag_eval" / "output"
FOCUS_CASE_IDS = (
    "agent_para_005",
    "resume_has_002",
    "resume_has_003",
    "resume_para_002",
)


def die(message: str, code: int = 1) -> None:
    print(f"[ERROR] {message}", file=sys.stderr)
    raise SystemExit(code)


def format_method_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(results, start=1):
        rows.append(
            {
                "rank": index,
                "id": item.get("id"),
                "source": item.get("source"),
                "page": item.get("page"),
                "distance": item.get("distance"),
                "dense_rank": item.get("dense_rank"),
                "bm25_rank": item.get("bm25_rank"),
                "rrf_score": item.get("rrf_score"),
                "bm25_score": item.get("bm25_score"),
                "snippet": truncate(str(item.get("content") or "")),
            }
        )
    return rows


def evaluate_case_three_ways(
    case: dict[str, Any],
    *,
    user_id: str,
    top_k: int,
    filename_filter: str | None,
    candidate_k: int,
    rrf_k: int,
    rrf_tie_break: str,
    store: VectorStore,
    corpus_cache: dict[str | None, list],
) -> dict[str, Any]:
    query = str(case.get("query") or "").strip()
    if not query or query.startswith("【") or "请改成" in query:
        return {
            "id": case.get("id"),
            "category": case.get("category"),
            "query": query,
            "error": "query 仍是模板占位或为空，已跳过检索",
            "skipped": True,
            "needs_human_review": True,
            "labeled": is_labeled(case),
        }

    case_filename = resolve_case_filename(case, filename_filter)
    cache_key = case_filename
    if cache_key not in corpus_cache:
        corpus_cache[cache_key] = load_corpus_from_chroma(
            store,
            user_id=str(user_id),
            filename=case_filename,
        )
    corpus = corpus_cache[cache_key]

    methods: dict[str, Any] = {}
    try:
        dense = retrieve_dense_only(
            query,
            str(user_id),
            top_k=top_k,
            filename=case_filename,
            candidate_k=candidate_k,
            store=store,
        )
        bm25 = retrieve_bm25_only(
            query,
            str(user_id),
            top_k=top_k,
            filename=case_filename,
            candidate_k=candidate_k,
            store=store,
            corpus=corpus,
        )
        hybrid = retrieve_hybrid_rrf(
            query,
            str(user_id),
            top_k=top_k,
            filename=case_filename,
            candidate_k=candidate_k,
            rrf_k=rrf_k,
            rrf_tie_break=rrf_tie_break,
            store=store,
            corpus=corpus,
        )
    except Exception as exc:
        return {
            "id": case.get("id"),
            "category": case.get("category"),
            "query": query,
            "filename_filter": case_filename,
            "error": str(exc),
            "skipped": False,
            "needs_human_review": True,
            "labeled": is_labeled(case),
        }

    for name, results in (
        ("dense", dense),
        ("bm25", bm25),
        ("hybrid_rrf", hybrid),
    ):
        top1 = judge_hit(case, results, top_n=1)
        top3 = judge_hit(case, results, top_n=min(3, top_k))
        methods[name] = {
            "result_count": len(results),
            "top1_judgment": top1,
            "top3_judgment": top3,
            "results": format_method_results(results),
        }

    return {
        "id": case.get("id"),
        "category": case.get("category"),
        "query": query,
        "notes": case.get("notes"),
        "filename_filter": case_filename,
        "expected_source": case.get("expected_source"),
        "expected_page": case.get("expected_page"),
        "expected_evidence": case.get("expected_evidence"),
        "labeled": is_labeled(case),
        "needs_human_review": True,
        "methods": methods,
        # 兼容 summarize：以 hybrid 作为主判定字段副本
        "top1_judgment": methods["hybrid_rrf"]["top1_judgment"],
        "top3_judgment": methods["hybrid_rrf"]["top3_judgment"],
    }


def summarize_by_method(rows: list[dict[str, Any]]) -> dict[str, Any]:
    labeled = [
        r
        for r in rows
        if r.get("labeled") and not r.get("skipped") and "error" not in r
    ]
    out: dict[str, Any] = {
        "total_cases": len(rows),
        "labeled_cases": len(labeled),
        "unlabeled_cases": sum(
            1 for r in rows if not r.get("labeled") and not r.get("skipped")
        ),
        "skipped_or_template": sum(1 for r in rows if r.get("skipped")),
        "errors": sum(1 for r in rows if r.get("error") and not r.get("skipped")),
        "methods": {},
    }
    for method in ("dense", "bm25", "hybrid_rrf"):
        top1_hits = 0
        top3_hits = 0
        for row in labeled:
            method_block = (row.get("methods") or {}).get(method) or {}
            if (method_block.get("top1_judgment") or {}).get("hit") is True:
                top1_hits += 1
            if (method_block.get("top3_judgment") or {}).get("hit") is True:
                top3_hits += 1
        out["methods"][method] = {
            "verified_top1_hits": top1_hits,
            "verified_top3_hits": top3_hits,
            "verified_top1_hit_rate": (top1_hits / len(labeled)) if labeled else None,
            "verified_top3_hit_rate": (top3_hits / len(labeled)) if labeled else None,
        }
    return out


def focus_case_report(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {r.get("id"): r for r in rows}
    report: list[dict[str, Any]] = []
    for case_id in FOCUS_CASE_IDS:
        row = by_id.get(case_id)
        if not row:
            report.append({"id": case_id, "missing": True})
            continue
        entry: dict[str, Any] = {
            "id": case_id,
            "filename_filter": row.get("filename_filter"),
            "query": row.get("query"),
            "methods": {},
        }
        for method in ("dense", "bm25", "hybrid_rrf"):
            block = (row.get("methods") or {}).get(method) or {}
            entry["methods"][method] = {
                "top1_hit": (block.get("top1_judgment") or {}).get("hit"),
                "top1_rank": (block.get("top1_judgment") or {}).get("hit_rank"),
                "top3_hit": (block.get("top3_judgment") or {}).get("hit"),
                "top3_rank": (block.get("top3_judgment") or {}).get("hit_rank"),
            }
        report.append(entry)
    return report


def write_outputs(
    output_dir: Path,
    payload: dict[str, Any],
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = output_dir / f"rag_hybrid_rrf_eval_{stamp}.json"
    csv_path = output_dir / f"rag_hybrid_rrf_eval_{stamp}.csv"

    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    fieldnames = [
        "id",
        "category",
        "query",
        "labeled",
        "filename_filter",
        "expected_source",
        "expected_page",
        "dense_top1_hit",
        "dense_top1_rank",
        "dense_top3_hit",
        "dense_top3_rank",
        "bm25_top1_hit",
        "bm25_top1_rank",
        "bm25_top3_hit",
        "bm25_top3_rank",
        "hybrid_top1_hit",
        "hybrid_top1_rank",
        "hybrid_top3_hit",
        "hybrid_top3_rank",
        "error",
        "notes",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in payload["cases"]:
            methods = row.get("methods") or {}

            def g(method: str, field: str, key: str) -> Any:
                return ((methods.get(method) or {}).get(field) or {}).get(key)

            writer.writerow(
                {
                    "id": row.get("id"),
                    "category": row.get("category"),
                    "query": row.get("query"),
                    "labeled": row.get("labeled"),
                    "filename_filter": row.get("filename_filter"),
                    "expected_source": row.get("expected_source"),
                    "expected_page": row.get("expected_page"),
                    "dense_top1_hit": g("dense", "top1_judgment", "hit"),
                    "dense_top1_rank": g("dense", "top1_judgment", "hit_rank"),
                    "dense_top3_hit": g("dense", "top3_judgment", "hit"),
                    "dense_top3_rank": g("dense", "top3_judgment", "hit_rank"),
                    "bm25_top1_hit": g("bm25", "top1_judgment", "hit"),
                    "bm25_top1_rank": g("bm25", "top1_judgment", "hit_rank"),
                    "bm25_top3_hit": g("bm25", "top3_judgment", "hit"),
                    "bm25_top3_rank": g("bm25", "top3_judgment", "hit_rank"),
                    "hybrid_top1_hit": g("hybrid_rrf", "top1_judgment", "hit"),
                    "hybrid_top1_rank": g("hybrid_rrf", "top1_judgment", "hit_rank"),
                    "hybrid_top3_hit": g("hybrid_rrf", "top3_judgment", "hit"),
                    "hybrid_top3_rank": g("hybrid_rrf", "top3_judgment", "hit_rank"),
                    "error": row.get("error"),
                    "notes": row.get("notes"),
                }
            )
    return json_path, csv_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="混合检索实验评测（Dense / BM25 / Hybrid-RRF，不改生产检索）",
    )
    parser.add_argument("--user-id", required=True, help="与入库 JWT 用户 ID 一致")
    parser.add_argument(
        "--cases",
        default=str(DEFAULT_CASES),
        help="评测用例 JSON（默认 eval_cases_v2.json）",
    )
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--candidate-k", type=int, default=DEFAULT_CANDIDATE_K)
    parser.add_argument("--rrf-k", type=int, default=DEFAULT_RRF_K)
    parser.add_argument(
        "--rrf-tie-break",
        default=DEFAULT_RRF_TIE_BREAK,
        choices=[RRF_TIE_BREAK_DENSE_FIRST, RRF_TIE_BREAK_BM25],
        help=(
            "RRF 同分打破策略：dense_first=保持 v1 行为；"
            "bm25_tiebreak=同分优先更小 bm25_rank"
        ),
    )
    parser.add_argument(
        "--filename",
        default=None,
        help="可选全局 filename；案例级 filename 字段可覆盖",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="输出目录（写入 rag_hybrid_rrf_eval_*.json/csv）",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not 1 <= args.top_k <= 10:
        die("top_k 必须在 1..10")
    if args.candidate_k < 1:
        die("candidate_k 必须 >= 1")
    if args.rrf_k < 0:
        die("rrf_k 必须 >= 0")

    cases_path = Path(args.cases)
    meta, cases = load_cases(cases_path)
    store = VectorStore()

    print(f"[INFO] cases_file={cases_path}")
    print(
        f"[INFO] evaluating {len(cases)} cases "
        f"top_k={args.top_k} candidate_k={args.candidate_k} rrf_k={args.rrf_k} "
        f"rrf_tie_break={args.rrf_tie_break}"
    )
    print("[INFO] Chroma access: read-only get/query via VectorStore")

    corpus_cache: dict[str | None, list] = {}
    rows: list[dict[str, Any]] = []
    for case in cases:
        if not isinstance(case, dict):
            continue
        print(f"  - {case.get('id')}: retrieving dense/bm25/hybrid...")
        row = evaluate_case_three_ways(
            case,
            user_id=args.user_id,
            top_k=args.top_k,
            filename_filter=args.filename,
            candidate_k=args.candidate_k,
            rrf_k=args.rrf_k,
            rrf_tie_break=args.rrf_tie_break,
            store=store,
            corpus_cache=corpus_cache,
        )
        rows.append(row)
        if row.get("skipped"):
            print(f"    skipped: {row.get('error')}")
        elif row.get("error"):
            print(f"    error: {row.get('error')}")
        else:
            methods = row.get("methods") or {}
            parts = []
            for name in ("dense", "bm25", "hybrid_rrf"):
                t1 = ((methods.get(name) or {}).get("top1_judgment") or {}).get("hit")
                parts.append(f"{name}_top1={t1}")
            print(
                f"    labeled={row.get('labeled')} "
                f"filename_filter={row.get('filename_filter')} "
                + " ".join(parts)
            )

    method_summary = summarize_by_method(rows)
    focus = focus_case_report(rows)
    # hybrid 主 summary（与现有 summarize 字段对齐，便于对照）
    hybrid_rows = []
    for row in rows:
        if row.get("skipped") or row.get("error"):
            hybrid_rows.append(row)
            continue
        hybrid_rows.append(
            {
                **row,
                "top1_judgment": ((row.get("methods") or {}).get("hybrid_rrf") or {}).get(
                    "top1_judgment"
                ),
                "top3_judgment": ((row.get("methods") or {}).get("hybrid_rrf") or {}).get(
                    "top3_judgment"
                ),
            }
        )

    payload = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "experiment": "hybrid_rrf_v1",
        "cases_file": str(cases_path),
        "meta_from_cases_file": meta,
        "config": {
            "user_id": str(args.user_id),
            "filename_filter": args.filename,
            "top_k": args.top_k,
            "candidate_k": args.candidate_k,
            "rrf_k": args.rrf_k,
            "rrf_tie_break": args.rrf_tie_break,
            "tokenizer": "cjk_char_bigram_plus_latin_word",
            "chroma_readonly": True,
            "calls_chat_llm": False,
            "modifies_chroma": False,
        },
        "summary": method_summary,
        "hybrid_summary_compatible": summarize(hybrid_rows),
        "focus_cases": focus,
        "cases": rows,
    }

    json_path, csv_path = write_outputs(Path(args.output_dir), payload)
    print("\n[DONE] method summary:")
    print(json.dumps(method_summary, ensure_ascii=False, indent=2))
    print("\n[DONE] focus cases:")
    print(json.dumps(focus, ensure_ascii=False, indent=2))
    print(f"[DONE] json: {json_path}")
    print(f"[DONE] csv : {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
