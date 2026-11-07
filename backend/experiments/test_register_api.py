"""
第四阶段：注册 API 集成实验（TestClient + Mock，不向真实邮箱发信）。

不 FLUSHDB；不删除既有业务用户。
"""

from __future__ import annotations

import sys
import traceback
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.email_code_service import (
    CODE_TTL_SECONDS,
    CooldownActiveError,
    IssuedCode,
    RedisUnavailableError,
    VerifyResult,
    VerifyStatus,
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


@contextmanager
def api_client(**patches: object):
    """绕过 lifespan 真实初始化，并应用传入的 patch 目标。"""

    with ExitStack() as stack:
        stack.enter_context(patch("app.main.init_database"))
        stack.enter_context(patch("app.main.init_redis", return_value=True))
        stack.enter_context(patch("app.main.dispose_engine"))
        stack.enter_context(patch("app.main.close_redis"))
        mocks: dict[str, object] = {}
        for target, kwargs in patches.items():
            if not isinstance(kwargs, dict):
                raise TypeError("patch kwargs must be dict")
            mocks[target] = stack.enter_context(patch(target, **kwargs))
        from app.main import app

        with TestClient(app) as client:
            yield client, mocks


def _assert_no_secrets(payload: dict) -> None:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    for forbidden in ("request_id", "code_hash", "hmac", "access_token", "password"):
        assert_true(forbidden not in data, f"响应 data 不得含 {forbidden}: {data}")


def test_send_code_success_unregistered() -> None:
    issued = IssuedCode(
        email="new@example.com",
        code="012345",
        request_id="rid-1",
        expires_in=CODE_TTL_SECONDS,
    )
    with api_client(
        **{
            "app.api.auth.get_user_by_email": {"return_value": None},
            "app.api.auth.issue_code": {"return_value": issued},
            "app.api.auth.send_register_code_email": {},
            "app.api.auth.cancel_code_issue": {},
        }
    ) as (client, mocks):
        r = client.post(
            "/api/auth/email/send-code",
            json={"email": "  New@Example.COM "},
        )
        body = r.json()
        assert_true(r.status_code == 200, str(r.status_code))
        assert_true(body["code"] == 200, str(body))
        assert_true(body["data"]["expires_in"] == CODE_TTL_SECONDS, str(body))
        mocks["app.api.auth.issue_code"].assert_called_once()
        mocks["app.api.auth.send_register_code_email"].assert_called_once_with(
            "new@example.com",
            "012345",
        )
        mocks["app.api.auth.cancel_code_issue"].assert_not_called()
        _assert_no_secrets(body)
        assert_true("012345" not in str(body), "响应不得含验证码")


def test_send_code_already_registered_no_mail() -> None:
    with api_client(
        **{
            "app.api.auth.get_user_by_email": {
                "return_value": {"id": 1, "username": "u"},
            },
            "app.api.auth.issue_code": {},
            "app.api.auth.send_register_code_email": {},
        }
    ) as (client, mocks):
        r = client.post(
            "/api/auth/email/send-code",
            json={"email": "taken@example.com"},
        )
        body = r.json()
        assert_true(body["code"] == 200, str(body))
        mocks["app.api.auth.issue_code"].assert_not_called()
        mocks["app.api.auth.send_register_code_email"].assert_not_called()
        _assert_no_secrets(body)


def test_send_code_cooldown() -> None:
    with api_client(
        **{
            "app.api.auth.get_user_by_email": {"return_value": None},
            "app.api.auth.issue_code": {
                "side_effect": CooldownActiveError("a@example.com", retry_after=42),
            },
            "app.api.auth.send_register_code_email": {},
        }
    ) as (client, mocks):
        r = client.post(
            "/api/auth/email/send-code",
            json={"email": "a@example.com"},
        )
        body = r.json()
        assert_true(body["code"] == 429, str(body))
        assert_true(body["data"]["retry_after"] == 42, str(body))
        mocks["app.api.auth.send_register_code_email"].assert_not_called()


def test_send_code_redis_unavailable() -> None:
    with api_client(
        **{
            "app.api.auth.get_user_by_email": {"return_value": None},
            "app.api.auth.issue_code": {
                "side_effect": RedisUnavailableError("down"),
            },
            "app.api.auth.send_register_code_email": {},
        }
    ) as (client, mocks):
        r = client.post(
            "/api/auth/email/send-code",
            json={"email": "a@example.com"},
        )
        body = r.json()
        assert_true(body["code"] == 503, str(body))
        mocks["app.api.auth.send_register_code_email"].assert_not_called()


def test_send_code_smtp_fail_and_cancel() -> None:
    from app.services.email_service import EmailSendError

    issued = IssuedCode(
        email="a@example.com",
        code="111222",
        request_id="rid-smtp",
        expires_in=300,
    )
    with api_client(
        **{
            "app.api.auth.get_user_by_email": {"return_value": None},
            "app.api.auth.issue_code": {"return_value": issued},
            "app.api.auth.send_register_code_email": {
                "side_effect": EmailSendError("SMTPException"),
            },
            "app.api.auth.cancel_code_issue": {"return_value": (True, True)},
        }
    ) as (client, mocks):
        r = client.post(
            "/api/auth/email/send-code",
            json={"email": "a@example.com"},
        )
        body = r.json()
        assert_true(body["code"] == 503, str(body))
        mocks["app.api.auth.cancel_code_issue"].assert_called_once_with(
            "a@example.com",
            "rid-smtp",
        )
        assert_true("111222" not in str(body), "不得泄露验证码")
        assert_true("rid-smtp" not in str(body), "不得泄露 request_id")


def test_send_code_smtp_fail_cancel_fail_no_leak() -> None:
    from app.services.email_service import EmailSendError

    issued = IssuedCode(
        email="a@example.com",
        code="333444",
        request_id="rid-secret",
        expires_in=300,
    )
    with api_client(
        **{
            "app.api.auth.get_user_by_email": {"return_value": None},
            "app.api.auth.issue_code": {"return_value": issued},
            "app.api.auth.send_register_code_email": {
                "side_effect": EmailSendError("fail"),
            },
            "app.api.auth.cancel_code_issue": {
                "side_effect": RuntimeError("cancel boom"),
            },
            "app.api.auth.logger": {},
        }
    ) as (client, mocks):
        r = client.post(
            "/api/auth/email/send-code",
            json={"email": "a@example.com"},
        )
        body = r.json()
        assert_true(body["code"] == 503, str(body))
        blob = str(body) + str(mocks["app.api.auth.logger"].error.call_args_list)
        assert_true("333444" not in blob, "日志/响应不得含验证码")
        assert_true("rid-secret" not in str(body), "响应不得含 request_id")


def test_register_success() -> None:
    with api_client(
        **{
            "app.api.auth.get_user_by_email": {"return_value": None},
            "app.api.auth.get_user_by_username": {"return_value": None},
            "app.api.auth.verify_and_consume_code": {
                "return_value": VerifyResult(VerifyStatus.OK, 0),
            },
            "app.api.auth.hash_password": {"return_value": "$2b$hashed"},
            "app.api.auth.create_user": {"return_value": 99},
            "app.api.auth.create_access_token": {},
        }
    ) as (client, mocks):
        r = client.post(
            "/api/auth/register",
            json={
                "email": "ok@example.com",
                "code": "123456",
                "username": "newuser",
                "password": "password1",
            },
        )
        body = r.json()
        assert_true(r.status_code == 200, f"HTTP 约定为 200，实际 {r.status_code}")
        assert_true(body["code"] == 200, str(body))
        assert_true(body["data"]["user_id"] == 99, str(body))
        assert_true(body["data"]["username"] == "newuser", str(body))
        mocks["app.api.auth.verify_and_consume_code"].assert_called_once()
        mocks["app.api.auth.hash_password"].assert_called_once_with("password1")
        mocks["app.api.auth.create_user"].assert_called_once()
        kwargs = mocks["app.api.auth.create_user"].call_args.kwargs
        assert_true(kwargs["password_hash"] == "$2b$hashed", str(kwargs))
        assert_true(kwargs["password_hash"] != "password1", "不得存明文")
        assert_true(kwargs.get("email") == "ok@example.com", str(kwargs))
        mocks["app.api.auth.create_access_token"].assert_not_called()
        assert_true("access_token" not in str(body), "不得自动登录发 JWT")


_REGISTER_CONFLICT_MESSAGE = "邮箱或用户名已被占用，请更换后重新获取验证码"
_REGISTER_CODE_FAIL_MESSAGE = "验证码无效或已过期，请重新获取"


def _post_register_verify_fail(
    *,
    verify_status: VerifyStatus,
    attempts: int = 0,
) -> tuple[int, dict, object]:
    """提交注册并 mock 指定验码失败状态；返回 (http_status, body, mocks)。"""

    with api_client(
        **{
            "app.api.auth.get_user_by_email": {"return_value": None},
            "app.api.auth.get_user_by_username": {"return_value": None},
            "app.api.auth.verify_and_consume_code": {
                "return_value": VerifyResult(verify_status, attempts),
            },
            "app.api.auth.create_user": {},
            "app.api.auth.hash_password": {},
        }
    ) as (client, mocks):
        r = client.post(
            "/api/auth/register",
            json={
                "email": "ok@example.com",
                "code": "000000",
                "username": "newuser",
                "password": "password1",
            },
        )
        return r.status_code, r.json(), mocks


def test_register_wrong_code() -> None:
    """已存在验证码记录时提交错误验证码（INVALID）。"""

    status, body, mocks = _post_register_verify_fail(
        verify_status=VerifyStatus.INVALID,
        attempts=1,
    )
    assert_true(status == 200, f"HTTP 约定为 200，实际 {status}")
    assert_true(body["code"] == 400, str(body))
    assert_true(body["message"] == _REGISTER_CODE_FAIL_MESSAGE, str(body))
    mocks["app.api.auth.verify_and_consume_code"].assert_called_once()
    mocks["app.api.auth.create_user"].assert_not_called()


def test_register_expired_code() -> None:
    """无验证码记录 / 过期（EXPIRED）。"""

    status, body, mocks = _post_register_verify_fail(
        verify_status=VerifyStatus.EXPIRED,
        attempts=0,
    )
    assert_true(status == 200, f"HTTP 约定为 200，实际 {status}")
    assert_true(body["code"] == 400, str(body))
    assert_true(body["message"] == _REGISTER_CODE_FAIL_MESSAGE, str(body))
    mocks["app.api.auth.create_user"].assert_not_called()


def test_register_exhausted() -> None:
    """验证码错误次数耗尽（EXHAUSTED）。"""

    status, body, mocks = _post_register_verify_fail(
        verify_status=VerifyStatus.EXHAUSTED,
        attempts=5,
    )
    assert_true(status == 200, f"HTTP 约定为 200，实际 {status}")
    assert_true(body["code"] == 400, str(body))
    assert_true(body["message"] == _REGISTER_CODE_FAIL_MESSAGE, str(body))
    mocks["app.api.auth.create_user"].assert_not_called()


def test_register_verify_fail_statuses_unified() -> None:
    """无码、错码、过期、耗尽对外 HTTP/code/message 完全一致。"""

    cases = (
        (VerifyStatus.EXPIRED, 0),
        (VerifyStatus.INVALID, 1),
        (VerifyStatus.EXHAUSTED, 5),
    )
    observed: list[tuple[int, int, str]] = []
    for status, attempts in cases:
        http_status, body, _mocks = _post_register_verify_fail(
            verify_status=status,
            attempts=attempts,
        )
        observed.append((http_status, body["code"], body["message"]))

    first = observed[0]
    for item in observed[1:]:
        assert_true(item == first, f"验码失败响应不一致: {observed!r}")
    assert_true(first[0] == 200, str(first))
    assert_true(first[1] == 400, str(first))
    assert_true(first[2] == _REGISTER_CODE_FAIL_MESSAGE, str(first))


def test_register_redis_unavailable() -> None:
    with api_client(
        **{
            "app.api.auth.get_user_by_email": {"return_value": None},
            "app.api.auth.get_user_by_username": {"return_value": None},
            "app.api.auth.verify_and_consume_code": {
                "side_effect": RedisUnavailableError("down"),
            },
            "app.api.auth.create_user": {},
        }
    ) as (client, mocks):
        r = client.post(
            "/api/auth/register",
            json={
                "email": "ok@example.com",
                "code": "123456",
                "username": "newuser",
                "password": "password1",
            },
        )
        assert_true(r.status_code == 200, f"HTTP 约定为 200，实际 {r.status_code}")
        assert_true(r.json()["code"] == 503, str(r.json()))
        mocks["app.api.auth.create_user"].assert_not_called()


def test_register_wrong_code_anti_email_enumeration() -> None:
    """已注册邮箱 + 错码 与 未注册邮箱 + 错码：业务 code/message 必须一致，且都会验码。"""

    payload = {
        "email": "probe@example.com",
        "code": "000000",
        "username": "probeuser",
        "password": "password1",
    }
    common_verify = {
        "return_value": VerifyResult(VerifyStatus.INVALID, 1),
    }

    with api_client(
        **{
            "app.api.auth.get_user_by_email": {
                "return_value": {"id": 1, "username": "existing"},
            },
            "app.api.auth.get_user_by_username": {"return_value": None},
            "app.api.auth.verify_and_consume_code": common_verify,
            "app.api.auth.create_user": {},
            "app.api.auth.hash_password": {},
        }
    ) as (client_reg, mocks_reg):
        r_registered = client_reg.post("/api/auth/register", json=payload)
        body_registered = r_registered.json()
        mocks_reg["app.api.auth.verify_and_consume_code"].assert_called_once()
        mocks_reg["app.api.auth.create_user"].assert_not_called()
        mocks_reg["app.api.auth.hash_password"].assert_not_called()

    with api_client(
        **{
            "app.api.auth.get_user_by_email": {"return_value": None},
            "app.api.auth.get_user_by_username": {"return_value": None},
            "app.api.auth.verify_and_consume_code": common_verify,
            "app.api.auth.create_user": {},
            "app.api.auth.hash_password": {},
        }
    ) as (client_new, mocks_new):
        r_new = client_new.post("/api/auth/register", json=payload)
        body_new = r_new.json()
        mocks_new["app.api.auth.verify_and_consume_code"].assert_called_once()
        mocks_new["app.api.auth.create_user"].assert_not_called()

    assert_true(r_registered.status_code == 200, str(r_registered.status_code))
    assert_true(r_new.status_code == 200, str(r_new.status_code))
    assert_true(body_registered["code"] == body_new["code"] == 400, str(body_registered))
    assert_true(
        body_registered["message"]
        == body_new["message"]
        == _REGISTER_CODE_FAIL_MESSAGE,
        f"{body_registered!r} vs {body_new!r}",
    )


def test_register_duplicate_email() -> None:
    """验码成功后邮箱冲突：须已调用 verify，且使用模糊 409 文案。"""

    with api_client(
        **{
            "app.api.auth.get_user_by_email": {
                "return_value": {"id": 1, "username": "x"},
            },
            "app.api.auth.get_user_by_username": {"return_value": None},
            "app.api.auth.verify_and_consume_code": {
                "return_value": VerifyResult(VerifyStatus.OK, 0),
            },
            "app.api.auth.hash_password": {},
            "app.api.auth.create_user": {},
        }
    ) as (client, mocks):
        r = client.post(
            "/api/auth/register",
            json={
                "email": "dup@example.com",
                "code": "123456",
                "username": "newuser",
                "password": "password1",
            },
        )
        body = r.json()
        assert_true(r.status_code == 200, f"HTTP 约定为 200，实际 {r.status_code}")
        assert_true(body["code"] == 409, str(body))
        assert_true(body["message"] == _REGISTER_CONFLICT_MESSAGE, str(body))
        mocks["app.api.auth.verify_and_consume_code"].assert_called_once()
        mocks["app.api.auth.hash_password"].assert_not_called()
        mocks["app.api.auth.create_user"].assert_not_called()


def test_register_duplicate_username() -> None:
    """验码成功后用户名冲突：与邮箱冲突完全相同的 code/message。"""

    with api_client(
        **{
            "app.api.auth.get_user_by_email": {"return_value": None},
            "app.api.auth.get_user_by_username": {
                "return_value": {"id": 2, "username": "taken"},
            },
            "app.api.auth.verify_and_consume_code": {
                "return_value": VerifyResult(VerifyStatus.OK, 0),
            },
            "app.api.auth.hash_password": {},
            "app.api.auth.create_user": {},
        }
    ) as (client, mocks):
        r = client.post(
            "/api/auth/register",
            json={
                "email": "ok@example.com",
                "code": "123456",
                "username": "taken",
                "password": "password1",
            },
        )
        body = r.json()
        assert_true(r.status_code == 200, f"HTTP 约定为 200，实际 {r.status_code}")
        assert_true(body["code"] == 409, str(body))
        assert_true(body["message"] == _REGISTER_CONFLICT_MESSAGE, str(body))
        mocks["app.api.auth.verify_and_consume_code"].assert_called_once()
        mocks["app.api.auth.create_user"].assert_not_called()


def test_register_email_and_username_conflict_same_response() -> None:
    """邮箱冲突与用户名冲突对外不可区分。"""

    email_conflict_body: dict
    username_conflict_body: dict

    with api_client(
        **{
            "app.api.auth.get_user_by_email": {
                "return_value": {"id": 1, "username": "x"},
            },
            "app.api.auth.get_user_by_username": {"return_value": None},
            "app.api.auth.verify_and_consume_code": {
                "return_value": VerifyResult(VerifyStatus.OK, 0),
            },
            "app.api.auth.create_user": {},
        }
    ) as (client, _mocks):
        r = client.post(
            "/api/auth/register",
            json={
                "email": "dup@example.com",
                "code": "123456",
                "username": "newuser",
                "password": "password1",
            },
        )
        email_conflict_body = r.json()
        assert_true(r.status_code == 200, str(r.status_code))

    with api_client(
        **{
            "app.api.auth.get_user_by_email": {"return_value": None},
            "app.api.auth.get_user_by_username": {
                "return_value": {"id": 2, "username": "taken"},
            },
            "app.api.auth.verify_and_consume_code": {
                "return_value": VerifyResult(VerifyStatus.OK, 0),
            },
            "app.api.auth.create_user": {},
        }
    ) as (client, _mocks):
        r = client.post(
            "/api/auth/register",
            json={
                "email": "ok@example.com",
                "code": "123456",
                "username": "taken",
                "password": "password1",
            },
        )
        username_conflict_body = r.json()
        assert_true(r.status_code == 200, str(r.status_code))

    assert_true(
        email_conflict_body["code"] == username_conflict_body["code"] == 409,
        str(email_conflict_body),
    )
    assert_true(
        email_conflict_body["message"]
        == username_conflict_body["message"]
        == _REGISTER_CONFLICT_MESSAGE,
        f"{email_conflict_body!r} vs {username_conflict_body!r}",
    )


def test_register_integrity_after_consume() -> None:
    with api_client(
        **{
            "app.api.auth.get_user_by_email": {"return_value": None},
            "app.api.auth.get_user_by_username": {"return_value": None},
            "app.api.auth.verify_and_consume_code": {
                "return_value": VerifyResult(VerifyStatus.OK, 0),
            },
            "app.api.auth.hash_password": {"return_value": "$2b$x"},
            "app.api.auth.create_user": {
                "side_effect": IntegrityError("stmt", {}, Exception("dup")),
            },
            "app.api.auth.create_access_token": {},
        }
    ) as (client, mocks):
        r = client.post(
            "/api/auth/register",
            json={
                "email": "race@example.com",
                "code": "123456",
                "username": "raceuser",
                "password": "password1",
            },
        )
        body = r.json()
        assert_true(r.status_code == 200, f"HTTP 约定为 200，实际 {r.status_code}")
        assert_true(body["code"] == 409, str(body))
        assert_true(body["message"] == _REGISTER_CONFLICT_MESSAGE, body["message"])
        mocks["app.api.auth.create_access_token"].assert_not_called()


def test_register_skips_create_without_verify_ok() -> None:
    with api_client(
        **{
            "app.api.auth.get_user_by_email": {"return_value": None},
            "app.api.auth.get_user_by_username": {"return_value": None},
            "app.api.auth.verify_and_consume_code": {
                "return_value": VerifyResult(VerifyStatus.INVALID, 2),
            },
            "app.api.auth.hash_password": {},
            "app.api.auth.create_user": {},
        }
    ) as (client, mocks):
        client.post(
            "/api/auth/register",
            json={
                "email": "ok@example.com",
                "code": "123456",
                "username": "newuser",
                "password": "password1",
            },
        )
        mocks["app.api.auth.hash_password"].assert_not_called()
        mocks["app.api.auth.create_user"].assert_not_called()


def main() -> int:
    cases = [
        ("send_code_success_unregistered", test_send_code_success_unregistered),
        ("send_code_already_registered_no_mail", test_send_code_already_registered_no_mail),
        ("send_code_cooldown", test_send_code_cooldown),
        ("send_code_redis_unavailable", test_send_code_redis_unavailable),
        ("send_code_smtp_fail_and_cancel", test_send_code_smtp_fail_and_cancel),
        ("send_code_smtp_fail_cancel_fail_no_leak", test_send_code_smtp_fail_cancel_fail_no_leak),
        ("register_success", test_register_success),
        ("register_wrong_code", test_register_wrong_code),
        ("register_wrong_code_anti_email_enumeration", test_register_wrong_code_anti_email_enumeration),
        ("register_expired_code", test_register_expired_code),
        ("register_exhausted", test_register_exhausted),
        ("register_verify_fail_statuses_unified", test_register_verify_fail_statuses_unified),
        ("register_redis_unavailable", test_register_redis_unavailable),
        ("register_duplicate_email", test_register_duplicate_email),
        ("register_duplicate_username", test_register_duplicate_username),
        (
            "register_email_and_username_conflict_same_response",
            test_register_email_and_username_conflict_same_response,
        ),
        ("register_integrity_after_consume", test_register_integrity_after_consume),
        ("register_skips_create_without_verify_ok", test_register_skips_create_without_verify_ok),
    ]
    results = [run_case(name, fn) for name, fn in cases]
    passed = sum(1 for _, ok, _ in results if ok)
    print("=== register API phase-4 (TestClient + Mock) ===")
    for name, ok, detail in results:
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {name}")
        if not ok:
            print(detail)
    print(f"total: {passed}/{len(results)}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
