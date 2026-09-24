"""
密码哈希与校验（bcrypt）。

仅保存哈希到数据库，不存储明文密码。
"""

from __future__ import annotations

import bcrypt


def hash_password(plain_password: str) -> str:
    """
    将明文密码转为 bcrypt 哈希字符串（UTF-8）。
    """

    password_bytes = plain_password.encode("utf-8")
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    """
    校验明文密码是否与库中哈希匹配。
    哈希格式非法时返回 False，不向外抛出细节。
    """

    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            password_hash.encode("utf-8"),
        )
    except (ValueError, TypeError):
        return False
