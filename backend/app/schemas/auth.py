"""
认证相关请求模型（注册 / 发码）。

登录请求模型仍定义在 app.api.auth，本文件不改动登录契约。
"""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field, field_validator


def _normalize_email(value: object) -> object:
    """strip + lower；非字符串原样返回，交给 EmailStr 校验。"""

    if isinstance(value, str):
        return value.strip().lower()
    return value


class SendRegisterCodeRequest(BaseModel):
    """发送注册邮箱验证码。"""

    email: EmailStr

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        return _normalize_email(value)


class RegisterRequest(BaseModel):
    """邮箱验证码注册。"""

    email: EmailStr
    # 保持字符串，避免 int 丢掉前导 0（如 "012345"）
    code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")
    username: str = Field(..., min_length=1, max_length=64)
    # bcrypt 传统上限约 72 字节；注册侧限制字符长度并校验 UTF-8 字节数
    password: str = Field(..., min_length=8, max_length=72)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        return _normalize_email(value)

    @field_validator("username", mode="before")
    @classmethod
    def strip_username(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("username")
    @classmethod
    def username_not_blank(cls, value: str) -> str:
        if not value:
            raise ValueError("username 不能为空")
        if len(value) > 64:
            raise ValueError("username 长度不能超过 64")
        return value

    @field_validator("password")
    @classmethod
    def password_bcrypt_byte_limit(cls, value: str) -> str:
        """
        与 app.core.password.hash_password 兼容：
        bcrypt 按字节处理口令；超长在部分环境下会截断或失败，注册阶段直接拒绝。
        """

        if len(value.encode("utf-8")) > 72:
            raise ValueError("密码过长（UTF-8 编码后不能超过 72 字节）")
        return value
