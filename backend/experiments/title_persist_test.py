"""验证首条消息自动更新标题（临时库，不调 AI）。"""
from __future__ import annotations

import tempfile
from pathlib import Path

import app.database as database

tmpdir = Path(tempfile.mkdtemp())
database.DATABASE_PATH = tmpdir / "title_flow.db"

from app.database_init import init_database  # noqa: E402
from app.repositories.conversation_repository import (  # noqa: E402
    create_conversation,
    get_conversation,
)
from app.services.chat_service import prepare_chat_context  # noqa: E402


def main() -> int:
    init_database()
    results: list[tuple[str, bool, str]] = []

    cid = create_conversation(user_id=1, title="新会话")

    # 第一次：应生成标题
    prepared = prepare_chat_context(
        conversation_id=cid,
        user_id=1,
        message="  请解释一下 JavaScript 的闭包概念  ",
    )
    conv = get_conversation(cid, 1)
    ok = (
        prepared.generated_title is not None
        and conv is not None
        and conv["title"] == prepared.generated_title
        and conv["title"] != "新会话"
    )
    results.append(("first_message_sets_title", ok, str(conv)))

    first_title = conv["title"] if conv else None

    # 第二次：不应覆盖
    prepared2 = prepare_chat_context(
        conversation_id=cid,
        user_id=1,
        message="第二条消息不应该改标题",
    )
    conv2 = get_conversation(cid, 1)
    ok2 = (
        prepared2.generated_title is None
        and conv2 is not None
        and conv2["title"] == first_title
    )
    results.append(("second_message_keeps_title", ok2, str(conv2)))

    print("=== title persistence flow ===")
    failed = 0
    for name, passed, detail in results:
        status = "PASS" if passed else "FAIL"
        if not passed:
            failed += 1
        print(f"[{status}] {name} | {detail[:160]}")

    print(f"summary: {len(results) - failed}/{len(results)} passed")
    return failed


if __name__ == "__main__":
    raise SystemExit(main())
