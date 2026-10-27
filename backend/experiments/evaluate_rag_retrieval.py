"""
真实语料 RAG 检索评估脚本（只检索，不调用对话大模型）。

- 直接调用 app.services.rag_retrieval_service.retrieve_knowledge
- 使用生产 Chroma（backend/data/chroma_db）与真实 BGE
- 不修改距离阈值，不写入生产业务库
- 结果导出到 experiments/rag_eval/output/

Windows CMD 示例见文件末尾或交付报告。
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.rag.vector_store import CHROMA_DIR, COLLECTION_NAME, VectorStore
from app.services.rag_ingestion_service import MODEL_NAME, get_embedding_model
from app.services.rag_retrieval_service import retrieve_knowledge


DEFAULT_CASES = (
    Path(__file__).resolve().parent / "rag_eval" / "eval_cases.template.json"
)
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "rag_eval" / "output"


def die(message: str, code: int = 1) -> None:
    print(f"[ERROR] {message}", file=sys.stderr)
    raise SystemExit(code)


def load_cases(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not path.is_file():
        die(f"测评用例文件不存在: {path}")

    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or "cases" not in raw:
        die("测评文件格式错误：需要包含 cases 数组的 JSON 对象")

    cases = raw["cases"]
    if not isinstance(cases, list) or not cases:
        die("cases 为空：请先填写测评样本")

    return raw.get("meta") or {}, cases


def preflight_real_stack(user_id: str) -> dict[str, Any]:
    """确认真实 Chroma + 真实 BGE 可用；失败则明确报错，不用假向量。"""

    if not CHROMA_DIR.exists():
        die(
            f"Chroma 持久化目录不存在: {CHROMA_DIR}\n"
            "请先上传 PDF 入库，或确认后端 data/chroma_db 路径。"
        )

    store = VectorStore()
    total = store.collection.count()
    if total <= 0:
        die(
            f"Collection「{COLLECTION_NAME}」为空（count=0）。\n"
            "没有真实入库语料，无法做真实检索评估。"
        )

    # 统计当前用户文档，帮助核对 user_id
    user_rows = store.get_chunks(
        where={"user_id": str(user_id)},
        include=["metadatas"],
    )
    sources: dict[str, int] = {}
    for meta in user_rows["metadatas"]:
        meta = meta or {}
        source = str(meta.get("source") or "").strip()
        if source:
            sources[source] = sources.get(source, 0) + 1

    if not sources:
        die(
            f"用户 user_id={user_id} 在知识库中没有任何 Chunk。\n"
            "请确认评估用户 ID 与上传 PDF 时的 JWT 用户一致。\n"
            f"当前 Collection 总条数={total}，但该用户为 0。"
        )

    print(f"[INFO] embedding model: {MODEL_NAME}")
    print("[INFO] loading real SentenceTransformer (可能较慢)...")
    try:
        model = get_embedding_model()
        probe = model.encode(
            "检索评估连通性探测",
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        dim = len(probe.tolist()) if hasattr(probe, "tolist") else len(probe)
    except Exception as exc:
        die(f"真实 BGE 模型加载/推理失败，中止评估（不使用假向量）。原因: {exc}")

    if dim < 8:
        die(f"Embedding 维度异常: {dim}")

    print(f"[INFO] chroma_dir={CHROMA_DIR}")
    print(f"[INFO] collection={COLLECTION_NAME} total_chunks={total}")
    print(f"[INFO] user_id={user_id} docs={len(sources)} user_chunks={len(user_rows['ids'])}")
    for name, count in sorted(sources.items()):
        print(f"       - {name}: {count} chunks")

    return {
        "chroma_dir": str(CHROMA_DIR),
        "collection": COLLECTION_NAME,
        "total_chunks": total,
        "user_id": str(user_id),
        "user_chunk_count": len(user_rows["ids"]),
        "user_sources": sources,
        "embedding_model": MODEL_NAME,
        "embedding_dim": dim,
    }


def is_labeled(case: dict[str, Any]) -> bool:
    """有预期来源，且至少有页码或证据短语之一，才算可自动验证的标注。"""

    source = case.get("expected_source")
    if not isinstance(source, str) or not source.strip():
        return False
    # 模板占位符不算有效标注
    if source.startswith("【") or "请改成" in source:
        return False

    page = case.get("expected_page")
    evidence = case.get("expected_evidence")
    has_page = page is not None and page != ""
    has_evidence = isinstance(evidence, str) and evidence.strip() and "请改成" not in evidence
    return bool(has_page or has_evidence)


def normalize_evidence_text(text: str) -> str:
    """去掉空白字符，避免 PDF 换行/空格导致证据精确子串误判。"""

    return re.sub(r"\s+", "", text or "")


def judge_hit(
    case: dict[str, Any],
    results: list[dict[str, Any]],
    *,
    top_n: int,
) -> dict[str, Any]:
    """基于标注判断 Top-N 是否命中预期证据；距离本身不当作相关性标签。"""

    slice_results = results[:top_n]
    if not is_labeled(case):
        return {
            "labeled": False,
            "hit": None,
            "hit_rank": None,
            "reason": "缺少有效 expected_source，或缺少 expected_page/expected_evidence；不计入已验证命中",
            "needs_human_review": True,
        }

    expected_source = str(case["expected_source"]).strip()
    expected_page = case.get("expected_page")
    expected_evidence = case.get("expected_evidence")
    if isinstance(expected_evidence, str):
        expected_evidence = expected_evidence.strip()
    else:
        expected_evidence = None

    for rank, item in enumerate(slice_results, start=1):
        source = item.get("source")
        page = item.get("page")
        content = str(item.get("content") or "")

        if source != expected_source:
            continue

        if expected_page is not None and expected_page != "":
            try:
                if int(page) != int(expected_page):
                    continue
            except (TypeError, ValueError):
                continue

        if expected_evidence:
            if normalize_evidence_text(expected_evidence) not in normalize_evidence_text(
                content
            ):
                continue

        return {
            "labeled": True,
            "hit": True,
            "hit_rank": rank,
            "reason": "来源/页码/证据短语与标注一致（自动规则命中）",
            "needs_human_review": True,
        }

    return {
        "labeled": True,
        "hit": False,
        "hit_rank": None,
        "reason": "Top 结果未同时满足标注的来源/页码/证据条件",
        "needs_human_review": True,
    }


def truncate(text: str, limit: int = 240) -> str:
    text = (text or "").replace("\n", " ").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


DIAGNOSIS_RESULT_KEYS = (
    "content_for_diagnosis",
    "raw_evidence_in_content",
    "normalized_evidence_in_content",
)


def resolve_case_filename(
    case: dict[str, Any],
    filename_filter: str | None,
) -> str | None:
    """案例级 filename 覆盖全局 filter；非字符串（含 JSON null）回退全局。"""

    case_filename = case.get("filename", filename_filter)
    if isinstance(case_filename, str):
        return case_filename.strip() or None
    return filename_filter


def format_result_rows(
    results: list[dict[str, Any]],
    *,
    include_full_content: bool = False,
    expected_evidence: Any = None,
) -> list[dict[str, Any]]:
    """将 retrieve_knowledge 结果格式化为导出行。

    完整文本在检索结果的 content 字段中；默认只导出 snippet。
    include_full_content=True 时额外写入 content_for_diagnosis 及证据命中标记，
    供本地诊断，不改变 judge_hit 逻辑。
    """

    evidence: str | None
    if isinstance(expected_evidence, str) and expected_evidence.strip():
        evidence = expected_evidence.strip()
    else:
        evidence = None

    rows: list[dict[str, Any]] = []
    for index, item in enumerate(results, start=1):
        content = str(item.get("content") or "")
        row: dict[str, Any] = {
            "rank": index,
            "source": item.get("source"),
            "page": item.get("page"),
            "distance": item.get("distance"),
            "snippet": truncate(content),
        }
        if include_full_content:
            row["content_for_diagnosis"] = content
            if evidence is not None:
                row["raw_evidence_in_content"] = evidence in content
                row["normalized_evidence_in_content"] = (
                    normalize_evidence_text(evidence)
                    in normalize_evidence_text(content)
                )
        rows.append(row)
    return rows


def strip_diagnosis_fields(case_row: dict[str, Any]) -> dict[str, Any]:
    """从案例结果中移除完整证据字段，用于正式评测报告。"""

    cleaned = dict(case_row)
    results = cleaned.get("results")
    if isinstance(results, list):
        cleaned["results"] = [
            {k: v for k, v in item.items() if k not in DIAGNOSIS_RESULT_KEYS}
            if isinstance(item, dict)
            else item
            for item in results
        ]
    return cleaned


def evaluate_case(
    case: dict[str, Any],
    *,
    user_id: str,
    top_k: int,
    filename_filter: str | None,
    include_full_content: bool = False,
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
        }

    case_filename = resolve_case_filename(case, filename_filter)

    try:
        results = retrieve_knowledge(
            query=query,
            user_id=str(user_id),
            top_k=top_k,
            filename=case_filename,
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
        }

    top1 = judge_hit(case, results, top_n=1)
    top3 = judge_hit(case, results, top_n=min(3, top_k))

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
        "result_count": len(results),
        "top1_judgment": top1,
        "top3_judgment": top3,
        "needs_human_review": True,
        "results": format_result_rows(
            results,
            include_full_content=include_full_content,
            expected_evidence=case.get("expected_evidence"),
        ),
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    labeled = [r for r in rows if r.get("labeled") and not r.get("skipped") and "error" not in r]
    top1_hits = sum(
        1 for r in labeled if (r.get("top1_judgment") or {}).get("hit") is True
    )
    top3_hits = sum(
        1 for r in labeled if (r.get("top3_judgment") or {}).get("hit") is True
    )
    return {
        "total_cases": len(rows),
        "skipped_or_template": sum(1 for r in rows if r.get("skipped")),
        "errors": sum(1 for r in rows if r.get("error") and not r.get("skipped")),
        "labeled_cases": len(labeled),
        "unlabeled_cases": sum(1 for r in rows if not r.get("labeled") and not r.get("skipped")),
        "verified_top1_hits": top1_hits,
        "verified_top3_hits": top3_hits,
        "verified_top1_hit_rate": (top1_hits / len(labeled)) if labeled else None,
        "verified_top3_hit_rate": (top3_hits / len(labeled)) if labeled else None,
        "note": (
            "命中率仅统计带有效 expected_source + (expected_page|expected_evidence) 的样本；"
            "所有样本 needs_human_review=true，距离不作相关性金标准。"
        ),
    }


def write_diagnosis_output(
    output_dir: Path,
    payload: dict[str, Any],
    *,
    stamp: str | None = None,
) -> Path:
    """写入独立诊断 JSON（含 content_for_diagnosis），不覆盖正式评测文件名。"""

    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = stamp or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = output_dir / f"rag_retrieval_rank_diagnosis_{stamp}.json"
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def write_outputs(output_dir: Path, payload: dict[str, Any]) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = output_dir / f"rag_retrieval_eval_{stamp}.json"
    csv_path = output_dir / f"rag_retrieval_eval_{stamp}.csv"

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
        "expected_evidence",
        "result_count",
        "top1_hit",
        "top1_rank",
        "top3_hit",
        "top3_rank",
        "top1_source",
        "top1_page",
        "top1_distance",
        "top1_snippet",
        "needs_human_review",
        "error",
        "notes",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in payload["cases"]:
            results = row.get("results") or []
            top1 = results[0] if results else {}
            top1_j = row.get("top1_judgment") or {}
            top3_j = row.get("top3_judgment") or {}
            writer.writerow(
                {
                    "id": row.get("id"),
                    "category": row.get("category"),
                    "query": row.get("query"),
                    "labeled": row.get("labeled"),
                    "filename_filter": row.get("filename_filter"),
                    "expected_source": row.get("expected_source"),
                    "expected_page": row.get("expected_page"),
                    "expected_evidence": row.get("expected_evidence"),
                    "result_count": row.get("result_count"),
                    "top1_hit": top1_j.get("hit"),
                    "top1_rank": top1_j.get("hit_rank"),
                    "top3_hit": top3_j.get("hit"),
                    "top3_rank": top3_j.get("hit_rank"),
                    "top1_source": top1.get("source"),
                    "top1_page": top1.get("page"),
                    "top1_distance": top1.get("distance"),
                    "top1_snippet": top1.get("snippet"),
                    "needs_human_review": row.get("needs_human_review"),
                    "error": row.get("error"),
                    "notes": row.get("notes"),
                }
            )

    return json_path, csv_path


def parse_diagnose_ids(raw: str | None) -> set[str]:
    if not raw:
        return set()
    return {part.strip() for part in raw.split(",") if part.strip()}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="真实语料 RAG 检索评估（调用 retrieve_knowledge，不调对话模型）",
    )
    parser.add_argument(
        "--user-id",
        required=True,
        help="与入库时 JWT 用户 ID 一致的字符串，例如 1",
    )
    parser.add_argument(
        "--filename",
        default=None,
        help="可选：全局限定只在该 PDF 文件名内检索",
    )
    parser.add_argument(
        "--cases",
        default=str(DEFAULT_CASES),
        help="测评用例 JSON 路径（默认模板文件）",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=3,
        help="检索 top_k，默认 3",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="评估结果输出目录",
    )
    parser.add_argument(
        "--include-full-content",
        action="store_true",
        help="在正式评测 JSON 的 results 中写入 content_for_diagnosis（默认关闭）",
    )
    parser.add_argument(
        "--diagnose-ids",
        default=None,
        help="逗号分隔案例 ID；为这些案例生成含完整 content 的独立诊断 JSON",
    )
    parser.add_argument(
        "--diagnosis-only",
        action="store_true",
        help="只评估 --diagnose-ids 指定案例，并只写诊断 JSON（不写正式 eval JSON/CSV）",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not 1 <= args.top_k <= 10:
        die("top_k 必须在 1..10（与 retrieve_knowledge 一致）")

    diagnose_ids = parse_diagnose_ids(args.diagnose_ids)
    if args.diagnosis_only and not diagnose_ids:
        die("--diagnosis-only 需要同时提供 --diagnose-ids")

    cases_path = Path(args.cases)
    meta, cases = load_cases(cases_path)

    if args.diagnosis_only:
        cases = [c for c in cases if isinstance(c, dict) and c.get("id") in diagnose_ids]
        missing = diagnose_ids - {c.get("id") for c in cases}
        if missing:
            die(f"--diagnose-ids 在用例文件中不存在: {sorted(missing)}")

    stack = preflight_real_stack(args.user_id)

    print(f"[INFO] cases_file={cases_path}")
    print(
        f"[INFO] evaluating {len(cases)} cases with top_k={args.top_k} "
        f"include_full_content={args.include_full_content} "
        f"diagnose_ids={sorted(diagnose_ids) or None} ..."
    )

    rows: list[dict[str, Any]] = []
    for case in cases:
        if not isinstance(case, dict):
            continue
        case_id = str(case.get("id") or "")
        need_full = bool(
            args.include_full_content or (case_id and case_id in diagnose_ids)
        )
        print(f"  - {case.get('id')}: retrieving...")
        row = evaluate_case(
            case,
            user_id=args.user_id,
            top_k=args.top_k,
            filename_filter=args.filename,
            include_full_content=need_full,
        )
        rows.append(row)
        if row.get("skipped"):
            print(f"    skipped: {row.get('error')}")
        elif row.get("error"):
            print(f"    error: {row.get('error')}")
        else:
            t1 = (row.get("top1_judgment") or {}).get("hit")
            t3 = (row.get("top3_judgment") or {}).get("hit")
            print(
                f"    results={row.get('result_count')} "
                f"labeled={row.get('labeled')} top1_hit={t1} top3_hit={t3} "
                f"filename_filter={row.get('filename_filter')}"
            )

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = Path(args.output_dir)

    if diagnose_ids:
        diag_cases = [
            row
            for row in rows
            if row.get("id") in diagnose_ids and not row.get("skipped")
        ]
        diag_payload = {
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "purpose": "local rank/evidence diagnosis with full content_for_diagnosis",
            "warning": (
                "含完整检索文本，仅供本地开发诊断；"
                "重新检索结果不一定等同于历史评测 JSON 中的文本。"
            ),
            "reference_baseline_eval": (
                "experiments/rag_eval/output/rag_retrieval_eval_20261026T091151Z.json"
            ),
            "cases_file": str(cases_path),
            "meta_from_cases_file": meta,
            "config": {
                "user_id": str(args.user_id),
                "filename_filter": args.filename,
                "top_k": args.top_k,
                "diagnose_ids": sorted(diagnose_ids),
                "include_full_content": True,
                "uses_production_retrieve_knowledge": True,
                "calls_chat_llm": False,
                "distance_threshold_applied": False,
            },
            "stack": stack,
            "cases": diag_cases,
        }
        diag_path = write_diagnosis_output(
            output_dir,
            diag_payload,
            stamp=stamp,
        )
        print(f"[DONE] diagnosis json: {diag_path}")

    if args.diagnosis_only:
        print("[DONE] diagnosis-only：未写入正式 eval JSON/CSV")
        return 0

    formal_rows = (
        rows
        if args.include_full_content
        else [strip_diagnosis_fields(row) for row in rows]
    )
    payload = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "cases_file": str(cases_path),
        "meta_from_cases_file": meta,
        "config": {
            "user_id": str(args.user_id),
            "filename_filter": args.filename,
            "top_k": args.top_k,
            "include_full_content": bool(args.include_full_content),
            "uses_production_retrieve_knowledge": True,
            "calls_chat_llm": False,
            "distance_threshold_applied": False,
        },
        "stack": stack,
        "summary": summarize(formal_rows),
        "cases": formal_rows,
    }

    json_path, csv_path = write_outputs(output_dir, payload)
    print("\n[DONE] summary:")
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    print(f"[DONE] json: {json_path}")
    print(f"[DONE] csv : {csv_path}")
    print(
        "\n提醒：若仍使用 template 占位样本，命中率统计无意义。"
        "请复制为 eval_cases.json，按真实 PDF 填写后再跑。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
