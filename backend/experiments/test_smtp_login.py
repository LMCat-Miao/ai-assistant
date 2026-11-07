"""
独立 SMTP 登录诊断（真实连接，不发送邮件）。

使用 SMTP_SSL + EHLO 后，强制 AUTH LOGIN（server.auth），不调用 send_message。

安全约束：
- 不打印 SMTP_USERNAME / SMTP_PASSWORD
- 不打印 AUTH 载荷、Base64、密钥
- 不开启 smtplib debuglevel
- 不打印完整异常消息或可能含敏感信息的响应正文
"""

from __future__ import annotations

import os
import smtplib
import ssl
import sys
from pathlib import Path

from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = BACKEND_ROOT / ".env"

# 本诊断固定探测 QQ 企业常用入口；账号/密码仍来自 .env
DIAG_HOST = "smtp.qq.com"
DIAG_PORT = 465
DEFAULT_TIMEOUT = 30.0


def _safe_smtp_code(exc: BaseException) -> object:
    return getattr(exc, "smtp_code", None)


def _make_auth_login_object(username: str, password: str):
    """
    强制 SMTP AUTH LOGIN 的 authobject。

    - challenge 为 None（含无参初始响应探测）时返回 None，不发送 initial-response
    - 第 1 次挑战返回 username
    - 第 2 次挑战返回 password
    - 额外挑战抛出不含敏感信息的 RuntimeError
    返回值由 smtplib 自行 Base64 编码；本函数不打印任何凭据。
    """

    challenge_count = 0

    def authobject(challenge=None):
        nonlocal challenge_count
        if challenge is None:
            return None
        challenge_count += 1
        if challenge_count == 1:
            return username
        if challenge_count == 2:
            return password
        raise RuntimeError("unexpected extra AUTH LOGIN challenge")

    return authobject


def _close_smtp(server: smtplib.SMTP | smtplib.SMTP_SSL | None) -> None:
    """安全关闭；quit 失败不影响主流程结果。"""
    if server is None:
        return
    try:
        server.quit()
    except Exception:
        try:
            server.close()
        except Exception:
            pass


def main() -> int:
    load_dotenv(ENV_PATH)

    username = os.getenv("SMTP_USERNAME")
    password = os.getenv("SMTP_PASSWORD")
    timeout_raw = (os.getenv("SMTP_TIMEOUT") or "").strip()

    if not username or username.strip() == "":
        print("result: FAIL")
        print("connect_ok: False")
        print("error_type: ConfigError")
        print("detail: SMTP_USERNAME missing_or_empty")
        return 1
    if password is None or password == "":
        print("result: FAIL")
        print("connect_ok: False")
        print("error_type: ConfigError")
        print("detail: SMTP_PASSWORD missing_or_empty")
        return 1

    try:
        timeout = float(timeout_raw) if timeout_raw else DEFAULT_TIMEOUT
        if timeout <= 0:
            raise ValueError("timeout must be positive")
    except ValueError:
        print("result: FAIL")
        print("connect_ok: False")
        print("error_type: ConfigError")
        print("detail: SMTP_TIMEOUT invalid")
        return 1

    print(f"target: {DIAG_HOST}:{DIAG_PORT} (SMTP_SSL)")
    print(f"env_file_loaded: {ENV_PATH.is_file()}")
    print(f"username_configured: True")
    print(f"password_configured: True")
    print(f"timeout: {timeout}")

    server: smtplib.SMTP_SSL | None = None
    connect_ok = False
    ehlo_code: int | None = None
    auth_declared = False
    auth_mechs: list[str] = []
    login_ok = False
    error_type: str | None = None
    smtp_code: object = None

    try:
        context = ssl.create_default_context()
        # 禁止 debug，避免协议交互落入 stdout
        server = smtplib.SMTP_SSL(
            DIAG_HOST,
            DIAG_PORT,
            timeout=timeout,
            context=context,
        )
        server.set_debuglevel(0)
        connect_ok = True

        # ehlo 返回 (code, message)；只保留响应码，不打印 message
        ehlo_code, _ehlo_msg = server.ehlo()
        auth_raw = server.esmtp_features.get("auth", "")
        if auth_raw:
            auth_declared = True
            # 机制名通常为空格分隔的小写标识，不含凭据
            auth_mechs = [m for m in str(auth_raw).split() if m]

        # 强制 AUTH LOGIN（不使用 AUTH PLAIN / server.login 自动择优）
        server.auth("LOGIN", _make_auth_login_object(username, password))
        login_ok = True
    except (smtplib.SMTPException, OSError, ssl.SSLError, TimeoutError) as exc:
        error_type = type(exc).__name__
        smtp_code = _safe_smtp_code(exc)
    except Exception as exc:  # noqa: BLE001 — 诊断脚本需捕获未知错误类型名
        error_type = type(exc).__name__
        smtp_code = _safe_smtp_code(exc)
    finally:
        _close_smtp(server)

    print(f"connect_ok: {connect_ok}")
    print(f"ehlo_code: {ehlo_code}")
    print(f"auth_declared: {auth_declared}")
    print(f"auth_mechanisms: {','.join(auth_mechs) if auth_mechs else ''}")
    print("auth_method: LOGIN")
    print(f"login_ok: {login_ok}")
    print(f"error_type: {error_type}")
    print(f"smtp_code: {smtp_code}")
    print(f"result: {'OK' if login_ok else 'FAIL'}")

    return 0 if login_ok else 1


if __name__ == "__main__":
    sys.exit(main())
