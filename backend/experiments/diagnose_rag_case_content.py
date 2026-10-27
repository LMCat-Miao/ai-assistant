"""
只读诊断：对指定评测案例重新 retrieve_knowledge，导出完整 content 并核对 expected_evidence。

- 不修改生产 RAG、不修改既有评测 JSON/CSV
- 重新检索结果 ≠ 历史那次运行的文本；仅用于对照诊断
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.rag_retrieval_service import retrieve_knowledge

CASES_PATH = BACKEND_ROOT / "experiments" / "rag_eval" / "eval_cases.json"
HIST_PATH = (
    BACKEND_ROOT
    / "experiments"
    / "rag_eval"
    / "output"
    / "rag_retrieval_eval_20261026T073728Z.json"
)
OUT_DIR = BACKEND_ROOT / "experiments" / "rag_eval" / "output"
TARGET_IDS = ("agent_has_002", "agent_para_002")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def unicode_codepoints(label: str, text: str) -> list[dict[str, Any]]:
    return [
        {"index": i, "char": ch, "ord": ord(ch), "repr": repr(ch)}
        for i, ch in enumerate(text)
    ]


def find_first_divergence(expected: str, content: str) -> dict[str, Any] | None:
    """若 expected 不是 content 子串，尝试定位 expected 最长前缀在 content 中的落点差异。"""

    if expected in content:
        return None

    # 找 expected 的最长前缀，使该前缀出现在 content 中
    best_prefix = ""
    best_pos = -1
    for end in range(1, len(expected) + 1):
        prefix = expected[:end]
        pos = content.find(prefix)
        if pos >= 0:
            best_prefix = prefix
            best_pos = pos
        else:
            break

    if best_pos < 0:
        # 尝试用 expected 的前若干字符做窗口搜索失败
        probe = expected[: min(12, len(expected))]
        return {
            "type": "no_prefix_found",
            "probe_prefix": probe,
            "probe_prefix_repr": repr(probe),
            "probe_in_content": probe in content,
        }

    next_index = len(best_prefix)
    expected_next = expected[next_index] if next_index < len(expected) else None
    content_next_index = best_pos + next_index
    content_next = (
        content[content_next_index] if content_next_index < len(content) else None
    )
    window_start = max(0, content_next_index - 20)
    window_end = min(len(content), content_next_index + 40)

    return {
        "type": "prefix_divergence",
        "matched_prefix": best_prefix,
        "matched_prefix_repr": repr(best_prefix),
        "matched_prefix_len": len(best_prefix),
        "match_position_in_content": best_pos,
        "expected_next_char": expected_next,
        "expected_next_repr": repr(expected_next) if expected_next is not None else None,
        "expected_next_ord": ord(expected_next) if expected_next is not None else None,
        "content_next_char": content_next,
        "content_next_repr": repr(content_next) if content_next is not None else None,
        "content_next_ord": ord(content_next) if content_next is not None else None,
        "content_window": content[window_start:window_end],
        "content_window_repr": repr(content[window_start:window_end]),
    }


def analyze_case(
    case: dict[str, Any],
    *,
    user_id: str,
    filename: str | None,
    top_k: int,
) -> dict[str, Any]:
    query = case["query"]
    expected_source = case.get("expected_source")
    expected_page = case.get("expected_page")
    expected_evidence = case.get("expected_evidence")

    results = retrieve_knowledge(
        query=query,
        user_id=str(user_id),
        top_k=top_k,
        filename=filename,
    )

    ranked: list[dict[str, Any]] = []
    for index, item in enumerate(results, start=1):
        content = str(item.get("content") or "")
        evidence = (
            expected_evidence.strip()
            if isinstance(expected_evidence, str)
            else None
        )
        contains = (evidence in content) if evidence else None
        entry: dict[str, Any] = {
            "rank": index,
            "source": item.get("source"),
            "page": item.get("page"),
            "distance": item.get("distance"),
            "content": content,
            "content_length": len(content),
            "expected_evidence_exact_in_content": contains,
        }
        if evidence and contains is False:
            entry["divergence"] = find_first_divergence(evidence, content)
            entry["expected_evidence_repr"] = repr(evidence)
            entry["expected_evidence_codepoints_head"] = unicode_codepoints(
                "expected",
                evidence[:80],
            )
        ranked.append(entry)

    top1 = ranked[0] if ranked else None
    any_top3_contains = any(
        r.get("expected_evidence_exact_in_content") is True for r in ranked
    )

    return {
        "case_id": case.get("id"),
        "category": case.get("category"),
        "query": query,
        "expected_source": expected_source,
        "expected_page": expected_page,
        "expected_evidence": expected_evidence,
        "expected_evidence_repr": repr(expected_evidence)
        if expected_evidence is not None
        else None,
        "retrieval_conditions": {
            "user_id": str(user_id),
            "filename": filename,
            "top_k": top_k,
            "api": "retrieve_knowledge",
        },
        "results": ranked,
        "summary": {
            "top1_source_page_match": bool(
                top1
                and top1.get("source") == expected_source
                and top1.get("page") == expected_page
            ),
            "top1_exact_evidence_in_full_content": (
                top1.get("expected_evidence_exact_in_content") if top1 else None
            ),
            "any_top3_exact_evidence_in_full_content": any_top3_contains,
        },
    }


def main() -> int:
    cases_doc = load_json(CASES_PATH)
    hist = load_json(HIST_PATH)
    hist_config = hist.get("config") or {}

    user_id = str(hist_config.get("user_id") or "1")
    filename = hist_config.get("filename_filter")
    if filename is None:
        filename = (cases_doc.get("meta") or {}).get("suggested_filename_filter")
    top_k = int(hist_config.get("top_k") or 3)

    case_map = {c["id"]: c for c in cases_doc.get("cases", []) if "id" in c}
    missing = [cid for cid in TARGET_IDS if cid not in case_map]
    if missing:
        print(f"[ERROR] cases missing: {missing}")
        return 1

    # 历史评测中各案的 filename_filter（若有）
    hist_case_filters = {
        c.get("id"): c.get("filename_filter")
        for c in hist.get("cases", [])
        if c.get("id") in TARGET_IDS
    }

    diagnoses: list[dict[str, Any]] = []
    for case_id in TARGET_IDS:
        case = case_map[case_id]
        case_filename = hist_case_filters.get(case_id, filename)
        print(f"[INFO] retrieving {case_id} ...")
        diagnoses.append(
            analyze_case(
                case,
                user_id=user_id,
                filename=case_filename,
                top_k=top_k,
            )
        )

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = OUT_DIR / f"diagnose_agent_cases_full_content_{stamp}.json"
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    payload = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": "readonly diagnosis of agent_has_002 / agent_para_002 full content vs expected_evidence",
        "warning": (
            "本次为重新检索结果，可能与历史评测运行不完全相同；"
            "不得直接当作 20261026T073728Z 那次运行的完整文本。"
        ),
        "reference_historical_eval": str(HIST_PATH),
        "historical_config_used_as_template": {
            "user_id": user_id,
            "filename_filter": filename,
            "top_k": top_k,
            "historical_created_at_utc": hist.get("created_at_utc"),
        },
        "cases_file": str(CASES_PATH),
        "diagnoses": diagnoses,
    }
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[DONE] wrote {out_path}")

    for d in diagnoses:
        print("\n" + "=" * 60)
        print(d["case_id"])
        print("expected_evidence_repr:", d.get("expected_evidence_repr"))
        s = d["summary"]
        print("top1_source_page_match:", s["top1_source_page_match"])
        print(
            "top1_exact_evidence_in_full_content:",
            s["top1_exact_evidence_in_full_content"],
        )
        print(
            "any_top3_exact_evidence_in_full_content:",
            s["any_top3_exact_evidence_in_full_content"],
        )
        top1 = (d.get("results") or [None])[0]
        if top1 and top1.get("divergence"):
            div = top1["divergence"]
            print("divergence.type:", div.get("type"))
            if div.get("type") == "prefix_divergence":
                print("matched_prefix_repr:", div.get("matched_prefix_repr"))
                print("expected_next_repr:", div.get("expected_next_repr"))
                print("content_next_repr:", div.get("content_next_repr"))
                print("content_window_repr:", div.get("content_window_repr"))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
