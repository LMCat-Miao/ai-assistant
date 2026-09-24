from app.database import get_db
from app.services.user_seed import ensure_admin_user


def init_database():
    """
    初始化 / 迁移数据库。

    全部使用 CREATE TABLE IF NOT EXISTS 与条件种子，
    可重复执行，不会删除 conversations / messages。
    """

    db = get_db()

    try:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        db.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (conversation_id)
                    REFERENCES conversations(id)
            )
            """
        )

        # 用户表：支持重复执行，不破坏已有数据
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        db.commit()

        print("✅ 数据库初始化成功")

    finally:
        db.close()

    # 表提交后再做 admin 种子（内部自行开连接）
    try:
        message = ensure_admin_user()
        print(f"✅ 用户迁移：{message}")
    except Exception as exc:
        # 不阻断服务启动，但把问题打出来
        print(f"⚠️ 用户迁移失败：{exc}")
