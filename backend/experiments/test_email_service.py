"""
第三阶段：email_service SMTP 实验脚本（全部 Mock，不向真实邮箱发信）。
"""

from __future__ import annotations

import sys
import traceback
from email.message import EmailMessage
from pathlib import Path
from unittest.mock import MagicMock, patch

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.email_service import (
    EmailSendError,
    EmailSMTPConfigError,
    send_register_code_email,
)


BASE_ENV = {
    "SMTP_HOST": "smtp.example.com",
    "SMTP_PORT": "465",
    "SMTP_USERNAME": "noreply@example.com",
    "SMTP_PASSWORD": "secret-smtp-password-do-not-log",
    "SMTP_FROM_EMAIL": "noreply@example.com",
    "SMTP_USE_SSL": "true",
    "SMTP_USE_TLS": "false",
    "SMTP_TIMEOUT": "12.5",
}

# 阻止读取真实 backend/.env，仅使用测试注入的环境变量
_LOAD_DOTENV_PATCH = patch("app.services.email_service.load_dotenv", lambda *a, **k: None)


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_case(name: str, fn) -> tuple[str, bool, str]:
    try:
        fn()
        return name, True, "ok"
    except Exception as exc:
        return name, False, f"{exc}\n{traceback.format_exc()}"


def test_smtp_ssl_flow() -> None:
    env = {**BASE_ENV}
    mock_server = MagicMock()
    with (
        _LOAD_DOTENV_PATCH,
        patch.dict("os.environ", env, clear=False),
        patch("app.services.email_service.smtplib.SMTP_SSL") as mock_ssl,
        patch("app.services.email_service.smtplib.SMTP") as mock_smtp,
    ):
        mock_ssl.return_value = mock_server
        send_register_code_email("User@Example.COM", "012345")

        mock_ssl.assert_called_once()
        kwargs = mock_ssl.call_args.kwargs
        assert_true(kwargs.get("timeout") == 12.5, f"timeout 应传递: {kwargs}")
        assert_true(mock_ssl.call_args.args[0] == "smtp.example.com", "host")
        assert_true(mock_ssl.call_args.args[1] == 465, "port")
        mock_smtp.assert_not_called()
        mock_server.login.assert_called_once_with(
            "noreply@example.com",
            "secret-smtp-password-do-not-log",
        )
        mock_server.send_message.assert_called_once()
        mock_server.quit.assert_called_once()


def test_smtp_starttls_flow() -> None:
    env = {
        **BASE_ENV,
        "SMTP_PORT": "587",
        "SMTP_USE_SSL": "false",
        "SMTP_USE_TLS": "true",
    }
    mock_server = MagicMock()
    with (
        _LOAD_DOTENV_PATCH,
        patch.dict("os.environ", env, clear=False),
        patch("app.services.email_service.smtplib.SMTP_SSL") as mock_ssl,
        patch("app.services.email_service.smtplib.SMTP") as mock_smtp,
    ):
        mock_smtp.return_value = mock_server
        send_register_code_email("a@example.com", "654321")

        mock_smtp.assert_called_once()
        assert_true(mock_smtp.call_args.kwargs.get("timeout") == 12.5, "timeout")
        mock_ssl.assert_not_called()
        mock_server.ehlo.assert_called()
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once()
        mock_server.send_message.assert_called_once()


def test_message_headers_and_body() -> None:
    env = {**BASE_ENV}
    mock_server = MagicMock()
    with (
        _LOAD_DOTENV_PATCH,
        patch.dict("os.environ", env, clear=False),
        patch("app.services.email_service.smtplib.SMTP_SSL", return_value=mock_server),
    ):
        send_register_code_email("recv@example.com", "112233")
        msg = mock_server.send_message.call_args.args[0]
        assert_true(isinstance(msg, EmailMessage), "应为 EmailMessage")
        assert_true(msg["To"] == "recv@example.com", f"To={msg['To']}")
        assert_true(msg["From"] == "noreply@example.com", f"From={msg['From']}")
        assert_true("注册验证码" in (msg["Subject"] or ""), f"Subject={msg['Subject']}")
        body = msg.get_content()
        assert_true("112233" in body, "正文应含验证码")
        assert_true("5 分钟" in body, "应说明有效期")
        assert_true("请勿向他人泄露" in body, "应含防泄露提示")
        assert_true("忽略" in body, "应含非本人操作提示")


def test_missing_config_raises() -> None:
    env = {**BASE_ENV, "SMTP_HOST": ""}
    with _LOAD_DOTENV_PATCH, patch.dict("os.environ", env, clear=False):
        raised = False
        try:
            send_register_code_email("a@example.com", "123456")
        except EmailSMTPConfigError:
            raised = True
        assert_true(raised, "缺少 SMTP_HOST 应抛 EmailSMTPConfigError")


