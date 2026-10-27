"""evaluate_rag_retrieval.judge_hit 证据匹配规则单元测试（不连 Chroma / Embedding）。"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

EXPERIMENTS_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = EXPERIMENTS_DIR.parent
for path in (str(EXPERIMENTS_DIR), str(BACKEND_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from evaluate_rag_retrieval import (
    format_result_rows,
    judge_hit,
    normalize_evidence_text,
    strip_diagnosis_fields,
)


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_case(name: str, fn) -> tuple[str, bool, str]:
    try:
        fn()
        return name, True, "ok"
    except Exception as exc:
        return name, False, f"{exc}\n{traceback.format_exc()}"


def _labeled_case(**overrides) -> dict:
    case = {
        "id": "unit_case",
        "expected_source": "agent.pdf",
        "expected_page": 2,
        "expected_evidence": "执行者范式（instructor-executor paradigm） 和平等伙伴范式（equal partnership paradigm）",
    }
    case.update(overrides)
    return case


def test_normalize_strips_whitespace() -> None:
    assert_true(
        normalize_evidence_text("a \n\tb  c") == "abc",
        "应删除空格/换行/制表符",
    )
    assert_true(normalize_evidence_text("") == "", "空串应返回空串")
    assert_true(normalize_evidence_text(None) == "", "None 应按空串处理")  # type: ignore[arg-type]


def test_hit_when_content_has_newline_inside_evidence() -> None:
    evidence = "执行者范式（instructor-executor paradigm） 和平等伙伴范式（equal partnership paradigm）"
    content = (
        "归纳出 agent 与人类协作的两种范式：执行者范式（instructor-executor paradigm） "
        "和平等伙伴范式\n（equal partnership paradigm），并给出实践中的具体应用。"
    )
    judgment = judge_hit(
        _labeled_case(expected_evidence=evidence, expected_page=2),
        [{"source": "agent.pdf", "page": 2, "content": content}],
        top_n=1,
    )
    assert_true(judgment["labeled"] is True, "应计为已标注")
    assert_true(judgment["hit"] is True, "证据内含 \\n 时应命中")
    assert_true(judgment["hit_rank"] == 1, "命中 rank 应为 1")


def test_hit_when_content_has_spaces_or_tabs_inside_evidence() -> None:
    evidence = "效用（utility）、社交性（sociability）"
    content = "从效用（utility）、社交\t性（sociability）、价值观评估"
    judgment = judge_hit(
        _labeled_case(
            expected_evidence=evidence,
            expected_page=3,
        ),
        [{"source": "agent.pdf", "page": 3, "content": content}],
        top_n=1,
    )
    assert_true(judgment["hit"] is True, "证据内含制表符时应命中")

    content_spaces = "从效用（utility）、社交  性（sociability）、价值观评估"
    judgment2 = judge_hit(
        _labeled_case(expected_evidence=evidence, expected_page=3),
        [{"source": "agent.pdf", "page": 3, "content": content_spaces}],
        top_n=1,
    )
    assert_true(judgment2["hit"] is True, "证据内含多空格时应命中")


def test_miss_when_evidence_absent() -> None:
    judgment = judge_hit(
        _labeled_case(
            expected_evidence="执行者范式（instructor-executor paradigm） 和平等伙伴范式（equal partnership paradigm）",
            expected_page=2,
        ),
        [
            {
                "source": "agent.pdf",
                "page": 2,
                "content": "本文讨论人机协作，但未给出两种范式的具体名称。",
            }
        ],
        top_n=1,
    )
    assert_true(judgment["labeled"] is True, "应计为已标注")
    assert_true(judgment["hit"] is False, "缺少证据时不应命中")
    assert_true(judgment["hit_rank"] is None, "未命中时 hit_rank 应为 None")


def test_miss_when_source_or_page_mismatch() -> None:
    evidence = "执行者范式（instructor-executor paradigm） 和平等伙伴范式（equal partnership paradigm）"
    content = f"前文。{evidence}。后文。"
    wrong_source = judge_hit(
        _labeled_case(expected_evidence=evidence, expected_page=2),
        [{"source": "other.pdf", "page": 2, "content": content}],
        top_n=1,
    )
    assert_true(wrong_source["hit"] is False, "来源不匹配不应命中")

    wrong_page = judge_hit(
        _labeled_case(expected_evidence=evidence, expected_page=2),
        [{"source": "agent.pdf", "page": 9, "content": content}],
        top_n=1,
    )
    assert_true(wrong_page["hit"] is False, "页码不匹配不应命中")


def test_unlabeled_case_not_verified_hit() -> None:
    judgment = judge_hit(
        {
            "id": "unlabeled",
            "expected_source": None,
            "expected_page": None,
            "expected_evidence": None,
        },
        [{"source": "agent.pdf", "page": 1, "content": "任意内容"}],
        top_n=1,
    )
    assert_true(judgment["labeled"] is False, "未标注应 labeled=False")
    assert_true(judgment["hit"] is None, "未标注不应计入已验证命中")
    assert_true(judgment["hit_rank"] is None, "未标注 hit_rank 应为 None")


def test_default_result_rows_omit_full_content() -> None:
    full = "完整文档正文应仅出现在诊断模式中。" * 20
    rows = format_result_rows(
        [{"source": "agent.pdf", "page": 1, "distance": 0.1, "content": full}],
        include_full_content=False,
        expected_evidence="完整文档正文",
    )
    assert_true(len(rows) == 1, "应有 1 条结果")
    row = rows[0]
    assert_true("snippet" in row, "默认应有 snippet")
    assert_true("content_for_diagnosis" not in row, "默认不得输出完整 content")
    assert_true("raw_evidence_in_content" not in row, "默认不得输出原始证据命中字段")
    assert_true(
        "normalized_evidence_in_content" not in row,
        "默认不得输出规范化证据命中字段",
    )
    assert_true(row["snippet"] != full, "默认 snippet 不得等于完整正文")
    assert_true(len(row["snippet"]) < len(full), "默认 snippet 应短于完整正文")
    dumped = json_dumps_safe(row)
    assert_true(
        '"content_for_diagnosis"' not in dumped,
        "默认序列化不得出现 content_for_diagnosis 字段名",
    )


def test_diagnosis_result_rows_include_full_content() -> None:
    full = "求职意向：AI 前端开发实习生 / 前端开发实习生（AI 方向）"
    rows = format_result_rows(
        [{"source": "resume.pdf", "page": 1, "distance": 0.2, "content": full}],
        include_full_content=True,
        expected_evidence=full,
    )
    row = rows[0]
    assert_true(row.get("content_for_diagnosis") == full, "诊断模式应含完整 content")
    assert_true(row.get("raw_evidence_in_content") is True, "原始证据应命中")
    assert_true(row.get("normalized_evidence_in_content") is True, "规范化证据应命中")


def test_strip_diagnosis_fields_removes_full_content() -> None:
    case_row = {
        "id": "x",
        "filename_filter": "resume.pdf",
        "results": [
            {
                "rank": 1,
                "source": "resume.pdf",
                "page": 1,
                "distance": 0.1,
                "snippet": "短摘要",
                "content_for_diagnosis": "这是完整正文不应出现在正式报告",
                "raw_evidence_in_content": True,
                "normalized_evidence_in_content": True,
            }
        ],
    }
    cleaned = strip_diagnosis_fields(case_row)
    result = cleaned["results"][0]
    assert_true("snippet" in result, "正式报告保留 snippet")
    assert_true("content_for_diagnosis" not in result, "正式报告应剥离完整正文")
    assert_true("raw_evidence_in_content" not in result, "正式报告应剥离证据命中字段")
    assert_true(
        case_row["results"][0].get("content_for_diagnosis"),
        "剥离不得修改原始 case_row 内层引用前的诊断数据意图：原对象仍可含全文",
    )


def json_dumps_safe(obj: dict) -> str:
    import json

    return json.dumps(obj, ensure_ascii=False)


def main() -> int:
    cases = [
        ("normalize_strips_whitespace", test_normalize_strips_whitespace),
        (
            "hit_when_content_has_newline_inside_evidence",
            test_hit_when_content_has_newline_inside_evidence,
        ),
        (
            "hit_when_content_has_spaces_or_tabs_inside_evidence",
            test_hit_when_content_has_spaces_or_tabs_inside_evidence,
        ),
        ("miss_when_evidence_absent", test_miss_when_evidence_absent),
        ("miss_when_source_or_page_mismatch", test_miss_when_source_or_page_mismatch),
        ("unlabeled_case_not_verified_hit", test_unlabeled_case_not_verified_hit),
        (
            "default_result_rows_omit_full_content",
            test_default_result_rows_omit_full_content,
        ),
        (
            "diagnosis_result_rows_include_full_content",
            test_diagnosis_result_rows_include_full_content,
        ),
        (
            "strip_diagnosis_fields_removes_full_content",
            test_strip_diagnosis_fields_removes_full_content,
        ),
    ]
    failed = 0
    for name, fn in cases:
        case_name, ok, detail = run_case(name, fn)
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {case_name}")
        if not ok:
            failed += 1
            print(detail)
    print(f"\n{len(cases) - failed}/{len(cases)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
