"""
一次性种子脚本：创建 test_user（默认同 id=2）。

用法（在 backend 目录、已激活 venv）：

  # 方式 1：环境变量（推荐自动化 / CI）
  set TEST_USER_PASSWORD=你的密码
  python -m scripts.seed_test_user

  # 方式 2：交互输入（密码不会写入仓库）
  python -m scripts.seed_test_user

若用户名已存在：安全跳过，不覆盖密码。
"""

from __future__ import annotations

import getpass
import os
import sys

from app.core.password import hash_password
from app.database_init import init_database
from app.repositories.user_repository import create_user, get_user_by_username


TEST_USERNAME = "test_user"
TEST_USER_ID = 2


def main() -> int:
    # 确保 users 表与 admin 迁移已完成（不删业务数据）
    init_database()

    existing = get_user_by_username(TEST_USERNAME)
    if existing is not None:
        print(
            f"用户「{TEST_USERNAME}」已存在（id={existing['id']}），"
            "跳过创建，不覆盖密码。"
        )
        return 0

    password = os.environ.get("TEST_USER_PASSWORD", "").strip()
    if not password:
        password = getpass.getpass(f"请输入 {TEST_USERNAME} 的密码（不回显）: ")
        confirm = getpass.getpass("请再输入一次确认: ")
        if password != confirm:
            print("两次密码不一致，已取消。")
            return 1

    if not password:
        print("密码不能为空。")
        return 1

    # 若 id=2 已被占用，则改用自增 id
    from app.repositories.user_repository import get_user_by_id

    preferred_id: int | None = TEST_USER_ID
    if get_user_by_id(TEST_USER_ID) is not None:
        print(
            f"注意：id={TEST_USER_ID} 已被占用，将使用自增 ID 创建 {TEST_USERNAME}。"
        )
        preferred_id = None

    user_id = create_user(
        username=TEST_USERNAME,
        password_hash=hash_password(password),
        user_id=preferred_id,
    )

    print(f"已创建用户 {TEST_USERNAME}（id={user_id}）。")
    print("请妥善保存密码；密码哈希已写入数据库，明文不会存库。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
