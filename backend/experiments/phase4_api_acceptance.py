"""
第四阶段联调：用 FastAPI TestClient 验收会话 API（不依赖真实 AI）。
使用临时 SQLite，不污染正式库。
"""
from __future__ import annotations

import tempfile
from pathlib import Path

# 必须在 import app.main 之前切换数据库路径
import app.database as database

tmpdir = Path(tempfile.mkdtemp())
database.DATABASE_PATH = tmpdir / "acceptance.db"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.repositories.message_reponsitory import (  # noqa: E402
    create_message,
    get_messages_by_conversation,
)


def login(client: TestClient) -> str:
    res = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "123456"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["code"] == 200
    return body["data"]["access_token"]


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def main() -> int:
    results: list[tuple[str, bool, str]] = []
    client = TestClient(app)
    token = login(client)
    headers = auth_headers(token)

    # 1. 会话列表（空）
    r = client.get("/conversations", headers=headers)
    ok = r.status_code == 200 and r.json()["code"] == 200 and r.json()["data"] == []
    results.append(("GET /conversations empty", ok, r.text[:200]))

    # 2. 创建会话
    r = client.post("/conversations/", headers=headers)
    body = r.json()
    ok = (
        r.status_code == 200
        and body["code"] == 200
        and isinstance(body["data"].get("conversation_id"), int)
    )
    cid = body["data"]["conversation_id"] if ok else None
    results.append(("POST /conversations/", ok, str(body)))

    # 3. 列表非空
    r = client.get("/conversations", headers=headers)
    data = r.json()["data"]
    ok = r.status_code == 200 and any(item["id"] == cid for item in data)
    results.append(("GET /conversations after create", ok, str(data)))

    # 4. 写入消息后读历史
    assert cid is not None
    create_message(cid, "user", "你好")
    create_message(cid, "assistant", "你好，我是助手")
    r = client.get(f"/conversations/{cid}/messages", headers=headers)
    msgs = r.json()["data"]
    ok = r.status_code == 200 and len(msgs) == 2 and msgs[0]["role"] == "user"
    results.append(("GET messages", ok, str(msgs)))

    # 5. 不存在的会话消息 -> 404
    r = client.get("/conversations/999999/messages", headers=headers)
    ok = r.status_code == 404
    results.append(("GET messages missing -> 404", ok, r.text[:120]))

    # 6. 聊天 Schema：缺 conversation_id -> 422
    r = client.post(
        "/api/chat/stream",
        headers=headers,
        json={"message": "hi"},
    )
    ok = r.status_code == 422
    results.append(("POST chat missing conversation_id -> 422", ok, str(r.status_code)))

    # 7. 不存在会话的聊天 -> 404（准备阶段）
    r = client.post(
        "/api/chat/stream",
        headers=headers,
        json={"conversation_id": 999999, "message": "hi"},
    )
    ok = r.status_code == 404
    results.append(("POST chat missing conversation -> 404", ok, r.text[:160]))

    # 8. 无效 Token
    r = client.get("/conversations", headers=auth_headers("bad.token"))
    ok = r.status_code == 401
    results.append(("invalid token -> 401", ok, str(r.status_code)))

    # 9. 无 Token
    r = client.get("/conversations")
    ok = r.status_code in (401, 403)
    results.append(("no token -> 401/403", ok, str(r.status_code)))

    # 10. 删除会话并清理消息
    r = client.delete(f"/conversations/{cid}", headers=headers)
    ok = r.status_code == 200 and r.json()["code"] == 200
    msgs_after = get_messages_by_conversation(cid)
    ok = ok and msgs_after == []
    results.append(("DELETE conversation clears messages", ok, f"msgs={msgs_after}"))

    # 11. 再删不存在 -> 404
    r = client.delete(f"/conversations/{cid}", headers=headers)
    ok = r.status_code == 404
    results.append(("DELETE missing -> 404", ok, str(r.status_code)))

    # 12. 路由重复：确认 /api/auth/login 仍可用（重复注册不致命）
    r = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "wrong"},
    )
    ok = r.status_code == 200 and r.json()["code"] == 401
    results.append(("login wrong password still works", ok, r.text[:120]))

    print("=== Phase 4 API acceptance (TestClient) ===")
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