def test_ssl_tls_conflict_raises() -> None:
    env = {**BASE_ENV, "SMTP_USE_SSL": "true", "SMTP_USE_TLS": "true"}
    with _LOAD_DOTENV_PATCH, patch.dict("os.environ", env, clear=False):
        raised = False
        try:
            send_register_code_email("a@example.com", "123456")
        except EmailSMTPConfigError as exc:
            raised = True
            assert_true("不能同时" in str(exc), str(exc))
        assert_true(raised, "SSL+TLS 同时开启应失败")


def test_connect_failure() -> None:
    with (
        _LOAD_DOTENV_PATCH,
        patch.dict("os.environ", BASE_ENV, clear=False),
        patch(
            "app.services.email_service.smtplib.SMTP_SSL",
            side_effect=OSError("connection refused"),
        ),
    ):
        raised = False
        try:
            send_register_code_email("a@example.com", "123456")
        except EmailSendError as exc:
            raised = True
            assert_true("OSError" in str(exc), str(exc))
            assert_true("secret-smtp-password" not in str(exc), "异常不得含密码")
        assert_true(raised, "连接失败应抛 EmailSendError")


def test_login_failure() -> None:
    import smtplib

    mock_server = MagicMock()
    mock_server.login.side_effect = smtplib.SMTPAuthenticationError(535, b"fail")
    with (
        _LOAD_DOTENV_PATCH,
        patch.dict("os.environ", BASE_ENV, clear=False),
        patch("app.services.email_service.smtplib.SMTP_SSL", return_value=mock_server),
    ):
        raised = False
        try:
            send_register_code_email("a@example.com", "123456")
        except EmailSendError:
            raised = True
        assert_true(raised, "登录失败应抛 EmailSendError")
        mock_server.send_message.assert_not_called()


def test_send_failure() -> None:
    import smtplib

    mock_server = MagicMock()
    mock_server.send_message.side_effect = smtplib.SMTPException("send fail")
    with (
        _LOAD_DOTENV_PATCH,
        patch.dict("os.environ", BASE_ENV, clear=False),
        patch("app.services.email_service.smtplib.SMTP_SSL", return_value=mock_server),
    ):
        raised = False
        try:
            send_register_code_email("a@example.com", "998877")
        except EmailSendError:
            raised = True
        assert_true(raised, "发送失败应抛 EmailSendError")


def test_timeout_passed() -> None:
    mock_server = MagicMock()
    env = {**BASE_ENV, "SMTP_TIMEOUT": "7"}
    with (
        _LOAD_DOTENV_PATCH,
        patch.dict("os.environ", env, clear=False),
        patch("app.services.email_service.smtplib.SMTP_SSL") as mock_ssl,
    ):
        mock_ssl.return_value = mock_server
        send_register_code_email("a@example.com", "123456")
        assert_true(mock_ssl.call_args.kwargs.get("timeout") == 7.0, "timeout=7")


def test_logs_do_not_leak_secrets() -> None:
    mock_server = MagicMock()
    code = "445566"
    password = BASE_ENV["SMTP_PASSWORD"]
    with (
        _LOAD_DOTENV_PATCH,
        patch.dict("os.environ", BASE_ENV, clear=False),
        patch("app.services.email_service.smtplib.SMTP_SSL", return_value=mock_server),
        patch("app.services.email_service.logger") as mock_logger,
    ):
        send_register_code_email("leakcheck@example.com", code)
        all_msgs: list[str] = []
        for call in mock_logger.info.call_args_list + mock_logger.error.call_args_list:
            all_msgs.append(" ".join(str(a) for a in call.args))
            all_msgs.append(" ".join(str(v) for v in call.kwargs.values()))
        blob = "\n".join(all_msgs)
        assert_true(code not in blob, f"日志不得含验证码: {blob!r}")
        assert_true(password not in blob, f"日志不得含 SMTP 密码: {blob!r}")


def main() -> int:
    cases = [
        ("smtp_ssl_flow", test_smtp_ssl_flow),
        ("smtp_starttls_flow", test_smtp_starttls_flow),
        ("message_headers_and_body", test_message_headers_and_body),
        ("missing_config_raises", test_missing_config_raises),
        ("ssl_tls_conflict_raises", test_ssl_tls_conflict_raises),
        ("connect_failure", test_connect_failure),
        ("login_failure", test_login_failure),
        ("send_failure", test_send_failure),
        ("timeout_passed", test_timeout_passed),
        ("logs_do_not_leak_secrets", test_logs_do_not_leak_secrets),
    ]
    results = [run_case(name, fn) for name, fn in cases]
    passed = sum(1 for _, ok, _ in results if ok)
    print("=== email_service phase-3 (all mocked) ===")
    for name, ok, detail in results:
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {name}")
        if not ok:
            print(detail)
    print(f"total: {passed}/{len(results)}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
