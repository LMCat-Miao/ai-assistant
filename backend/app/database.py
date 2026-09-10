import sqlite3
from pathlib import Path


# backend/
BASE_DIR = Path(__file__).resolve().parent.parent

# backend/database/ai_assistant.db
DATABASE_PATH = BASE_DIR / "database" / "ai_assistant.db"


def get_db():
    connection = sqlite3.connect(DATABASE_PATH)

    # 查询结果可以通过字段名访问
    connection.row_factory = sqlite3.Row

    return connection