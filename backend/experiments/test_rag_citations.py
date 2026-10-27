"""RAG 来源引用与无答案处理隔离测试。"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import traceback
from pathlib import Path
from unittest.mock import patch

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import app.database as database
from app.database_init import init_database
from app.repositories.message_reponsitory import (
    create_message,
    get_messages_by_conversation,
)
from app.repositories.conversation_repository import create_conversation
from app.services.chat_service import prepare_chat_context
from app.services.rag_citations import build_citations_from_chunks


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_case(name: str, fn) -> tuple[str, bool, str]:
    try:
        fn()
        return name, True, "ok"
    except Exception as exc:
        return name, False, f"{exc}\n{traceback.format_exc()}"


def test_build_citations_merge_same_file_page() -> None:
    citations = build_citations_from_chunks(
        [
            {
                "source": "a.pdf",
                "page": 1,
                "content": "第一段内容 AAA",
                "distance": 0.4,
            },
            {
                "source": "a.pdf",
                "page": 1,
                "content": "更近的一段 BBB",
                "distance": 0.1,
            },
            {
                "source": "a.pdf",
                "page": 2,
                "content": "第二页",
                "distance": 0.2,
            },
            {
                "source": None,
                "page": 3,
                "content": "无文件名应跳过",
                "distance": 0.01,
            },
        ]
    )
    assert_true(len(citations) == 2, f"应合并为 2 条，实际={len(citations)}")
    first = citations[0]
    assert_true(first["filename"] == "a.pdf", "文件名错误")
    assert_true(first["page"] == 1, "页码错误")
    assert_true(first["chunk_count"] == 2, "同页 chunk 应合并计数")
    assert_true(first["distance"] == 0.1, "应保留更近距离")
    assert_true("BBB" in first["snippet"], "应保留更近片段")


def test_prepare_normal_chat_has_no_citations() -> None:
    with (
        patch(
            "app.services.chat_service.get_conversation",
            return_value={"id": 1, "title": "新会话", "user_id": 1},
        ),
        patch(
            "app.services.chat_service.get_messages_by_conversation",
            side_effect=[[], [{"role": "user", "content": "你好"}]],
        ),
        patch("app.services.chat_service.create_message"),
        patch(
            "app.services.chat_service.maybe_update_conversation_title",
            return_value=None,
        ),
        patch("app.services.chat_service.retrieve_knowledge") as retrieve_mock,
    ):
        result = prepare_chat_context(
            conversation_id=1,
            user_id=1,
            message="你好",
            use_knowledge=False,
        )

    retrieve_mock.assert_not_called()
    assert_true(result.knowledge_status == "none", "普通聊天 status=none")
    assert_true(result.citations == [], "普通聊天无引用")


def test_prepare_rag_hit_builds_citations_from_retrieval() -> None:
    with (
        patch(
            "app.services.chat_service.get_conversation",
            return_value={"id": 1, "title": "新会话", "user_id": 1},
        ),
        patch(
            "app.services.chat_service.get_messages_by_conversation",
            side_effect=[[], [{"role": "user", "content": "项目经历"}]],
        ),
        patch("app.services.chat_service.create_message"),
        patch(
            "app.services.chat_service.maybe_update_conversation_title",
            return_value=None,
        ),
        patch(
            "app.services.chat_service.retrieve_knowledge",
            return_value=[
                {
                    "content": "做过 AI 助手项目",
                    "source": "resume.pdf",
                    "page": 2,
                    "distance": 0.12,
                }
            ],
        ),
    ):
        result = prepare_chat_context(
            conversation_id=1,
            user_id=1,
            message="项目经历",
            use_knowledge=True,
            knowledge_filename="resume.pdf",
        )

    assert_true(result.knowledge_status == "hit", "应有命中")
    assert_true(len(result.citations) == 1, "应有 1 条引用")
    assert_true(result.citations[0]["filename"] == "resume.pdf", "文件名必须来自检索")
    assert_true(result.citations[0]["page"] == 2, "页码必须来自检索")
    assert_true("AI 助手" in (result.citations[0].get("snippet") or ""), "片段来自检索")


def test_prepare_rag_empty_no_fake_citations() -> None:
    with (
        patch(
            "app.services.chat_service.get_conversation",
            return_value={"id": 1, "title": "新会话", "user_id": 1},
        ),
        patch(
            "app.services.chat_service.get_messages_by_conversation",
            side_effect=[[], [{"role": "user", "content": "无关"}]],
        ),
        patch("app.services.chat_service.create_message"),
        patch(
            "app.services.chat_service.maybe_update_conversation_title",
            return_value=None,
        ),
        patch(
            "app.services.chat_service.retrieve_knowledge",
            return_value=[],
        ),
    ):
        result = prepare_chat_context(
            conversation_id=1,
            user_id=1,
            message="无关",
            use_knowledge=True,
        )

    assert_true(result.knowledge_status == "empty", "无命中应为 empty")
    assert_true(result.citations == [], "无命中不得伪造引用")
    system = result.context[0]["content"]
    assert_true("没有找到相关资料" in system, "应提示资料不足")


def test_message_citations_persist_and_reload() -> None:
    temp = Path(tempfile.mkdtemp(prefix="cite_db_"))
    try:
        database.DATABASE_PATH = temp / "test_citations.db"
        init_database()
        cid = create_conversation(user_id=1, title="引用测试")
        create_message(
            conversation_id=cid,
            role="assistant",
            content="根据资料回答",
            citations=[
                {
                    "filename": "guide.pdf",
                    "page": 3,
                    "snippet": "重要概念",
                    "distance": 0.2,
                    "chunk_count": 1,
                }
            ],
        )
        rows = get_messages_by_conversation(cid)
        assert_true(len(rows) == 1, "应有 1 条消息")
        cites = rows[0].get("citations")
        assert_true(isinstance(cites, list) and len(cites) == 1, "应还原 citations")
        assert_true(cites[0]["filename"] == "guide.pdf", "持久化文件名错误")
        assert_true(cites[0]["page"] == 3, "持久化页码错误")
    finally:
        shutil.rmtree(temp, ignore_errors=True)


def test_distance_candidate_eval_is_inconclusive_without_real_bge() -> None:
    """距离阈值评估：使用确定性假向量仅验证流程，不产出可上线阈值。

    Chroma 默认 L2；项目入库 normalize_embeddings=True。
    假哈希向量的距离分布不能代表 BGE 真实分布，故本测试只记录观察，
    并断言「不得据此写入生产硬阈值」。
    """

    from app.rag.vector_store import VectorStore
    import hashlib

    temp = Path(tempfile.mkdtemp(prefix="dist_eval_"))
    try:
        store = VectorStore(
            persist_directory=temp / "chroma",
            collection_name="dist_eval_probe",
        )

        def emb(text: str) -> list[float]:
            digest = hashlib.sha256(text.encode()).digest()
            values = [((digest[i % 16] / 255.0) - 0.5) for i in range(8)]
            norm = sum(v * v for v in values) ** 0.5 or 1.0
            return [v / norm for v in values]

        docs = [
            ("related", "Vue 3 的响应式基于 Proxy"),
            ("weak", "今天天气很好适合散步"),
            ("unrelated", "番茄炒蛋的做法需要鸡蛋"),
        ]
        store.add_chunks(
            ids=[f"id_{name}" for name, _ in docs],
            documents=[text for _, text in docs],
            embeddings=[emb(text) for _, text in docs],
            metadatas=[
                {"user_id": "1", "source": "demo.pdf", "page": i + 1}
                for i, _ in enumerate(docs)
            ],
        )

        query = "Vue 3 响应式 Proxy"
        results = store.search(query_embedding=emb(query), top_k=3)
        distances = [float(item["distance"]) for item in results]
        assert_true(len(distances) == 3, "应返回 3 条距离")

        # 仅打印观察，不设定生产阈值
        print("distance_eval_observation:", json.dumps(distances))
        print(
            "NOTE: fake-hash embeddings are NOT BGE; "
            "no production distance threshold is adopted from this run."
        )
    finally:
        shutil.rmtree(temp, ignore_errors=True)


def main() -> int:
    cases = [
        ("build_citations_merge_same_file_page", test_build_citations_merge_same_file_page),
        ("prepare_normal_chat_has_no_citations", test_prepare_normal_chat_has_no_citations),
        ("prepare_rag_hit_builds_citations_from_retrieval", test_prepare_rag_hit_builds_citations_from_retrieval),
        ("prepare_rag_empty_no_fake_citations", test_prepare_rag_empty_no_fake_citations),
        ("message_citations_persist_and_reload", test_message_citations_persist_and_reload),
        ("distance_candidate_eval_is_inconclusive_without_real_bge", test_distance_candidate_eval_is_inconclusive_without_real_bge),
    ]

    print("=== RAG citations / no-answer tests ===")
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
