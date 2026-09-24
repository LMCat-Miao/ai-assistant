"""临时脚本：验证 delete_conversation 在隔离数据库中的行为。"""
import tempfile
from pathlib import Path

import app.database as database
from app.database_init import init_database
from app.repositories.conversation_repository import (
    create_conversation,
    delete_conversation,
    get_conversation,
    get_conversations_by_user,
)
from app.repositories.message_reponsitory import (
    create_message,
    get_messages_by_conversation,
)


def main() -> int:
    tmpdir = Path(tempfile.mkdtemp())
    database.DATABASE_PATH = tmpdir / "test_delete.db"
    init_database()

    results: list[tuple[str, bool, str]] = []

    # 1) 用户 1 创建会话并写入消息
    cid = create_conversation(user_id=1, title="测试会话")
    create_message(cid, "user", "你好")
    create_message(cid, "assistant", "你好，有什么可以帮你")
    msgs_before = get_messages_by_conversation(cid)
    results.append(
        (
            "create_with_messages",
            len(msgs_before) == 2,
            f"msgs={len(msgs_before)}",
        )
    )

    # 2) 用户 2 不能删除用户 1 的会话
    ok_other = delete_conversation(conversation_id=cid, user_id=2)
    still = get_conversation(cid, 1)
    msgs_still = get_messages_by_conversation(cid)
    results.append(
        (
            "other_user_cannot_delete",
            ok_other is False and still is not None and len(msgs_still) == 2,
            f"ok={ok_other}, still={still is not None}, msgs={len(msgs_still)}",
        )
    )

    # 3) 删除不存在的会话
    ok_missing = delete_conversation(conversation_id=99999, user_id=1)
    results.append(
        (
            "missing_returns_false",
            ok_missing is False,
            f"ok={ok_missing}",
        )
    )

    # 4) 用户 1 删除自己的会话，消息一并清理
    ok_owner = delete_conversation(conversation_id=cid, user_id=1)
    gone = get_conversation(cid, 1)
    msgs_after = get_messages_by_conversation(cid)
    results.append(
        (
            "owner_delete_clears_messages",
            ok_owner is True and gone is None and len(msgs_after) == 0,
            f"ok={ok_owner}, gone={gone}, msgs={len(msgs_after)}",
        )
    )

    # 5) 删除最后一个会话后列表为空
    cid2 = create_conversation(user_id=1, title="仅有一个")
    create_message(cid2, "user", "最后一条")
    delete_conversation(cid2, 1)
    lst = get_conversations_by_user(1)
    results.append(
        (
            "list_empty_after_last",
            lst == [],
            f"list={lst}",
        )
    )

    print("=== delete_conversation repository tests ===")
    failed = 0
    for name, passed, detail in results:
        status = "PASS" if passed else "FAIL"
        if not passed:
            failed += 1
        print(f"[{status}] {name} ({detail})")

    print(f"summary: {len(results) - failed}/{len(results)} passed")
    return failed


if __name__ == "__main__":
    raise SystemExit(main())
