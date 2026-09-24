import sqlite3
from pathlib import Path


# backend/
BASE_DIR = Path(__file__).resolve().parent.parent

# backend/database/ai_assistant.db
DATABASE_PATH = BASE_DIR / "database" / "ai_assistant.db"


def get_db():
    # 确保 database 目录存在（首次启动 / 临时测试库父目录）
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(DATABASE_PATH)

    # 查询结果可以通过字段名访问
    connection.row_factory = sqlite3.Row

    return connection
