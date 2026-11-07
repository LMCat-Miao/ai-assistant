"""
SMTP 邮件发送服务。

仅负责把内容发到邮箱；不生成/存储/校验验证码，不操作 Redis / MySQL。
供上层在 issue_code 之后调用；发送失败由上层决定 cancel_code_issue。
"""

from __future__ import annotations

import logging
import os
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Final

from dotenv import load_dotenv


logger = logging.getLogger(__name__)

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_ENV_PATH = _BACKEND_ROOT / ".env"

# 与验证码产品文案一致（300 秒）；本模块不依赖 Redis Service
_CODE_VALID_MINUTES: Final[int] = 5
_DEFAULT_TIMEOUT: Final[float] = 30.0


class EmailServiceError(Exception):
    """邮件服务异常基类。"""


class EmailSMTPConfigError(EmailServiceError):
    """SMTP 配置缺失或不合法。"""


class EmailSendError(EmailServiceError):
    """SMTP 连接、认证或发送失败。"""


@dataclass(frozen=True)
class SMTPSettings:
    host: str
    port: int
    username: str
    password: str
    from_email: str
    use_ssl: bool
    use_tls: bool
    timeout: float


def _parse_bool(raw: str | None, *, name: str, default: bool = False) -> bool:
    if raw is None or raw.strip() == "":
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise EmailSMTPConfigError(f"{name} 无效，应为 true/false：{raw!r}")


def _load_smtp_settings() -> SMTPSettings:
    """从 backend/.env 读取 SMTP 配置；缺失或不合法时抛 EmailSMTPConfigError。"""

    load_dotenv(_ENV_PATH)

    host = (os.getenv("SMTP_HOST") or "").strip()
    port_raw = (os.getenv("SMTP_PORT") or "").strip()
    username = (os.getenv("SMTP_USERNAME") or "").strip()
    password = os.getenv("SMTP_PASSWORD")
    from_email = (os.getenv("SMTP_FROM_EMAIL") or "").strip()
    use_ssl = _parse_bool(os.getenv("SMTP_USE_SSL"), name="SMTP_USE_SSL", default=False)
    use_tls = _parse_bool(os.getenv("SMTP_USE_TLS"), name="SMTP_USE_TLS", default=False)
    timeout_raw = (os.getenv("SMTP_TIMEOUT") or "").strip()

    if not host:
        raise EmailSMTPConfigError("缺少环境变量 SMTP_HOST")
    if not port_raw:
        raise EmailSMTPConfigError("缺少环境变量 SMTP_PORT")
    if not username:
        raise EmailSMTPConfigError("缺少环境变量 SMTP_USERNAME")
    if password is None or password == "":
        raise EmailSMTPConfigError("缺少环境变量 SMTP_PASSWORD")
    if not from_email:
        raise EmailSMTPConfigError("缺少环境变量 SMTP_FROM_EMAIL")

    try:
        port = int(port_raw)
    except ValueError as exc:
        raise EmailSMTPConfigError(f"SMTP_PORT 无效：{port_raw!r}") from exc
    if port < 1 or port > 65535:
        raise EmailSMTPConfigError(f"SMTP_PORT 超出范围：{port}")

    if use_ssl and use_tls:
        raise EmailSMTPConfigError(
            "SMTP_USE_SSL 与 SMTP_USE_TLS 不能同时为 true；"
            "请二选一（465 常用 SSL，587 常用 STARTTLS）"
        )
    if not use_ssl and not use_tls:
        raise EmailSMTPConfigError(
            "必须启用 SMTP_USE_SSL 或 SMTP_USE_TLS 之一（禁止明文 SMTP）"
        )

    if timeout_raw:
        try:
            timeout = float(timeout_raw)
        except ValueError as exc:
            raise EmailSMTPConfigError(f"SMTP_TIMEOUT 无效：{timeout_raw!r}") from exc
    else:
        timeout = _DEFAULT_TIMEOUT
    if timeout <= 0:
        raise EmailSMTPConfigError("SMTP_TIMEOUT 必须为正数")

    return SMTPSettings(
        host=host,
        port=port,
        username=username,
        password=password,
        from_email=from_email,
        use_ssl=use_ssl,
        use_tls=use_tls,
        timeout=timeout,
    )


