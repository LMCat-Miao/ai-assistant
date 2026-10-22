"""阶段 C：全文读取与 Map-Reduce 总结的隔离自动化测试。

使用临时 Chroma 目录，不读写正式知识库；模型调用全部 mock。
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import traceback
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.rag.vector_store import VectorStore
from app.services.rag_document_service import (
    DocumentNotFoundError,
    DocumentVersionConflictError,
    get_document_chunks,
    list_user_documents,
    parse_chunk_index_from_id,
)
from app.services.rag_summarize_service import (
    DocumentTooLargeError,
    SummarizeModelError,
    split_chunks_into_batches,
    summarize_document,
)


EMBED_DIM = 8


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_case(name: str, fn) -> tuple[str, bool, str]:
    try:
        fn()
        return name, True, "ok"
    except Exception as exc:
        return name, False, f"{exc}\n{traceback.format_exc()}"


def seed_chunks(
    store: VectorStore,
    *,
    user_id: str,
    source: str,
    file_hash: str,
    texts: list[str],
    pages: list[int] | None = None,
    with_chunk_index: bool = True,
    with_file_hash_meta: bool = True,
    id_prefix: str | None = None,
) -> list[str]:
    """写入测试 Chunk；可模拟缺少 chunk_index / file_hash 的历史数据。"""

    user_hash = "a" * 12
    prefix = id_prefix or f"pdf_{user_hash}_{file_hash}"
    ids: list[str] = []
    documents: list[str] = []
    embeddings: list[list[float]] = []
    metadatas: list[dict[str, Any]] = []

    for index, text in enumerate(texts):
        record_id = f"{prefix}_chunk_{index:04d}"
        ids.append(record_id)
        documents.append(text)
        embeddings.append([((index + 1) * 0.01)] * EMBED_DIM)
        meta: dict[str, Any] = {
            "user_id": str(user_id),
            "source": source,
            "page": (pages[index] if pages else index + 1),
            "file_type": "pdf",
        }
        if with_file_hash_meta:
            meta["file_hash"] = file_hash
        if with_chunk_index:
            meta["chunk_index"] = index
        metadatas.append(meta)

    store.add_chunks(
        ids=ids,
        documents=documents,
        embeddings=embeddings,
        metadatas=metadatas,
    )
    return ids


def make_store(temp_root: Path, name: str) -> VectorStore:
    return VectorStore(
        persist_directory=temp_root / "chroma",
        collection_name=name,
    )


def test_full_read_and_order_from_metadata() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="sum_order_"))
    try:
        store = make_store(temp_root, "test_order_meta")
        # 故意乱序写入，验证读取后按 chunk_index 恢复文档顺序。
        store.add_chunks(
            ids=[
                "pdf_aaaaaaaaaaaa_2222222222222222_chunk_0002",
                "pdf_aaaaaaaaaaaa_2222222222222222_chunk_0000",
                "pdf_aaaaaaaaaaaa_2222222222222222_chunk_0001",
            ],
            documents=["third", "first", "second"],
            embeddings=[[0.3] * EMBED_DIM, [0.1] * EMBED_DIM, [0.2] * EMBED_DIM],
            metadatas=[
                {
                    "user_id": "1",
                    "source": "b.pdf",
                    "page": 3,
                    "file_hash": "2222222222222222",
                    "chunk_index": 2,
                },
                {
                    "user_id": "1",
                    "source": "b.pdf",
                    "page": 1,
                    "file_hash": "2222222222222222",
                    "chunk_index": 0,
                },
                {
                    "user_id": "1",
                    "source": "b.pdf",
                    "page": 2,
                    "file_hash": "2222222222222222",
                    "chunk_index": 1,
                },
            ],
        )
        doc = get_document_chunks("1", "b.pdf", store=store)
        contents = [c["content"] for c in doc["chunks"]]
        assert_true(contents == ["first", "second", "third"], f"顺序错误: {contents}")
        assert_true(doc["chunk_count"] == 3, "chunk_count 应为 3")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_order_fallback_from_id_suffix() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="sum_id_order_"))
    try:
        store = make_store(temp_root, "test_id_order")
        seed_chunks(
            store,
            user_id="1",
            source="legacy.pdf",
            file_hash="3333333333333333",
            texts=["zero", "one", "two"],
            with_chunk_index=False,
            with_file_hash_meta=True,
        )
        # 打乱 get 返回不影响：我们按解析后的 index 排
        doc = get_document_chunks("1", "legacy.pdf", store=store)
        assert_true(
            [c["content"] for c in doc["chunks"]] == ["zero", "one", "two"],
            "应能从 ID 后缀恢复顺序",
        )
        assert_true(
            parse_chunk_index_from_id(doc["chunks"][1]["id"]) == 1,
            "ID 解析失败",
        )
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_user_isolation() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="sum_iso_"))
    try:
        store = make_store(temp_root, "test_iso")
        seed_chunks(
            store,
            user_id="10",
            source="same.pdf",
            file_hash="aaaaaaaaaaaaaaaa",
            texts=["USER10_SECRET"],
        )
        seed_chunks(
            store,
            user_id="20",
            source="same.pdf",
            file_hash="bbbbbbbbbbbbbbbb",
            texts=["USER20_SECRET"],
            id_prefix="pdf_bbbbbbbbbbbb_bbbbbbbbbbbbbbbb",
        )
        doc10 = get_document_chunks("10", "same.pdf", store=store)
        doc20 = get_document_chunks("20", "same.pdf", store=store)
        text10 = " ".join(c["content"] for c in doc10["chunks"])
        text20 = " ".join(c["content"] for c in doc20["chunks"])
        assert_true("USER10_SECRET" in text10 and "USER20" not in text10, "用户10串数据")
        assert_true("USER20_SECRET" in text20 and "USER10" not in text20, "用户20串数据")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_version_conflict_multiple_hashes() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="sum_conflict_"))
    try:
        store = make_store(temp_root, "test_conflict")
        seed_chunks(
            store,
            user_id="1",
            source="resume.pdf",
            file_hash="aaaaaaaaaaaaaaaa",
            texts=["old"],
        )
        seed_chunks(
            store,
            user_id="1",
            source="resume.pdf",
            file_hash="bbbbbbbbbbbbbbbb",
            texts=["new"],
            id_prefix="pdf_aaaaaaaaaaaa_bbbbbbbbbbbbbbbb",
        )
        raised = False
        try:
            get_document_chunks("1", "resume.pdf", store=store)
        except DocumentVersionConflictError:
            raised = True
        assert_true(raised, "多 file_hash 应报版本冲突")

        docs = list_user_documents("1", store=store)
        item = next(d for d in docs if d["filename"] == "resume.pdf")
        assert_true(item["version_conflict"] is True, "列表应标记 version_conflict")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_version_conflict_mixed_legacy() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="sum_mixed_"))
    try:
        store = make_store(temp_root, "test_mixed")
        # 有 file_hash 的新记录
        seed_chunks(
            store,
            user_id="1",
            source="mix.pdf",
            file_hash="cccccccccccccccc",
            texts=["new-meta"],
        )
        # 无 metadata.file_hash，且 ID 也无法解析的旧记录
        store.add_chunks(
            ids=["weird_legacy_chunk"],
            documents=["legacy-no-hash"],
            embeddings=[[0.9] * EMBED_DIM],
            metadatas=[
                {
                    "user_id": "1",
                    "source": "mix.pdf",
                    "page": 1,
                    "file_type": "pdf",
                }
            ],
        )
        raised = False
        try:
            get_document_chunks("1", "mix.pdf", store=store)
        except DocumentVersionConflictError:
            raised = True
        assert_true(raised, "新旧混杂应报版本冲突")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_document_not_found() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="sum_missing_"))
    try:
        store = make_store(temp_root, "test_missing")
        seed_chunks(
            store,
            user_id="1",
            source="exists.pdf",
            file_hash="dddddddddddddddd",
            texts=["ok"],
        )
        raised = False
        try:
            get_document_chunks("1", "missing.pdf", store=store)
        except DocumentNotFoundError:
            raised = True
        assert_true(raised, "不存在的文档应 404 语义异常")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_short_document_oneshot_summary() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="sum_short_"))
    try:
        store = make_store(temp_root, "test_short")
        seed_chunks(
            store,
            user_id="1",
            source="short.pdf",
            file_hash="eeeeeeeeeeeeeeee",
            texts=["短文档内容 ALPHA"],
        )

        calls: list[Any] = []

        def fake_chat(messages, timeout=None):
            calls.append({"messages": messages, "timeout": timeout})
            return "短文总结结果"

        result = summarize_document(
            user_id="1",
            filename="short.pdf",
            store=store,
            chat_fn=fake_chat,
            max_batch_chars=6000,
        )
        assert_true(result["mode"] == "oneshot", f"应为 oneshot，实际={result['mode']}")
        assert_true(result["batch_count"] == 1, "短文应只有 1 批")
        assert_true(result["summary"] == "短文总结结果", "终稿内容不对")
        assert_true(len(calls) == 1, "短文应只调用模型 1 次")
        assert_true(calls[0]["timeout"] == 60, "应传入默认超时")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_long_document_map_reduce() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="sum_long_"))
    try:
        store = make_store(temp_root, "test_long")
        texts = [f"段落{i}：" + ("字" * 80) for i in range(6)]
        seed_chunks(
            store,
            user_id="1",
            source="long.pdf",
            file_hash="ffffffffffffffff",
            texts=texts,
        )

        calls: list[str] = []

        def fake_chat(messages, timeout=None):
            user = messages[-1]["content"]
            if "局部总结" in user or "合并" in user:
                calls.append("reduce")
                return "合并后的终稿"
            calls.append("map")
            return f"局部-{len(calls)}"

        result = summarize_document(
            user_id="1",
            filename="long.pdf",
            store=store,
            chat_fn=fake_chat,
            max_batch_chars=200,
        )
        assert_true(result["mode"] == "map_reduce", f"应为 map_reduce，实际={result['mode']}")
        assert_true(result["batch_count"] >= 2, "长文应至少 2 批")
        assert_true(result["partial_count"] == result["batch_count"], "局部总结数应等于批次数")
        assert_true(calls.count("map") == result["batch_count"], "Map 次数不对")
        assert_true(calls.count("reduce") == 1, "应有 1 次 Reduce")
        assert_true(result["summary"] == "合并后的终稿", "终稿不对")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_model_failure_does_not_return_fake_complete() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="sum_fail_"))
    try:
        store = make_store(temp_root, "test_fail")
        texts = [f"块{i}：" + ("内容" * 40) for i in range(4)]
        seed_chunks(
            store,
            user_id="1",
            source="fail.pdf",
            file_hash="1212121212121212",
            texts=texts,
        )

        def flaky_chat(messages, timeout=None):
            user = messages[-1]["content"]
            if "第 2/" in user:
                raise TimeoutError("simulated timeout")
            if "局部总结" in user or "合并" in user:
                return "不该出现的终稿"
            return "局部成功"

        raised = False
        try:
            summarize_document(
                user_id="1",
                filename="fail.pdf",
                store=store,
                chat_fn=flaky_chat,
                max_batch_chars=120,
            )
        except SummarizeModelError as exc:
            raised = True
            assert_true("未生成完整终稿" in str(exc), f"错误应说明未完成: {exc}")

        assert_true(raised, "批次失败应抛 SummarizeModelError")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_too_many_batches() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="sum_toobig_"))
    try:
        store = make_store(temp_root, "test_toobig")
        texts = [f"X{i}:" + ("y" * 50) for i in range(10)]
        seed_chunks(
            store,
            user_id="1",
            source="huge.pdf",
            file_hash="3434343434343434",
            texts=texts,
        )
        raised = False
        try:
            summarize_document(
                user_id="1",
                filename="huge.pdf",
                store=store,
                chat_fn=lambda messages, timeout=None: "x",
                max_batch_chars=60,
                max_batches=2,
            )
        except DocumentTooLargeError:
            raised = True
        assert_true(raised, "超过批次数上限应报 DocumentTooLargeError")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_list_documents_and_batch_split_helper() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="sum_list_"))
    try:
        store = make_store(temp_root, "test_list")
        seed_chunks(
            store,
            user_id="1",
            source="a.pdf",
            file_hash="5656565656565656",
            texts=["a1", "a2"],
        )
        seed_chunks(
            store,
            user_id="1",
            source="b.pdf",
            file_hash="7878787878787878",
            texts=["b1"],
            id_prefix="pdf_aaaaaaaaaaaa_7878787878787878",
        )
        # 其他用户不应出现
        seed_chunks(
            store,
            user_id="9",
            source="a.pdf",
            file_hash="9090909090909090",
            texts=["other"],
            id_prefix="pdf_999999999999_9090909090909090",
        )
        docs = list_user_documents("1", store=store)
        names = {d["filename"] for d in docs}
        assert_true(names == {"a.pdf", "b.pdf"}, f"列表错误: {names}")

        batches = split_chunks_into_batches(
            [
                {"chunk_index": 0, "page": 1, "content": "aa"},
                {"chunk_index": 1, "page": 1, "content": "bb"},
                {"chunk_index": 2, "page": 2, "content": "c" * 50},
            ],
            max_batch_chars=40,
        )
        assert_true(len(batches) >= 2, "分批辅助函数应能拆批")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def main() -> int:
    cases = [
        ("full_read_and_order_from_metadata", test_full_read_and_order_from_metadata),
        ("order_fallback_from_id_suffix", test_order_fallback_from_id_suffix),
        ("user_isolation", test_user_isolation),
        ("version_conflict_multiple_hashes", test_version_conflict_multiple_hashes),
        ("version_conflict_mixed_legacy", test_version_conflict_mixed_legacy),
        ("document_not_found", test_document_not_found),
        ("short_document_oneshot_summary", test_short_document_oneshot_summary),
        ("long_document_map_reduce", test_long_document_map_reduce),
        ("model_failure_does_not_return_fake_complete", test_model_failure_does_not_return_fake_complete),
        ("too_many_batches", test_too_many_batches),
        ("list_documents_and_batch_split_helper", test_list_documents_and_batch_split_helper),
    ]

    print("=== document summarize / full-read tests ===")
    failed = 0
    for name, fn in cases:
        case_name, ok, detail = run_case(name, fn)
        print(f"[{'PASS' if ok else 'FAIL'}] {case_name}")
        if not ok:
            failed += 1
            print(detail)

    print(f"\nResult: {len(cases) - failed}/{len(cases)} passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
