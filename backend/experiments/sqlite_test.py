from app.database import get_db


db = get_db()


try:

    # ========================================================
    # 1. 创建一个测试会话
    # ========================================================

    cursor = db.execute(
        """
        INSERT INTO conversations (
            user_id,
            title
        )
        VALUES (?, ?)
        """,
        (1, "Vue3学习"),
    )

    conversation_id = cursor.lastrowid

    print(
        "创建会话成功：",
        conversation_id
    )


    # ========================================================
    # 2. 创建一条用户消息
    # ========================================================

    db.execute(
        """
        INSERT INTO messages (
            conversation_id,
            role,
            content
        )
        VALUES (?, ?, ?)
        """,
        (
            conversation_id,
            "user",
            "什么是 Vue3？",
        ),
    )


    # ========================================================
    # 3. 创建一条 AI 消息
    # ========================================================

    db.execute(
        """
        INSERT INTO messages (
            conversation_id,
            role,
            content
        )
        VALUES (?, ?, ?)
        """,
        (
            conversation_id,
            "assistant",
            "Vue3 是 Vue.js 的新一代版本。",
        ),
    )


    db.commit()


    # ========================================================
    # 4. 查询会话
    # ========================================================

    conversation = db.execute(
        """
        SELECT *
        FROM conversations
        WHERE id = ?
        """,
        (conversation_id,),
    ).fetchone()


    print("\n会话：")
    print(dict(conversation))


    # ========================================================
    # 5. 查询这个会话的所有消息
    # ========================================================

    messages = db.execute(
        """
        SELECT *
        FROM messages
        WHERE conversation_id = ?
        ORDER BY created_at ASC, id ASC
        """,
        (conversation_id,),
    ).fetchall()


    print("\n消息：")

    for message in messages:
        print(dict(message))


finally:

    db.close()