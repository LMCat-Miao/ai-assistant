"""
双用户认证与会话隔离自动化测试（临时 SQLite，不污染正式库）。
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import app.database as database

tmpdir = Path(tempfile.mkdtemp())
database.DATABASE_PATH = tmpdir / "users_isolation.db"

from fastapi.testclient import TestClient  # noqa: E402

from app.core.password import hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.repositories.conversation_repository import (  # noqa: E402
    create_conversation,
)
from app.repositories.message_reponsitory import create_message  # noqa: E402
from app.repositories.user_repository import (  # noqa: E402
    create_user,
    get_user_by_username,
)


def login(client: TestClient, username: str, password: str) -> dict:
    return client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def main() -> int:
    client = TestClient(app)
    results: list[tuple[str, bool, str]] = []

    # init_database 已在 import app.main 时执行，admin 应已存在
    admin_row = get_user_by_username("admin")
    results.append(
        (
            "admin_seeded_id_1",
            admin_row is not None and int(admin_row["id"]) == 1,
            str(admin_row),
        )
    )

    # 创建 test_user（id=2），密码不写进业务代码，仅本测试临时使用
    test_password = "test-pass-isolation-only"
    if get_user_by_username("test_user") is None:
        create_user(
            username="test_user",
            password_hash=hash_password(test_password),
            user_id=2,
        )

    # 1. admin 正确密码
    r = login(client, "admin", "123456")
    body = r.json()
    ok = r.status_code == 200 and body.get("code") == 200
    admin_token = body["data"]["access_token"] if ok else ""
    results.append(("admin_login_ok", ok, str(body.get("code"))))

    # 2. admin 错误密码
    r = login(client, "admin", "wrong-password")
    ok = r.status_code == 200 and r.json().get("code") == 401
    results.append(("admin_login_wrong_password", ok, str(r.json())))

    # 3. test_user 正确密码
    r = login(client, "test_user", test_password)
    body = r.json()
    ok = r.status_code == 200 and body.get("code") == 200
    test_token = body["data"]["access_token"] if ok else ""
    results.append(("test_user_login_ok", ok, str(body.get("code"))))

    # 4. 两个账号不同 user_id（通过 /api/user/me）
    admin_me = client.get("/api/user/me", headers=auth_header(admin_token)).json()
    test_me = client.get("/api/user/me", headers=auth_header(test_token)).json()
    admin_uid = str(admin_me["data"]["user_id"])
    test_uid = str(test_me["data"]["user_id"])
    ok = admin_uid == "1" and test_uid == "2" and admin_uid != test_uid
    results.append(
        ("different_user_ids", ok, f"admin={admin_uid}, test={test_uid}")
    )

    # admin 创建会话并写入消息
    r = client.post("/conversations/", headers=auth_header(admin_token))
    admin_cid = r.json()["data"]["conversation_id"]
    create_message(admin_cid, "user", "admin 的秘密消息")

    # 5. test_user 列表看不到 admin 会话
    r = client.get("/conversations", headers=auth_header(test_token))
    test_list = r.json().get("data") or []
    ok = r.json().get("code") == 200 and all(
        item["id"] != admin_cid for item in test_list
    )
    results.append(("test_list_hides_admin_conv", ok, str(test_list)))

    # 6. test_user 无法读 admin 历史
    r = client.get(
        f"/conversations/{admin_cid}/messages",
        headers=auth_header(test_token),
    )
    results.append(
        ("test_cannot_read_admin_messages", r.status_code == 404, str(r.status_code))
    )

    # 7. test_user 无法删 admin 会话
    r = client.delete(
        f"/conversations/{admin_cid}",
        headers=auth_header(test_token),
    )
    results.append(
        ("test_cannot_delete_admin_conv", r.status_code == 404, str(r.status_code))
    )

    # 8. test_user 无法向 admin 会话发起流式聊天
    r = client.post(
        "/api/chat/stream",
        headers=auth_header(test_token),
        json={"conversation_id": admin_cid, "message": "越权聊天"},
    )
    results.append(
        ("test_cannot_stream_admin_conv", r.status_code == 404, str(r.status_code))
    )

    # 9. test_user 无法 POST /api/messages 写入 admin 会话
    r = client.post(
        "/api/messages",
        headers=auth_header(test_token),
        json={
            "conversation_id": admin_cid,
            "role": "user",
            "content": "越权写入",
        },
    )
    results.append(
        ("test_cannot_post_message_admin_conv", r.status_code == 404, str(r.status_code))
    )

    # 重复执行 ensure_admin 不覆盖密码：改哈希不应被 init 改回——仅验证再次 ensure 不报错
    from app.services.user_seed import ensure_admin_user

    msg = ensure_admin_user()
    results.append(
        ("ensure_admin_skips_existing", "跳过" in msg or "已存在" in msg, msg)
    )

    print("=== users + isolation tests ===")
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