def _build_register_code_message(
    *,
    to_email: str,
    code: str,
    from_email: str,
) -> EmailMessage:
    """构建 UTF-8 注册验证码邮件（主题与正文含中文）。"""

    message = EmailMessage()
    message["Subject"] = "【AI 学习助手】注册验证码"
    message["From"] = from_email
    message["To"] = to_email
    message.set_content(
        (
            "您好，\n\n"
            f"您正在注册 AI 学习助手账号，验证码为：{code}\n\n"
            f"验证码有效期为 {_CODE_VALID_MINUTES} 分钟，请勿向他人泄露验证码。\n"
            "如果不是本人操作，请忽略本邮件。\n\n"
            "— AI 学习助手\n"
        ),
        charset="utf-8",
    )
    return message


def send_register_code_email(to_email: str, code: str) -> None:
    """
    向指定邮箱发送注册验证码。

    成功返回 None；配置问题抛 EmailSMTPConfigError；
    连接/登录/发送失败抛 EmailSendError（不自动重试）。
    不在日志中记录验证码或 SMTP 密码。
    """

    recipient = (to_email or "").strip().lower()
    plain_code = (code or "").strip()
    if not recipient:
        raise ValueError("to_email 不能为空")
    if not plain_code:
        raise ValueError("code 不能为空")

    settings = _load_smtp_settings()
    message = _build_register_code_message(
        to_email=recipient,
        code=plain_code,
        from_email=settings.from_email,
    )

    server: smtplib.SMTP | smtplib.SMTP_SSL | None = None
    stage = "connect"
    primary_failed = False
    try:
        if settings.use_ssl:
            context = ssl.create_default_context()
            server = smtplib.SMTP_SSL(
                settings.host,
                settings.port,
                timeout=settings.timeout,
                context=context,
            )
        else:
            server = smtplib.SMTP(
                settings.host,
                settings.port,
                timeout=settings.timeout,
            )
            # STARTTLS：先明文握手再升级
            server.ehlo()
            context = ssl.create_default_context()
            server.starttls(context=context)
            server.ehlo()

        stage = "login"
        server.login(settings.username, settings.password)
        stage = "send"
        server.send_message(message)
    except EmailSMTPConfigError:
        raise
    except (smtplib.SMTPException, OSError, ssl.SSLError, TimeoutError) as exc:
        primary_failed = True
        smtp_code = getattr(exc, "smtp_code", None)
        logger.error(
            "发送注册验证码邮件失败：to=%s stage=%s error_type=%s smtp_code=%s",
            recipient,
            stage,
            type(exc).__name__,
            smtp_code,
        )
        raise EmailSendError(
            f"发送注册验证码邮件失败（{type(exc).__name__}）"
        ) from exc
    finally:
        if server is not None:
            stage = "quit"
            try:
                server.quit()
            except Exception as close_exc:  # noqa: BLE001 — 关闭失败不掩盖发送结果
                close_smtp_code = getattr(close_exc, "smtp_code", None)
                if primary_failed:
                    logger.warning(
                        "关闭 SMTP 连接时出错（清理阶段，已忽略）："
                        "to=%s stage=%s error_type=%s smtp_code=%s",
                        recipient,
                        stage,
                        type(close_exc).__name__,
                        close_smtp_code,
                    )
                else:
                    logger.warning(
                        "关闭 SMTP 连接时出错（已忽略）："
                        "to=%s stage=%s error_type=%s smtp_code=%s",
                        recipient,
                        stage,
                        type(close_exc).__name__,
                        close_smtp_code,
                    )

    logger.info("注册验证码邮件已发送：to=%s", recipient)
