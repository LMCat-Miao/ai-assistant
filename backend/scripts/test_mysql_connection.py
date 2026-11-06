import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL


# 1. 加载 backend/.env 中的环境变量
load_dotenv()


# 2. 读取 MySQL 配置
mysql_host = os.getenv("MYSQL_HOST", "127.0.0.1")
mysql_port = int(os.getenv("MYSQL_PORT", "3307"))
mysql_user = os.getenv("MYSQL_USER")
mysql_password = os.getenv("MYSQL_PASSWORD")
mysql_database = os.getenv("MYSQL_DATABASE", "ai_assistant")


# 3. 检查必要配置
if not mysql_user or not mysql_password:
    raise ValueError("请检查 .env 中的 MYSQL_USER 和 MYSQL_PASSWORD")


# 4. 创建数据库连接 URL
# URL.create 可以正确处理密码中的特殊字符
database_url = URL.create(
    drivername="mysql+pymysql",
    username=mysql_user,
    password=mysql_password,
    host=mysql_host,
    port=mysql_port,
    database=mysql_database,
    query={"charset": "utf8mb4"},
)


# 5. 创建 SQLAlchemy Engine
engine = create_engine(
    database_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    echo=True,
)


# 6. 测试数据库连接
try:
    with engine.connect() as connection:

        # 查询 MySQL 版本
        version = connection.execute(
            text("SELECT VERSION()")
        ).scalar_one()

        # 查询当前数据库
        database = connection.execute(
            text("SELECT DATABASE()")
        ).scalar_one()

        # 查询当前端口
        port = connection.execute(
            text("SELECT @@port")
        ).scalar_one()

        print("\n========== MySQL 连接成功 ==========")
        print(f"MySQL 版本：{version}")
        print(f"当前数据库：{database}")
        print(f"连接端口：{port}")
        print("====================================")

except Exception as error:
    print("MySQL 连接失败！")
    print(f"错误信息：{error}")

finally:
    engine.dispose()