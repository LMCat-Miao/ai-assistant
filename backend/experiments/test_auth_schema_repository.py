"""
第一阶段：auth Schema + user_repository 最小校验（实验脚本，非 pytest）。

不发送真实邮件；仅创建/清理本脚本专用测试用户，不删除已有业务账号。
"""

from __future__ import annotations

import sys
import traceback
import uuid
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.password import hash_password
from app.database import get_connection
from app.repositories.user_repository import (
    create_user,
    get_user_by_email,
    get_user_by_username,
)
from app.schemas.auth import RegisterRequest, SendRegisterCodeRequest


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_case(name: str, fn) -> tuple[str, bool, str]:
    try:
        fn()
        return name, True, "ok"
    except Exception as exc:
        return name, False, f"{exc}\n{traceback.format_exc()}"


def test_schema_accepts_valid_email() -> None:
    req = SendRegisterCodeRequest(email="User@Example.COM")
    assert_true(str(req.email) == "user@example.com", "邮箱应规范化为小写")


def test_schema_strips_and_lowers_email() -> None:
    req = SendRegisterCodeRequest(email="  Foo.Bar@Example.COM  ")
    assert_true(str(req.email) == "foo.bar@example.com", "应 strip + lower")


def test_code_must_be_six_digits_string() -> None:
    base = {
        "email": "ok@example.com",
        "username": "user_ok",
        "password": "password1",
    }
    ok = RegisterRequest(code="012345", **base)
    assert_true(ok.code == "012345", "应保留前导 0 的字符串")
    assert_true(isinstance(ok.code, str), "code 必须是 str")

    for bad in ("12345", "1234567", "12ab56", 123456):
        raised = False
        try:
            RegisterRequest(code=bad, **base)  # type: ignore[arg-type]
        except ValidationError:
            raised = True
        assert_true(raised, f"非法 code 应被拒绝: {bad!r}")


def test_username_max_length_64() -> None:
    base = {
        "email": "len@example.com",
        "code": "123456",
        "password": "password1",
    }
    RegisterRequest(username="a" * 64, **base)

    raised = False
    try:
        RegisterRequest(username="a" * 65, **base)
    except ValidationError:
        raised = True
    assert_true(raised, "username 超过 64 应被拒绝")

    stripped = RegisterRequest(username="  name_ok  ", **base)
    assert_true(stripped.username == "name_ok", "username 应去除首尾空格")


def test_create_user_without_email_compatible() -> None:
    suffix = uuid.uuid4().hex[:12]
    username = f"p1_noemail_{suffix}"
    user_id = create_user(
        username=username,
        password_hash=hash_password("password1"),
    )
    try:
        row = get_user_by_username(username)
        assert_true(row is not None, "应能按 username 查到")
        assert_true(int(row["id"]) == int(user_id), "id 应一致")
        # email 列应为 NULL：按邮箱查不到
        assert_true(
            get_user_by_email(f"{username}@example.com") is None,
            "未写 email 时不应被邮箱命中",
        )
    finally:
        _delete_user_by_id(user_id)


def test_create_and_get_user_by_email() -> None:
    suffix = uuid.uuid4().hex[:12]
    username = f"p1_email_{suffix}"
    email = f"  P1.Test.{suffix}@Example.COM  "
    user_id = create_user(
        username=username,
        password_hash=hash_password("password1"),
        email=email,
    )
    try:
        expected = f"p1.test.{suffix}@example.com"
        found = get_user_by_email(f"  {expected.upper()}  ")
        assert_true(found is not None, "get_user_by_email 应命中")
        assert_true(int(found["id"]) == int(user_id), "id 应一致")
        assert_true(found["username"] == username, "username 应一致")
        assert_true("password_hash" in found, "返回结构应含 password_hash 键")
    finally:
        _delete_user_by_id(user_id)


def test_duplicate_email_raises_integrity_error() -> None:
    suffix = uuid.uuid4().hex[:12]
    email = f"p1.dup.{suffix}@example.com"
    username1 = f"p1_dup_a_{suffix}"
    username2 = f"p1_dup_b_{suffix}"
    user_id = create_user(
        username=username1,
        password_hash=hash_password("password1"),
        email=email,
    )
    raised = False
    try:
        try:
            create_user(
                username=username2,
                password_hash=hash_password("password1"),
                email=email,
            )
        except IntegrityError:
            raised = True
        assert_true(raised, "重复 email 应由唯一索引触发 IntegrityError")
        # 原用户仍在且未被覆盖
        original = get_user_by_username(username1)
        assert_true(original is not None, "原用户应仍存在")
        assert_true(get_user_by_username(username2) is None, "冲突用户不应插入")
    finally:
        _delete_user_by_id(user_id)


def _delete_user_by_id(user_id: int) -> None:
    """仅删除本脚本创建的测试用户。"""

    with get_connection() as conn:
        conn.execute(
            text("DELETE FROM users WHERE id = :id"),
            {"id": user_id},
        )
        conn.commit()


def main() -> int:
    cases = [
        ("schema_accepts_valid_email", test_schema_accepts_valid_email),
        ("schema_strips_and_lowers_email", test_schema_strips_and_lowers_email),
        ("code_must_be_six_digits_string", test_code_must_be_six_digits_string),
        ("username_max_length_64", test_username_max_length_64),
        ("create_user_without_email_compatible", test_create_user_without_email_compatible),
        ("create_and_get_user_by_email", test_create_and_get_user_by_email),
        ("duplicate_email_raises_integrity_error", test_duplicate_email_raises_integrity_error),
    ]

    results = [run_case(name, fn) for name, fn in cases]
    passed = sum(1 for _, ok, _ in results if ok)
    print("=== auth schema + repository phase-1 ===")
    for name, ok, detail in results:
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {name}")
        if not ok:
            print(detail)
    print(f"total: {passed}/{len(results)}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
