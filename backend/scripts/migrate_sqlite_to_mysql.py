"""
SQLite → MySQL 历史数据迁移脚本（独立、可重复安全检查）。

特点：
- 只读打开 SQLite，不修改源库与 Chroma
- 通过 .env 连接 MySQL（不打印密码）
- 单事务写入；任一步失败整批回滚
- 目标表非空则拒绝执行，防止重复迁移
- 显式保留原始主键 id（兼容 Chroma metadata.user_id）

用法（在 backend 目录、已激活 venv，且尚未写入业务数据时）：

  python -m scripts.migrate_sqlite_to_mysql

注意：本脚本不会修改 app 业务代码；迁移成功后需另行切换应用数据源。
"""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine, URL


# backend/ 根目录（不依赖进程 cwd）
BACKEND_ROOT = Path(__file__).resolve().parents[1]
SQLITE_PATH = BACKEND_ROOT / "database" / "ai_assistant.db"
ENV_PATH = BACKEND_ROOT / ".env"

TARGET_TABLES = ("users", "conversations", "messages")


def get_sqlite_connection() -> sqlite3.Connection:
    """以只读 URI 打开 SQLite，避免误写源库。"""

    if not SQLITE_PATH.is_file():
        raise FileNotFoundError(f"找不到 SQLite 数据库：{SQLITE_PATH}")

    uri = f"file:{SQLITE_PATH.resolve().as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def get_mysql_engine() -> Engine:
    """从 backend/.env 读取配置，创建 SQLAlchemy Engine（仅 Core，不用 ORM）。"""

    load_dotenv(ENV_PATH)

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

    # URL.create 可正确处理密码中的特殊字符；绝不 print password
    database_url = URL.create(
        drivername="mysql+pymysql",
        username=user,
        password=password,
        host=host,
        port=port,
        database=database,
        query={"charset": "utf8mb4"},
    )

    return create_engine(
        database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        echo=False,
    )


def check_mysql_empty(connection: Connection) -> None:
    """目标三表必须全部为空，否则拒绝迁移。"""

    non_empty: list[str] = []
    for table in TARGET_TABLES:
        count = connection.execute(
            text(f"SELECT COUNT(*) AS c FROM `{table}`")
        ).scalar_one()
        if int(count) > 0:
            non_empty.append(f"{table}={count}")

    if non_empty:
        raise RuntimeError(
            "MySQL 目标表非空，拒绝迁移以防覆盖或重复导入："
            + ", ".join(non_empty)
            + "。请确认使用空库，或人工处理后再试（本脚本不会 TRUNCATE/DROP）。"
        )


def _fetch_all_dicts(sqlite_conn: sqlite3.Connection, sql: str) -> list[dict[str, Any]]:
    rows = sqlite_conn.execute(sql).fetchall()
    return [dict(row) for row in rows]


def migrate_users(
    sqlite_conn: sqlite3.Connection,
    connection: Connection,
) -> int:
    """迁移 users：显式写入原 id；MySQL 多出的 email 列置为 NULL。"""

    rows = _fetch_all_dicts(
        sqlite_conn,
        """
        SELECT id, username, password_hash, created_at
        FROM users
        ORDER BY id
        """,
    )

    insert_sql = text(
        """
        INSERT INTO users (id, username, email, password_hash, created_at)
        VALUES (:id, :username, :email, :password_hash, :created_at)
        """
    )

    for row in rows:
        connection.execute(
            insert_sql,
            {
                "id": row["id"],
                "username": row["username"],
                "email": None,
                "password_hash": row["password_hash"],
                "created_at": row["created_at"],
            },
        )

    return len(rows)


