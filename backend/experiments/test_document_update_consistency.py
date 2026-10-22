"""同名 PDF 更新时的 Chroma 数据一致性自动化测试。

使用临时 Chroma 目录与独立 collection，不读写真实用户知识库。
Embedding 使用固定假向量，避免加载真实 BGE 模型。
"""

from __future__ import annotations

import hashlib
import shutil
import sys
import tempfile
import traceback
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pymupdf

# 保证可以从 backend 根目录导入 app.*
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.rag.vector_store import VectorStore
from app.services.rag_ingestion_service import (
    build_user_source_where,
    ingest_pdf,
    remove_stale_chunks_for_document,
)


EMBED_DIM = 8


class FakeEmbeddingModel:
    """返回确定性假向量，维度固定，足够支撑隔离测试。"""

    def encode(
        self,
        texts: list[str],
        show_progress_bar: bool = False,
        normalize_embeddings: bool = True,
    ):
        vectors: list[list[float]] = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            values = [((digest[i % len(digest)] / 255.0) - 0.5) for i in range(EMBED_DIM)]
            if normalize_embeddings:
                norm = sum(v * v for v in values) ** 0.5 or 1.0
                values = [v / norm for v in values]
            vectors.append(values)
        return _NumpyLike(vectors)


class _NumpyLike:
    def __init__(self, data: list[list[float]]) -> None:
        self._data = data

    def tolist(self) -> list[list[float]]:
        return self._data


def make_pdf(path: Path, text: str) -> Path:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    doc.save(path)
    doc.close()
    return path


def file_hash_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def list_docs(store: VectorStore, user_id: str, source: str) -> list[dict[str, Any]]:
    result = store.get_chunks(
        where=build_user_source_where(user_id, source),
        include=["metadatas", "documents"],
    )
    rows = []
    for record_id, document, metadata in zip(
        result["ids"],
        result["documents"],
        result["metadatas"],
    ):
        rows.append(
            {
                "id": record_id,
                "document": document,
                "metadata": metadata or {},
            }
        )
    return rows


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_case(name: str, fn) -> tuple[str, bool, str]:
    try:
        fn()
        return name, True, "ok"
    except Exception as exc:
        return name, False, f"{exc}\n{traceback.format_exc()}"


