"""
业务库连接层（MySQL 8.4 + SQLAlchemy 2.x Core + PyMySQL）。

业务数据库已切换到 MySQL；本模块通过 SQLAlchemy 2.x Core 管理
Engine / Connection 生命周期，PyMySQL 作为 MySQL 驱动。
不执行建表或数据迁移。

生产代码请使用 get_engine() / get_connection()；
不要调用已废弃的 get_db()（会主动抛出 RuntimeError）。
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Connection, Engine, URL


# backend/ 根目录（用于定位 .env，不依赖进程 cwd）
BASE_DIR = Path(__file__).resolve().parent.parent
_ENV_PATH = BASE_DIR / ".env"

# 进程内单例 Engine；首次 get_engine() 时创建
_engine: Engine | None = None


def _load_mysql_settings() -> dict[str, str | int]:
    """从 backend/.env 读取 MySQL 配置（不打印密码）。"""

    load_dotenv(_ENV_PATH)

    host = os.getenv("MYSQL_HOST", "127.0.0.1")
    port_raw = os.getenv("MYSQL_PORT", "3307")
    user = os.getenv("MYSQL_USER")
    password = os.getenv("MYSQL_PASSWORD")
    database = os.getenv("MYSQL_DATABASE", "ai_assistant")

    if not user:
        raise ValueError("缺少环境变量 MYSQL_USER，请检查 backend/.env")
    if password is None or password == "":
        raise ValueError("缺少环境变量 MYSQL_PASSWORD，请检查 backend/.env")

    try:
        port = int(port_raw)
    except ValueError as exc:
        raise ValueError(f"MYSQL_PORT 无效：{port_raw!r}") from exc

    return {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "database": database,
    }


def _build_database_url() -> URL:
    """使用 URL.create 构建连接串，避免密码特殊字符破坏 URL。"""

    settings = _load_mysql_settings()
    return URL.create(
        drivername="mysql+pymysql",
        username=str(settings["user"]),
        password=str(settings["password"]),
        host=str(settings["host"]),
        port=int(settings["port"]),
        database=str(settings["database"]),
        query={"charset": "utf8mb4"},
    )


def get_engine() -> Engine:
    """
    获取全局 SQLAlchemy Engine（懒加载单例）。

    Engine 管理连接池；不要在每次请求里 create_engine。
    创建 Engine 本身不会执行破坏性 DDL/DML。
    """

    global _engine
    if _engine is not None:
        return _engine

    _engine = create_engine(
        _build_database_url(),
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        pool_recycle=3600,
        echo=False,
    )
    return _engine


@contextmanager
def get_connection() -> Iterator[Connection]:
    """
    从连接池借出一条 SQLAlchemy Connection，并在退出 with 时归还。

    用法：
        with get_connection() as conn:
            conn.execute(text("SELECT 1"), {})
            conn.commit()   # 写操作需显式提交（SQLAlchemy 2 默认不自动 commit）

    注意：不会在退出时自动 commit；异常时也不会替你 rollback 写事务。
    需要事务时优先使用 get_engine().begin()。
    """

    connection = get_engine().connect()
    try:
        yield connection
    finally:
        connection.close()


def dispose_engine() -> None:
    """释放 Engine 与连接池（应用关闭时可选调用）。"""

    global _engine
    if _engine is not None:
        _engine.dispose()
        _engine = None


def get_db():
    """
    已废弃：旧 SQLite（sqlite3）访问入口的兼容性保护桩。

    - 生产 Repository / 业务代码统一使用 get_connection()（或 get_engine()）。
    - 新代码不要再调用本函数。
    - 调用时主动抛出 RuntimeError，避免误用旧 SQLite 连接方式。
    """

    raise RuntimeError(
        "get_db() 已移除 SQLite 实现。业务库请使用 "
        "app.database.get_engine() 或 get_connection()，"
        "并同步将 Repository 改为 SQLAlchemy Core（text + 命名参数）。"
    )
