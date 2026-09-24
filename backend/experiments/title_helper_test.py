"""验证会话标题截断与默认标题判断。"""
from app.services.chat_service import (
    DEFAULT_CONVERSATION_TITLE,
    build_title_from_message,
    is_default_title,
)


def main() -> int:
    cases: list[tuple[str, bool, str]] = []

    cases.append(
        (
            "empty",
            build_title_from_message("   \n  ") is None,
            "expected None",
        )
    )
    cases.append(
        (
            "short",
            build_title_from_message("  你好世界  ") == "你好世界",
            str(build_title_from_message("  你好世界  ")),
        )
    )
    long = "请解释一下" + ("闭包" * 40)
    title = build_title_from_message(long)
    cases.append(
        (
            "long_truncated",
            title is not None
            and title.endswith("…")
            and len(title) == 31,  # 30 chars + …
            str(title),
        )
    )
    cases.append(
        (
            "default_title",
            is_default_title(DEFAULT_CONVERSATION_TITLE)
            and is_default_title("")
            and is_default_title("  ")
            and not is_default_title("已有标题"),
            "ok",
        )
    )

    print("=== title helper tests ===")
    failed = 0
    for name, passed, detail in cases:
        status = "PASS" if passed else "FAIL"
        if not passed:
            failed += 1
        print(f"[{status}] {name} | {detail}")

    print(f"summary: {len(cases) - failed}/{len(cases)} passed")
    return failed


if __name__ == "__main__":
    raise SystemExit(main())