def migrate_conversations(
    sqlite_conn: sqlite3.Connection,
    connection: Connection,
) -> int:
    """迁移 conversations：保留原 id / user_id / 中文 title / 时间戳。"""

    rows = _fetch_all_dicts(
        sqlite_conn,
        """
        SELECT id, user_id, title, created_at, updated_at
        FROM conversations
        ORDER BY id
        """,
    )

    insert_sql = text(
        """
        INSERT INTO conversations (
            id, user_id, title, created_at, updated_at
        )
        VALUES (
            :id, :user_id, :title, :created_at, :updated_at
        )
        """
    )

    for row in rows:
        connection.execute(
            insert_sql,
            {
                "id": row["id"],
                "user_id": row["user_id"],
                "title": row["title"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            },
        )

    return len(rows)


def migrate_messages(
    sqlite_conn: sqlite3.Connection,
    connection: Connection,
) -> int:
    """迁移 messages：保留 citations_json 的 NULL 与原文。"""

    rows = _fetch_all_dicts(
        sqlite_conn,
        """
        SELECT
            id,
            conversation_id,
            role,
            content,
            created_at,
            citations_json
        FROM messages
        ORDER BY id
        """,
    )

    insert_sql = text(
        """
        INSERT INTO messages (
            id,
            conversation_id,
            role,
            content,
            created_at,
            citations_json
        )
        VALUES (
            :id,
            :conversation_id,
            :role,
            :content,
            :created_at,
            :citations_json
        )
        """
    )

    for row in rows:
        connection.execute(
            insert_sql,
            {
                "id": row["id"],
                "conversation_id": row["conversation_id"],
                "role": row["role"],
                "content": row["content"],
                "created_at": row["created_at"],
                "citations_json": row["citations_json"],
            },
        )

    return len(rows)


def _sqlite_sequence_map(sqlite_conn: sqlite3.Connection) -> dict[str, int]:
    """读取 sqlite_sequence；某表缺失时不出现在结果中。"""

    try:
        rows = sqlite_conn.execute(
            "SELECT name, seq FROM sqlite_sequence"
        ).fetchall()
    except sqlite3.Error:
        return {}
    return {str(name): int(seq) for name, seq in rows}


def reset_auto_increment(
    sqlite_conn: sqlite3.Connection,
    connection: Connection,
) -> dict[str, int]:
    """
    将 AUTO_INCREMENT 设为 max(sqlite_sequence.seq + 1, max(id) + 1)。

    sqlite_sequence.seq 为历史已使用的最大自增 ID，下一可用值应为 seq+1。
    仅对 TARGET_TABLES 白名单表执行；应在数据迁移事务成功提交之后单独调用。
    """

    seq_map = _sqlite_sequence_map(sqlite_conn)
    applied: dict[str, int] = {}

    for table in TARGET_TABLES:
        max_id = connection.execute(
            text(f"SELECT COALESCE(MAX(id), 0) FROM `{table}`")
        ).scalar_one()
        max_id = int(max_id)
        seq_val = int(seq_map.get(table, 0))
        next_ai = max(seq_val + 1, max_id + 1)
        # MySQL：ALTER TABLE ... AUTO_INCREMENT = N（会隐式提交，勿放在数据事务内）
        connection.execute(
            text(f"ALTER TABLE `{table}` AUTO_INCREMENT = {next_ai}")
        )
        applied[table] = next_ai

    return applied


def _mysql_rows(
    connection: Connection,
    sql: str,
) -> list[dict[str, Any]]:
    result = connection.execute(text(sql))
    return [dict(row._mapping) for row in result]


def _norm_ts(value: Any) -> str | None:
    """统一时间比较：datetime / 字符串都转成可比较的文本。"""

    if value is None:
        return None
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    text_value = str(value).strip()
    # 去掉可能的微秒后缀，便于与 SQLite 秒级时间对齐
    if "." in text_value:
        text_value = text_value.split(".", 1)[0]
    return text_value


def _norm_text(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def verify_migration(
    sqlite_conn: sqlite3.Connection,
    connection: Connection,
) -> None:
    """逐表比对数量、主键集合与关键字段；失败则抛错以触发事务回滚。"""

    # ----- 数量 -----
    counts: dict[str, tuple[int, int]] = {}
    for table in TARGET_TABLES:
        sqlite_count = sqlite_conn.execute(
            f"SELECT COUNT(*) FROM {table}"
        ).fetchone()[0]
        mysql_count = connection.execute(
            text(f"SELECT COUNT(*) AS c FROM `{table}`")
        ).scalar_one()
        counts[table] = (int(sqlite_count), int(mysql_count))
        print(f"[校验] {table}: SQLite={sqlite_count}, MySQL={mysql_count}")
        if int(sqlite_count) != int(mysql_count):
            raise RuntimeError(
                f"{table} 数量不一致：SQLite={sqlite_count}, MySQL={mysql_count}"
            )

    # ----- users：id + username（不打印 password_hash）-----
    sqlite_users = _fetch_all_dicts(
        sqlite_conn,
        "SELECT id, username, created_at FROM users ORDER BY id",
    )
    mysql_users = _mysql_rows(
        connection,
        "SELECT id, username, created_at FROM users ORDER BY id",
    )
    if [u["id"] for u in sqlite_users] != [u["id"] for u in mysql_users]:
        raise RuntimeError("users.id 集合或顺序不一致")
    for s_row, m_row in zip(sqlite_users, mysql_users):
        if s_row["username"] != m_row["username"]:
            raise RuntimeError(
                f"users.username 不一致 id={s_row['id']}: "
                f"SQLite={s_row['username']!r}, MySQL={m_row['username']!r}"
            )
        if _norm_ts(s_row["created_at"]) != _norm_ts(m_row["created_at"]):
            raise RuntimeError(
                f"users.created_at 不一致 id={s_row['id']}"
            )

    # 密码哈希一致性（静默比较，不输出哈希内容）
    sqlite_hashes = {
        int(r["id"]): r["password_hash"]
        for r in _fetch_all_dicts(
            sqlite_conn, "SELECT id, password_hash FROM users"
        )
    }
    mysql_hashes = {
        int(r["id"]): r["password_hash"]
        for r in _mysql_rows(
            connection, "SELECT id, password_hash FROM users"
        )
    }
    if sqlite_hashes != mysql_hashes:
        raise RuntimeError("users.password_hash 与源库不一致（内容未打印）")

    print("[校验] users.id / username / created_at / password_hash：通过")

    # ----- conversations：id、user_id、中文 title、时间 -----
    sqlite_convs = _fetch_all_dicts(
        sqlite_conn,
        """
        SELECT id, user_id, title, created_at, updated_at
        FROM conversations
        ORDER BY id
        """,
    )
    mysql_convs = _mysql_rows(
        connection,
        """
        SELECT id, user_id, title, created_at, updated_at
        FROM conversations
        ORDER BY id
        """,
    )
    if [r["id"] for r in sqlite_convs] != [r["id"] for r in mysql_convs]:
        raise RuntimeError("conversations.id 集合或顺序不一致")
    for s_row, m_row in zip(sqlite_convs, mysql_convs):
        if int(s_row["user_id"]) != int(m_row["user_id"]):
            raise RuntimeError(
                f"conversations.user_id 不一致 id={s_row['id']}"
            )
        if s_row["title"] != m_row["title"]:
            raise RuntimeError(
                f"conversations.title 不一致 id={s_row['id']} "
                f"(含中文标题校验失败)"
            )
        if _norm_ts(s_row["created_at"]) != _norm_ts(m_row["created_at"]):
            raise RuntimeError(
                f"conversations.created_at 不一致 id={s_row['id']}"
            )
        if _norm_ts(s_row["updated_at"]) != _norm_ts(m_row["updated_at"]):
            raise RuntimeError(
                f"conversations.updated_at 不一致 id={s_row['id']}"
            )

    print("[校验] conversations.id / user_id / title / 时间：通过")

    # ----- messages：id、FK、role、content、citations_json -----
    sqlite_msgs = _fetch_all_dicts(
        sqlite_conn,
        """
        SELECT
            id,
            conversation_id,
            role,
            content,
            created_at,
            citations_json
        FROM messages
        ORDER BY id
        """,
    )
    mysql_msgs = _mysql_rows(
        connection,
        """
        SELECT
            id,
            conversation_id,
            role,
            content,
            created_at,
            citations_json
        FROM messages
        ORDER BY id
        """,
    )
    if [r["id"] for r in sqlite_msgs] != [r["id"] for r in mysql_msgs]:
        raise RuntimeError("messages.id 集合或顺序不一致")
    for s_row, m_row in zip(sqlite_msgs, mysql_msgs):
        if int(s_row["conversation_id"]) != int(m_row["conversation_id"]):
            raise RuntimeError(
                f"messages.conversation_id 不一致 id={s_row['id']}"
            )
        if s_row["role"] != m_row["role"]:
            raise RuntimeError(f"messages.role 不一致 id={s_row['id']}")
        if s_row["content"] != m_row["content"]:
            raise RuntimeError(
                f"messages.content 不一致 id={s_row['id']}"
            )
        if _norm_ts(s_row["created_at"]) != _norm_ts(m_row["created_at"]):
            raise RuntimeError(
                f"messages.created_at 不一致 id={s_row['id']}"
            )
        if _norm_text(s_row["citations_json"]) != _norm_text(
            m_row["citations_json"]
        ):
            raise RuntimeError(
                f"messages.citations_json 不一致 id={s_row['id']}"
            )

    print("[校验] messages.id / 内容 / citations_json：通过")

    # ----- 外键孤立检查（MySQL 侧）-----
    orphan_convs = connection.execute(
        text(
            """
            SELECT COUNT(*) AS c
            FROM conversations c
            LEFT JOIN users u ON u.id = c.user_id
            WHERE u.id IS NULL
            """
        )
    ).scalar_one()
    if int(orphan_convs) != 0:
        raise RuntimeError(
            f"存在孤立 conversations.user_id：{orphan_convs} 条"
        )

    orphan_msgs = connection.execute(
        text(
            """
            SELECT COUNT(*) AS c
            FROM messages m
            LEFT JOIN conversations c ON c.id = m.conversation_id
            WHERE c.id IS NULL
            """
        )
    ).scalar_one()
    if int(orphan_msgs) != 0:
        raise RuntimeError(
            f"存在孤立 messages.conversation_id：{orphan_msgs} 条"
        )

    print("[校验] 外键孤立记录：无")
    print(
        "[校验] 汇总通过：",
        ", ".join(f"{t}={counts[t][0]}" for t in TARGET_TABLES),
    )


def main() -> int:
    """迁移入口：事务内迁移+校验；成功提交后再单独调整 AUTO_INCREMENT。"""

    print("========== SQLite → MySQL 数据迁移 ==========")
    print(f"SQLite：{SQLITE_PATH}")
    print(f"ENV   ：{ENV_PATH}")
    print("MySQL ：从环境变量读取（不打印密码）")

    sqlite_conn: sqlite3.Connection | None = None
    engine: Engine | None = None

    try:
        sqlite_conn = get_sqlite_connection()
        engine = get_mysql_engine()

        # 第一阶段：数据迁移事务（不含 ALTER TABLE）
        try:
            with engine.begin() as connection:
                print("[步骤] 检查 MySQL 目标表是否为空…")
                check_mysql_empty(connection)

                print("[步骤] 迁移 users…")
                n_users = migrate_users(sqlite_conn, connection)
                print(f"  已插入 users：{n_users}")

                print("[步骤] 迁移 conversations…")
                n_convs = migrate_conversations(sqlite_conn, connection)
                print(f"  已插入 conversations：{n_convs}")

                print("[步骤] 迁移 messages…")
                n_msgs = migrate_messages(sqlite_conn, connection)
                print(f"  已插入 messages：{n_msgs}")

                print("[步骤] 校验迁移结果…")
                verify_migration(sqlite_conn, connection)
        except Exception as exc:
            print("========== 数据迁移失败（数据事务已回滚）==========")
            print(f"错误类型：{type(exc).__name__}")
            print(f"错误信息：{exc}")
            print(
                "处理建议：检查上方错误；确认 MySQL 三表仍为空后可再次运行。"
                "未执行 AUTO_INCREMENT 调整。"
                "SQLite 与 Chroma 未被本脚本修改。"
            )
            return 1

        print("========== 数据迁移与校验已成功提交 ==========")

        # 第二阶段：自增序列调整（ALTER 会隐式提交，必须在数据事务之外）
        try:
            print("[步骤] 调整 AUTO_INCREMENT…")
            with engine.connect() as connection:
                ai_map = reset_auto_increment(sqlite_conn, connection)
                connection.commit()
            for table, value in ai_map.items():
                print(f"  {table}.AUTO_INCREMENT = {value}")
        except Exception as exc:
            print("========== AUTO_INCREMENT 调整失败 ==========")
            print(
                "说明：数据迁移与数据校验已经成功提交，"
                "本次失败不表示数据事务已回滚。"
            )
            print(f"错误类型：{type(exc).__name__}")
            print(f"错误信息：{exc}")
            print(
                "处理建议：数据已在 MySQL 中，请单独重试 AUTO_INCREMENT 调整，"
                "或手工执行 ALTER TABLE ... AUTO_INCREMENT = ...；"
                "不要再次全量迁移（目标表已非空）。"
            )
            return 1

        print("========== 迁移全部完成 ==========")
        return 0

    finally:
        if sqlite_conn is not None:
            sqlite_conn.close()
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
