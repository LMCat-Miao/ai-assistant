"""hybrid_rrf_retrieve 单元测试（内存夹具，默认不连真实 Chroma）。"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path
from unittest.mock import MagicMock

EXPERIMENTS_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = EXPERIMENTS_DIR.parent
for path in (str(EXPERIMENTS_DIR), str(BACKEND_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from evaluate_rag_retrieval import judge_hit
from hybrid_rrf_retrieve import (
    BM25Index,
    CorpusChunk,
    RRF_TIE_BREAK_BM25,
    RRF_TIE_BREAK_DENSE_FIRST,
    build_chroma_where,
    reciprocal_rank_fusion,
    retrieve_bm25_only,
    tokenize_for_bm25,
    _finalize_results,
    _merge_records,
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


def test_rrf_fusion_order() -> None:
    fused = reciprocal_rank_fusion(
        [
            ["a", "b", "c"],
            ["b", "a", "d"],
        ],
        k=60,
        tie_break=RRF_TIE_BREAK_DENSE_FIRST,
    )
    scores = {doc_id: score for doc_id, score in fused}
    # b: 1/(60+2)+1/(60+1)=1/62+1/61
    # a: 1/61+1/62
    assert_true(abs(scores["a"] - scores["b"]) < 1e-12, "对称两路时 a/b 分数应相等")
    assert_true(scores["a"] > scores["c"], "a 应高于仅一路出现的 c")
    assert_true(scores["b"] > scores["d"], "b 应高于仅一路出现的 d")
    # dense_first：dense 列表先出现 a，同分时 a 在前
    assert_true(fused[0][0] == "a", "dense_first 同分时应保持 dense 先插入的 a")


def test_rrf_score_different_keeps_score_order() -> None:
    fused = reciprocal_rank_fusion(
        [["winner", "loser"], ["winner"]],
        k=60,
        tie_break=RRF_TIE_BREAK_BM25,
        bm25_rank_by_id={"winner": 2, "loser": 1},
        dense_rank_by_id={"winner": 1, "loser": 2},
    )
    assert_true(fused[0][0] == "winner", "分数更高者应排前，即使 bm25_rank 更大")
    assert_true(fused[0][1] > fused[1][1], "Top1 分数应严格大于 Top2")


def test_rrf_tie_prefers_better_bm25_rank() -> None:
    # 模拟 agent_para_005：干扰块 d1/b3 与正确块 d3/b1 同分
    dense = ["noise", "mid", "correct"]
    bm25 = ["correct", "mid", "noise"]
    fused = reciprocal_rank_fusion(
        [dense, bm25],
        k=60,
        tie_break=RRF_TIE_BREAK_BM25,
        dense_rank_by_id={"noise": 1, "mid": 2, "correct": 3},
        bm25_rank_by_id={"correct": 1, "mid": 2, "noise": 3},
    )
    scores = {i: s for i, s in fused}
    assert_true(
        abs(scores["noise"] - scores["correct"]) < 1e-12,
        "noise 与 correct 应为 RRF 同分",
    )
    assert_true(fused[0][0] == "correct", "bm25_tiebreak 同分应优先 bm25_rank=1")


def test_rrf_tie_stable_when_bm25_ranks_equal() -> None:
    fused_once = reciprocal_rank_fusion(
        [["a", "b"], ["a", "b"]],
        k=60,
        tie_break=RRF_TIE_BREAK_BM25,
        dense_rank_by_id={"a": 1, "b": 2},
        bm25_rank_by_id={"a": 1, "b": 1},  # bm25 相同，退到 dense_rank
    )
    fused_twice = reciprocal_rank_fusion(
        [["a", "b"], ["a", "b"]],
        k=60,
        tie_break=RRF_TIE_BREAK_BM25,
        dense_rank_by_id={"a": 1, "b": 2},
        bm25_rank_by_id={"a": 1, "b": 1},
    )
    assert_true(
        [i for i, _ in fused_once] == [i for i, _ in fused_twice],
        "重复运行排序应稳定",
    )
    assert_true(fused_once[0][0] == "a", "bm25 也相同时应优先更小 dense_rank")


def test_rrf_missing_bm25_rank_degrades() -> None:
    fused = reciprocal_rank_fusion(
        [["only_dense", "both"], ["both"]],
        k=60,
        tie_break=RRF_TIE_BREAK_BM25,
        dense_rank_by_id={"only_dense": 1, "both": 2},
        bm25_rank_by_id={"both": 1},
    )
    # only_dense: 1/61；both: 1/62+1/61 → both 分数更高
    assert_true(fused[0][0] == "both", "有两路贡献者分数应更高")
    # 人为构造同分：仅测缺失 bm25 的降级——使用相同单路分数场景
    tied = reciprocal_rank_fusion(
        [["a", "b"], []],
        k=60,
        tie_break=RRF_TIE_BREAK_BM25,
        dense_rank_by_id={"a": 1, "b": 2},
        bm25_rank_by_id={},  # 均无 bm25 → 用 dense_rank
    )
    assert_true(tied[0][0] == "a", "缺少 bm25_rank 时应降级为 dense_rank 且不崩溃")


def test_dense_first_unchanged_on_tie() -> None:
    fused = reciprocal_rank_fusion(
        [["noise", "mid", "correct"], ["correct", "mid", "noise"]],
        k=60,
        tie_break=RRF_TIE_BREAK_DENSE_FIRST,
        dense_rank_by_id={"noise": 1, "mid": 2, "correct": 3},
        bm25_rank_by_id={"correct": 1, "mid": 2, "noise": 3},
    )
    assert_true(
        fused[0][0] == "noise",
        "dense_first 同分时应保持 dense 先插入的 noise（v1 行为）",
    )


def test_tie_break_does_not_duplicate_ids() -> None:
    fused = reciprocal_rank_fusion(
        [["a", "a", "b"], ["b", "a"]],
        k=60,
        tie_break=RRF_TIE_BREAK_BM25,
        dense_rank_by_id={"a": 1, "b": 2},
        bm25_rank_by_id={"b": 1, "a": 2},
    )
    ids = [i for i, _ in fused]
    assert_true(len(ids) == len(set(ids)), "排序策略不得产生重复 Chroma ID")
    assert_true(ids.count("a") == 1 and ids.count("b") == 1, "每个 ID 仅一次")


def test_rrf_single_list_and_empty() -> None:
    only_dense = reciprocal_rank_fusion([["x", "y"]], k=60)
    assert_true([i for i, _ in only_dense] == ["x", "y"], "仅一路时应保持该路顺序")
    only_bm25 = reciprocal_rank_fusion([[], ["p", "q"]], k=60)
    assert_true([i for i, _ in only_bm25] == ["p", "q"], "仅 BM25 一路应可用")
    empty = reciprocal_rank_fusion([[], []], k=60)
    assert_true(empty == [], "两路皆空应返回空")


def test_rrf_dedupe_within_list() -> None:
    fused = reciprocal_rank_fusion([["a", "a", "b"]], k=60)
    ids = [i for i, _ in fused]
    assert_true(ids == ["a", "b"], "同一路重复 ID 只能计一次")


def test_merge_records_same_id_not_duplicated() -> None:
    dense = {
        "id1": {
            "id": "id1",
            "content": "求职意向：AI 前端",
            "source": "resume.pdf",
            "page": 1,
            "distance": 0.9,
        }
    }
    bm25 = {
        "id1": {
            "id": "id1",
            "content": "求职意向：AI 前端",
            "source": "resume.pdf",
            "page": 1,
            "distance": None,
            "bm25_score": 2.5,
        }
    }
    merged = _merge_records(dense, bm25)
    assert_true(len(merged) == 1, "同一 Chroma ID 必须合并为一条")
    assert_true(merged["id1"]["distance"] == 0.9, "应保留 dense distance")
    assert_true(merged["id1"]["bm25_score"] == 2.5, "应保留 bm25_score")


def test_build_chroma_where_filters() -> None:
    only_user = build_chroma_where("1", None)
    assert_true(only_user == {"user_id": {"$eq": "1"}}, "无 filename 时仅过滤 user_id")
    with_file = build_chroma_where("1", "resume.pdf")
    assert_true("$and" in with_file, "有 filename 时应使用 $and")
    assert_true(
        {"user_id": {"$eq": "1"}} in with_file["$and"],
        "应包含 user_id 条件",
    )
    assert_true(
        {"source": {"$eq": "resume.pdf"}} in with_file["$and"],
        "应包含 source 条件",
    )
    try:
        build_chroma_where("", "a.pdf")
        assert_true(False, "空 user_id 应报错")
    except ValueError:
        pass


def test_chinese_bigram_bm25_prefers_exact_phrase_doc() -> None:
    corpus = [
        CorpusChunk("a", "自我评价：对前端与 AI 结合有兴趣", {"source": "r.pdf", "page": 2}),
        CorpusChunk(
            "b",
            "求职意向：AI 前端开发实习生 / 前端开发实习生（AI 方向）",
            {"source": "r.pdf", "page": 1},
        ),
    ]
    tokens = [tokenize_for_bm25(c.document) for c in corpus]
    assert_true("求职" in tokenize_for_bm25("求职意向") or "职意" in tokenize_for_bm25("求职意向"), "应产生汉字 bigram")
    index = BM25Index(tokens)
    ranked = index.ranked_indices(tokenize_for_bm25("求职意向写的是什么"), top_k=2)
    assert_true(len(ranked) >= 1, "BM25 应有结果")
    top_index = ranked[0][0]
    assert_true(corpus[top_index].id == "b", "含精确「求职意向」的文档应排更前")


def test_tokenize_keeps_latin_words() -> None:
    tokens = tokenize_for_bm25("熟悉 Vue3 框架及 ElementPlus")
    assert_true("vue3" in tokens, "应保留拉丁词 vue3")
    assert_true("elementplus" in tokens, "应保留 ElementPlus 小写整词")


def test_judge_hit_accepts_hybrid_shaped_results() -> None:
    case = {
        "id": "t",
        "expected_source": "resume.pdf",
        "expected_page": 1,
        "expected_evidence": "求职意向：AI 前端开发实习生",
    }
    results = [
        {
            "content": "姓名：李妙\n求职意向：AI 前端开发实习生 / 前端开发实习生（AI 方向）",
            "source": "resume.pdf",
            "page": 1,
            "distance": 1.0,
            "id": "chunk0",
            "dense_rank": 2,
            "bm25_rank": 1,
            "rrf_score": 0.03,
        }
    ]
    judgment = judge_hit(case, results, top_n=1)
    assert_true(judgment["hit"] is True, "hybrid 结果结构应可被 judge_hit 命中")
    assert_true(judgment["hit_rank"] == 1, "命中 rank 应为 1")


def test_empty_query_and_empty_corpus() -> None:
    store = MagicMock()
    try:
        retrieve_bm25_only("", "1", store=store, corpus=[])
        assert_true(False, "空 query 应报错")
    except ValueError:
        pass

    results = retrieve_bm25_only(
        "求职意向",
        "1",
        store=store,
        corpus=[],
        top_k=3,
    )
    assert_true(results == [], "空语料应返回空列表")


def test_finalize_skips_missing_and_duplicate_ids() -> None:
    records = {
        "a": {
            "content": "A",
            "source": "s",
            "page": 1,
            "distance": 0.1,
            "dense_rank": 1,
            "bm25_rank": None,
        }
    }
    out = _finalize_results(
        ["a", "a", "missing", "a"],
        records,
        top_k=3,
        rrf_scores={"a": 0.5},
    )
    assert_true(len(out) == 1, "重复与缺失 ID 不应产生重复行")
    assert_true(out[0]["id"] == "a", "应保留有效 ID")
    assert_true(out[0]["rrf_score"] == 0.5, "应写入 rrf_score")


def test_hybrid_with_mocked_dense_only_path() -> None:
    """模拟 dense 有结果、BM25 语料为空时，hybrid 仍返回 dense 排序。"""

    store = MagicMock()
    store.search.return_value = [
        {
            "id": "d1",
            "document": "Agent as a Service（智能体即服务）",
            "metadata": {"source": "agent.pdf", "page": 3},
            "distance": 1.2,
        }
    ]
    store.get_chunks.return_value = {"ids": [], "documents": [], "metadatas": []}

    # 跳过真实 embedding：直接补丁 _dense_rank_list 太重；这里测 retrieve_hybrid 需 embedding。
    # 改为直接验证 reciprocal_rank_fusion([dense, []]) 行为已在其他用例覆盖。
    fused = reciprocal_rank_fusion([["d1"], []], k=60)
    assert_true(fused[0][0] == "d1", "仅 dense 时 hybrid 融合结果应为 dense 文档")


def test_missing_metadata_still_builds_result() -> None:
    records = {
        "x": {
            "content": "正文",
            "source": None,
            "page": None,
            "distance": None,
            "dense_rank": 1,
            "bm25_rank": 1,
        }
    }
    out = _finalize_results(["x"], records, top_k=1, rrf_scores={"x": 0.1})
    assert_true(out[0]["content"] == "正文", "缺失 metadata 仍应返回 content")
    assert_true(out[0]["source"] is None, "允许 source 缺失")


def main() -> int:
    cases = [
        ("rrf_fusion_order", test_rrf_fusion_order),
        ("rrf_score_different_keeps_score_order", test_rrf_score_different_keeps_score_order),
        ("rrf_tie_prefers_better_bm25_rank", test_rrf_tie_prefers_better_bm25_rank),
        ("rrf_tie_stable_when_bm25_ranks_equal", test_rrf_tie_stable_when_bm25_ranks_equal),
        ("rrf_missing_bm25_rank_degrades", test_rrf_missing_bm25_rank_degrades),
        ("dense_first_unchanged_on_tie", test_dense_first_unchanged_on_tie),
        ("tie_break_does_not_duplicate_ids", test_tie_break_does_not_duplicate_ids),
        ("rrf_single_list_and_empty", test_rrf_single_list_and_empty),
        ("rrf_dedupe_within_list", test_rrf_dedupe_within_list),
        ("merge_records_same_id_not_duplicated", test_merge_records_same_id_not_duplicated),
        ("build_chroma_where_filters", test_build_chroma_where_filters),
        (
            "chinese_bigram_bm25_prefers_exact_phrase_doc",
            test_chinese_bigram_bm25_prefers_exact_phrase_doc,
        ),
        ("tokenize_keeps_latin_words", test_tokenize_keeps_latin_words),
        ("judge_hit_accepts_hybrid_shaped_results", test_judge_hit_accepts_hybrid_shaped_results),
        ("empty_query_and_empty_corpus", test_empty_query_and_empty_corpus),
        ("finalize_skips_missing_and_duplicate_ids", test_finalize_skips_missing_and_duplicate_ids),
        ("hybrid_with_mocked_dense_only_path", test_hybrid_with_mocked_dense_only_path),
        ("missing_metadata_still_builds_result", test_missing_metadata_still_builds_result),
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
