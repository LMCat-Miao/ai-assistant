"""
验证 POST /api/messages 的鉴权与会话归属（临时库，不改正式数据）。
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import app.database as database

tmpdir = Path(tempfile.mkdtemp())
database.DATABASE_PATH = tmpdir / "messages_auth.db"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.repositories.conversation_repository import create_conversation  # noqa: E402
from app.repositories.message_reponsitory import (  # noqa: E402
    get_messages_by_conversation,
)


def login(client: TestClient) -> str:
    res = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "123456"},
    )
    assert res.status_code == 200
    return res.json()["data"]["access_token"]


def main() -> int:
    client = TestClient(app)
    results: list[tuple[str, bool, str]] = []

    # A. 未登录 → 401
    r = client.post(
        "/api/messages",
        json={
            "conversation_id": 1,
            "role": "user",
            "content": "未登录写入",
        },
    )
    results.append(
        ("no_token_401", r.status_code == 401, str(r.status_code))
    )

    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}

    # admin 的会话（JWT sub=1）
    own_id = create_conversation(user_id=1, title="我的会话")
    # 其他用户的会话
    other_id = create_conversation(user_id=2, title="别人的会话")

    # B. 向自己的会话写入 → 成功
    r = client.post(
        "/api/messages",
        headers=headers,
        json={
            "conversation_id": own_id,
            "role": "user",
            "content": "合法写入",
        },
    )
    own_msgs = get_messages_by_conversation(own_id)
    ok = r.status_code == 200 and "message_id" in r.json() and len(own_msgs) == 1
    results.append(("own_conversation_ok", ok, r.text[:120]))

    # C. 向他人会话写入 → 404，且不落库
    r = client.post(
        "/api/messages",
        headers=headers,
        json={
            "conversation_id": other_id,
            "role": "user",
            "content": "越权写入",
        },
    )
    other_msgs = get_messages_by_conversation(other_id)
    ok = r.status_code == 404 and other_msgs == []
    results.append(
        ("other_conversation_404_no_write", ok, f"status={r.status_code}, msgs={other_msgs}")
    )

    # D. 不存在的会话 → 404
    r = client.post(
        "/api/messages",
        headers=headers,
        json={
            "conversation_id": 999999,
            "role": "user",
            "content": "不存在",
        },
    )
    results.append(("missing_conversation_404", r.status_code == 404, str(r.status_code)))

    print("=== POST /api/messages auth tests ===")
    failed = 0
    for name, passed, detail in results:
        status = "PASS" if passed else "FAIL"
        if not passed:
            failed += 1
        print(f"[{status}] {name} | {detail}")

    print(f"summary: {len(results) - failed}/{len(results)} passed")
    return failed


if __name__ == "__main__":
    raise SystemExit(main())
