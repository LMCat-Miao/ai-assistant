
import sqlite3
from pathlib import Path


# 使用刚刚备份的数据库进行检查，不操作原始数据库
BASE_DIR = Path(__file__).resolve().parents[1]
DB_PATH = BASE_DIR / "backups" / "ai_assistant_before_mysql_20261106.db"


def inspect_orphans():
    """检查数据库中的孤立会话和孤立消息"""

    if not DB_PATH.exists():
        raise FileNotFoundError(f"数据库备份不存在：{DB_PATH}")

    # 连接 SQLite 数据库
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row

    try:
        cursor = connection.cursor()

        # 1. 查找没有对应用户的会话
        cursor.execute("""
            SELECT
                c.id,
                c.user_id,
                c.title,
                c.created_at
            FROM conversations AS c
            LEFT JOIN users AS u ON c.user_id = u.id
            WHERE u.id IS NULL
            ORDER BY c.id
        """)

        orphan_conversations = cursor.fetchall()

        print("\n========== 孤立会话 ==========")
        print(f"数量：{len(orphan_conversations)}")

        for row in orphan_conversations:
            print(
                f"conversation_id={row['id']}, "
                f"user_id={row['user_id']}, "
                f"title={row['title']}"
            )

        # 2. 查找没有对应会话的消息
        cursor.execute("""
            SELECT
                m.id,
                m.conversation_id,
                m.role,
                m.created_at
            FROM messages AS m
            LEFT JOIN conversations AS c
                ON m.conversation_id = c.id
            WHERE c.id IS NULL
            ORDER BY m.id
        """)

        orphan_messages = cursor.fetchall()

        print("\n========== 孤立消息 ==========")
        print(f"数量：{len(orphan_messages)}")

        for row in orphan_messages:
            print(
                f"message_id={row['id']}, "
                f"conversation_id={row['conversation_id']}, "
                f"role={row['role']}"
            )

        # 3. 检查 SQLite 已声明的外键约束是否存在违规
        cursor.execute("PRAGMA foreign_key_check")
        foreign_key_errors = cursor.fetchall()

        print("\n========== 外键检查 ==========")
        print(f"违规数量：{len(foreign_key_errors)}")

        for row in foreign_key_errors:
            print(dict(row))

        print("\n========== 检查完成 ==========")

    finally:
        connection.close()


if __name__ == "__main__":
    inspect_orphans()