def test_same_user_same_name_content_change() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="rag_update_"))
    try:
        chroma_dir = temp_root / "chroma"
        store = VectorStore(
            persist_directory=chroma_dir,
            collection_name="test_update_consistency",
        )
        pdf_v1 = make_pdf(temp_root / "v1.pdf", "版本一：旧简历内容 ALPHA")
        pdf_v2 = make_pdf(temp_root / "v2.pdf", "版本二：新简历内容 BETA-UNIQUE")

        with patch(
            "app.services.rag_ingestion_service.get_embedding_model",
            return_value=FakeEmbeddingModel(),
        ):
            r1 = ingest_pdf(pdf_v1, user_id="10", original_filename="resume.pdf", store=store)
            r2 = ingest_pdf(pdf_v2, user_id="10", original_filename="resume.pdf", store=store)

        rows = list_docs(store, "10", "resume.pdf")
        texts = " ".join(row["document"] for row in rows)
        hashes = {row["metadata"].get("file_hash") for row in rows}

        assert_true(r1["file_hash"] != r2["file_hash"], "两版内容哈希应不同")
        assert_true(r2["removed_old_chunks"] >= 1, "应删除至少 1 个旧 Chunk")
        assert_true(r2["stale_cleanup_ok"] is True, "清理应成功")
        assert_true(hashes == {r2["file_hash"]}, f"只应保留新哈希，实际={hashes}")
        assert_true("BETA-UNIQUE" in texts, "应能读到新版本文本")
        assert_true("ALPHA" not in texts, "不应再读到旧版本文本")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_identical_file_reupload_no_duplicate() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="rag_same_"))
    try:
        chroma_dir = temp_root / "chroma"
        store = VectorStore(
            persist_directory=chroma_dir,
            collection_name="test_same_file",
        )
        pdf_path = make_pdf(temp_root / "same.pdf", "完全相同的文件内容")

        with patch(
            "app.services.rag_ingestion_service.get_embedding_model",
            return_value=FakeEmbeddingModel(),
        ):
            first = ingest_pdf(pdf_path, user_id="10", original_filename="same.pdf", store=store)
            second = ingest_pdf(pdf_path, user_id="10", original_filename="same.pdf", store=store)

        rows = list_docs(store, "10", "same.pdf")
        assert_true(first["file_hash"] == second["file_hash"], "相同文件哈希应一致")
        assert_true(len(rows) == first["chunks"], f"不应产生重复 Chunk，实际={len(rows)}")
        assert_true(second["removed_old_chunks"] == 0, "相同内容重传不应删除旧版")
        assert_true(
            all(row["metadata"].get("file_hash") == first["file_hash"] for row in rows),
            "所有 Chunk 应属于同一 file_hash",
        )
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_different_users_same_filename_isolated() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="rag_users_"))
    try:
        chroma_dir = temp_root / "chroma"
        store = VectorStore(
            persist_directory=chroma_dir,
            collection_name="test_user_isolation",
        )
        pdf_a = make_pdf(temp_root / "a.pdf", "用户A的专属内容 USER_A_ONLY")
        pdf_b = make_pdf(temp_root / "b.pdf", "用户B的专属内容 USER_B_ONLY")

        with patch(
            "app.services.rag_ingestion_service.get_embedding_model",
            return_value=FakeEmbeddingModel(),
        ):
            ingest_pdf(pdf_a, user_id="101", original_filename="notes.pdf", store=store)
            ingest_pdf(pdf_b, user_id="202", original_filename="notes.pdf", store=store)
            # 用户 A 更新同名文件，不应影响用户 B
            pdf_a2 = make_pdf(temp_root / "a2.pdf", "用户A的新内容 USER_A_NEW")
            ingest_pdf(pdf_a2, user_id="101", original_filename="notes.pdf", store=store)

        rows_a = list_docs(store, "101", "notes.pdf")
        rows_b = list_docs(store, "202", "notes.pdf")
        text_a = " ".join(row["document"] for row in rows_a)
        text_b = " ".join(row["document"] for row in rows_b)

        assert_true(len(rows_b) >= 1, "用户 B 的数据应仍存在")
        assert_true("USER_B_ONLY" in text_b, "用户 B 文本应保留")
        assert_true("USER_A_NEW" in text_a, "用户 A 应看到新文本")
        assert_true("USER_A_ONLY" not in text_a, "用户 A 旧文本应被清理")
        assert_true("USER_B_ONLY" not in text_a, "用户 A 结果中不应混入 B")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_different_files_same_user_unaffected() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="rag_files_"))
    try:
        chroma_dir = temp_root / "chroma"
        store = VectorStore(
            persist_directory=chroma_dir,
            collection_name="test_file_isolation",
        )
        pdf_resume = make_pdf(temp_root / "resume.pdf", "简历内容 RESUME_MARK")
        pdf_guide = make_pdf(temp_root / "guide.pdf", "指南内容 GUIDE_MARK")

        with patch(
            "app.services.rag_ingestion_service.get_embedding_model",
            return_value=FakeEmbeddingModel(),
        ):
            ingest_pdf(pdf_resume, user_id="10", original_filename="resume.pdf", store=store)
            ingest_pdf(pdf_guide, user_id="10", original_filename="guide.pdf", store=store)
            pdf_resume2 = make_pdf(temp_root / "resume2.pdf", "新简历 RESUME_NEW")
            ingest_pdf(
                pdf_resume2,
                user_id="10",
                original_filename="resume.pdf",
                store=store,
            )

        resume_rows = list_docs(store, "10", "resume.pdf")
        guide_rows = list_docs(store, "10", "guide.pdf")
        resume_text = " ".join(row["document"] for row in resume_rows)
        guide_text = " ".join(row["document"] for row in guide_rows)

        assert_true("RESUME_NEW" in resume_text, "简历应为新版本")
        assert_true("RESUME_MARK" not in resume_text, "旧简历应已清理")
        assert_true("GUIDE_MARK" in guide_text, "另一文件不应受影响")
        assert_true(len(guide_rows) >= 1, "guide.pdf 应仍有 Chunk")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_ingest_failure_keeps_old_version() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="rag_fail_"))
    try:
        chroma_dir = temp_root / "chroma"
        store = VectorStore(
            persist_directory=chroma_dir,
            collection_name="test_fail_safe",
        )
        pdf_old = make_pdf(temp_root / "old.pdf", "旧版仍应可用 OLD_KEEP")
        pdf_new = make_pdf(temp_root / "new.pdf", "新版失败 NEW_FAIL")

        with patch(
            "app.services.rag_ingestion_service.get_embedding_model",
            return_value=FakeEmbeddingModel(),
        ):
            first = ingest_pdf(
                pdf_old,
                user_id="10",
                original_filename="doc.pdf",
                store=store,
            )

            original_add = store.add_chunks

            def boom(*args, **kwargs):
                raise RuntimeError("模拟向量写入失败")

            store.add_chunks = boom  # type: ignore[method-assign]
            raised = False
            try:
                ingest_pdf(
                    pdf_new,
                    user_id="10",
                    original_filename="doc.pdf",
                    store=store,
                )
            except RuntimeError:
                raised = True
            finally:
                store.add_chunks = original_add  # type: ignore[method-assign]

        rows = list_docs(store, "10", "doc.pdf")
        text = " ".join(row["document"] for row in rows)
        hashes = {row["metadata"].get("file_hash") for row in rows}

        assert_true(raised, "入库失败应向上抛出异常")
        assert_true(len(rows) == first["chunks"], "失败后 Chunk 数量应不变")
        assert_true(hashes == {first["file_hash"]}, "失败后应仍是旧 file_hash")
        assert_true("OLD_KEEP" in text, "旧版文本应仍可检索到")
        assert_true("NEW_FAIL" not in text, "失败的新版不应入库")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_remove_stale_scoped_only_to_user_and_source() -> None:
    """直接验证清理函数不会越界删除。"""
    temp_root = Path(tempfile.mkdtemp(prefix="rag_scope_"))
    try:
        store = VectorStore(
            persist_directory=temp_root / "chroma",
            collection_name="test_scope_delete",
        )
        store.add_chunks(
            ids=["keep_other_user", "keep_other_file", "stale_target"],
            documents=["u2", "otherfile", "stale"],
            embeddings=[[0.1] * EMBED_DIM, [0.2] * EMBED_DIM, [0.3] * EMBED_DIM],
            metadatas=[
                {"user_id": "2", "source": "a.pdf", "file_hash": "old"},
                {"user_id": "1", "source": "b.pdf", "file_hash": "old"},
                {"user_id": "1", "source": "a.pdf", "file_hash": "old"},
            ],
        )
        # 先写入当前版本，再清理
        store.add_chunks(
            ids=["current"],
            documents=["current"],
            embeddings=[[0.4] * EMBED_DIM],
            metadatas=[
                {"user_id": "1", "source": "a.pdf", "file_hash": "new"},
            ],
        )

        removed = remove_stale_chunks_for_document(
            store=store,
            user_id="1",
            source="a.pdf",
            keep_file_hash="new",
        )
        remaining = store.get_chunks(include=["metadatas"])
        remaining_ids = set(remaining["ids"])

        assert_true(removed == 1, f"只应删除 1 条，实际={removed}")
        assert_true("stale_target" not in remaining_ids, "目标旧 Chunk 应被删")
        assert_true("keep_other_user" in remaining_ids, "其他用户不可删")
        assert_true("keep_other_file" in remaining_ids, "其他文件不可删")
        assert_true("current" in remaining_ids, "当前版本应保留")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def main() -> int:
    cases = [
        ("same_user_same_name_content_change", test_same_user_same_name_content_change),
        ("identical_file_reupload_no_duplicate", test_identical_file_reupload_no_duplicate),
        ("different_users_same_filename_isolated", test_different_users_same_filename_isolated),
        ("different_files_same_user_unaffected", test_different_files_same_user_unaffected),
        ("ingest_failure_keeps_old_version", test_ingest_failure_keeps_old_version),
        ("remove_stale_scoped_only_to_user_and_source", test_remove_stale_scoped_only_to_user_and_source),
    ]

    print("=== document update consistency tests ===")
    failed = 0
    for name, fn in cases:
        case_name, ok, detail = run_case(name, fn)
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {case_name}")
        if not ok:
            failed += 1
            print(detail)

    print(f"\nResult: {len(cases) - failed}/{len(cases)} passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
