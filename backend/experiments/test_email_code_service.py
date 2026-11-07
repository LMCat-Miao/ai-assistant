"""
第二阶段：email_code_service 实验脚本（不发真实邮件、不 FLUSHDB）。

仅操作 ai_assistant:register:* 下本脚本专用测试邮箱 Key。
"""

from __future__ import annotations

import os
import sys
import threading
import time
import traceback
import uuid
from pathlib import Path
from unittest.mock import patch

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# 测试专用 HMAC，不读取、不打印真实 .env 密钥
os.environ["EMAIL_CODE_HMAC_SECRET"] = "phase2-test-hmac-secret-key-32chars-min!"

from redis.exceptions import RedisError

from app.redis_client import close_redis, get_redis, init_redis
from app.services.email_code_service import (
    CODE_TTL_SECONDS,
    CooldownActiveError,
    RedisUnavailableError,
    VerifyStatus,
    cancel_code_issue,
    generate_code,
    issue_code,
    normalize_email,
    verify_and_consume_code,
)


TEST_EMAIL_A = f"phase2.code.{uuid.uuid4().hex[:10]}@example.com"
TEST_EMAIL_B = f"phase2.other.{uuid.uuid4().hex[:10]}@example.com"


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_case(name: str, fn) -> tuple[str, bool, str]:
    try:
        fn()
        return name, True, "ok"
    except Exception as exc:
        return name, False, f"{exc}\n{traceback.format_exc()}"


def _cleanup_email(email: str) -> None:
    client = get_redis()
    if client is None:
        return
    email_n = normalize_email(email)
    client.delete(
        f"ai_assistant:register:code:{email_n}",
        f"ai_assistant:register:cooldown:{email_n}",
    )


def test_generate_code_format() -> None:
    for _ in range(50):
        code = generate_code()
        assert_true(isinstance(code, str), "必须是 str")
        assert_true(len(code) == 6, f"长度必须为 6: {code!r}")
        assert_true(code.isdigit(), f"必须全数字: {code!r}")


def test_leading_zero_preserved() -> None:
    # 统计足够多次，确保能覆盖到前导 0；同时直接构造格式断言
    seen_leading_zero = False
    for _ in range(2000):
        code = generate_code()
        assert_true(isinstance(code, str) and code.isdigit() and len(code) == 6, "格式")
        if code.startswith("0") and code != "000000":
            seen_leading_zero = True
            # 若误转为 int 再转回会丢失前导 0
            assert_true(str(int(code)) != code, "转成 int 会丢失前导 0，故必须保持 str")
            assert_true(code == f"{int(code):06d}", "字符串形式应等价于零填充")
            break
    assert_true(seen_leading_zero, "应能生成以 0 开头的验证码")


def test_redis_stores_hash_not_plaintext() -> None:
    issued = issue_code(TEST_EMAIL_A)
    try:
        client = get_redis()
        assert_true(client is not None, "Redis 应可用")
        key = f"ai_assistant:register:code:{issued.email}"
        data = client.hgetall(key)
        assert_true("code_hash" in data, "应有 code_hash")
        assert_true(issued.code not in data.values(), "Redis 不得存明文验证码")
        assert_true(data["code_hash"] != issued.code, "hash 不能等于明文")
        assert_true(len(data["code_hash"]) == 64, "SHA256 hex 长度")
    finally:
        _cleanup_email(TEST_EMAIL_A)


def test_code_ttl_about_300() -> None:
    issued = issue_code(TEST_EMAIL_A)
    try:
        client = get_redis()
        assert_true(client is not None, "Redis 应可用")
        ttl = client.ttl(f"ai_assistant:register:code:{issued.email}")
        assert_true(
            isinstance(ttl, int) and CODE_TTL_SECONDS - 15 <= ttl <= CODE_TTL_SECONDS,
            f"TTL 应约为 300，实际={ttl}",
        )
    finally:
        _cleanup_email(TEST_EMAIL_A)


def test_cooldown_60s() -> None:
    issued = issue_code(TEST_EMAIL_A)
    try:
        raised = False
        try:
            issue_code(TEST_EMAIL_A)
        except CooldownActiveError as exc:
            raised = True
            assert_true(exc.retry_after is not None and exc.retry_after > 0, "应有 retry_after")
        assert_true(raised, "60 秒内重复发码应触发冷却")
    finally:
        _cleanup_email(TEST_EMAIL_A)


def test_verify_success_and_consume_once() -> None:
    issued = issue_code(TEST_EMAIL_A)
    try:
        first = verify_and_consume_code(issued.email, issued.code)
        assert_true(first.status == VerifyStatus.OK, f"应成功: {first}")
        second = verify_and_consume_code(issued.email, issued.code)
        assert_true(second.status == VerifyStatus.EXPIRED, f"再次消费应失效: {second}")
    finally:
        _cleanup_email(TEST_EMAIL_A)


def test_wrong_code_increments_attempts() -> None:
    issued = issue_code(TEST_EMAIL_A)
    try:
        wrong = "000000" if issued.code != "000000" else "111111"
        result = verify_and_consume_code(issued.email, wrong)
        assert_true(result.status == VerifyStatus.INVALID, f"应为 invalid: {result}")
        assert_true(result.attempts == 1, f"attempts 应为 1: {result}")
        client = get_redis()
        assert_true(client is not None, "Redis")
        stored = client.hget(
            f"ai_assistant:register:code:{issued.email}",
            "attempts",
        )
        assert_true(stored == "1", f"Redis attempts 应为 1: {stored}")
    finally:
        _cleanup_email(TEST_EMAIL_A)


def test_five_wrong_exhausts() -> None:
    issued = issue_code(TEST_EMAIL_A)
    try:
        wrong = "000000" if issued.code != "000000" else "111111"
        last = None
        for i in range(5):
            last = verify_and_consume_code(issued.email, wrong)
        assert_true(last is not None, "应有结果")
        assert_true(last.status == VerifyStatus.EXHAUSTED, f"第5次应耗尽: {last}")
        again = verify_and_consume_code(issued.email, issued.code)
        assert_true(again.status == VerifyStatus.EXPIRED, f"耗尽后正确码也失效: {again}")
    finally:
        _cleanup_email(TEST_EMAIL_A)


def test_expired_code_unusable() -> None:
    issued = issue_code(TEST_EMAIL_A)
    try:
        client = get_redis()
        assert_true(client is not None, "Redis")
        key = f"ai_assistant:register:code:{issued.email}"
        client.expire(key, 1)
        time.sleep(1.2)
        result = verify_and_consume_code(issued.email, issued.code)
        assert_true(result.status == VerifyStatus.EXPIRED, f"过期后应失效: {result}")
    finally:
        _cleanup_email(TEST_EMAIL_A)


def test_concurrent_consume_at_most_one_success() -> None:
    issued = issue_code(TEST_EMAIL_A)
    results: list[VerifyStatus] = []
    lock = threading.Lock()
    barrier = threading.Barrier(2)

    def worker() -> None:
        barrier.wait(timeout=5)
        r = verify_and_consume_code(issued.email, issued.code)
        with lock:
            results.append(r.status)

    try:
        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)
        ok_count = sum(1 for s in results if s == VerifyStatus.OK)
        assert_true(len(results) == 2, f"应有 2 个结果: {results}")
        assert_true(ok_count == 1, f"最多一个成功，实际 ok={ok_count}, results={results}")
    finally:
        _cleanup_email(TEST_EMAIL_A)


def test_cancel_does_not_remove_others_cooldown() -> None:
    # 请求 A 发码
    issued_a = issue_code(TEST_EMAIL_A)
    # 伪造：另一邮箱 B 的冷却属于另一 request
    client = get_redis()
    assert_true(client is not None, "Redis")
    other_rid = uuid.uuid4().hex
    email_b = normalize_email(TEST_EMAIL_B)
    client.set(
        f"ai_assistant:register:cooldown:{email_b}",
        other_rid,
        ex=60,
    )
    try:
        # 用 A 的 request_id 去 cancel B —— 不应删 B 的冷却
        deleted_code, deleted_cd = cancel_code_issue(TEST_EMAIL_B, issued_a.request_id)
        assert_true(deleted_code is False, "不应删除 B 的 code（本不匹配）")
        assert_true(deleted_cd is False, "不应删除他人 cooldown")
        assert_true(
            client.get(f"ai_assistant:register:cooldown:{email_b}") == other_rid,
            "B 的冷却应仍在",
        )

        # 用正确 request_id cancel A：应清 A 的 code 与 cooldown
        d_code, d_cd = cancel_code_issue(TEST_EMAIL_A, issued_a.request_id)
        assert_true(d_code is True, "应删除 A 的 code")
        assert_true(d_cd is True, "应删除 A 的 cooldown")
    finally:
        _cleanup_email(TEST_EMAIL_A)
        _cleanup_email(TEST_EMAIL_B)


def test_redis_unavailable_behavior() -> None:
    with patch("app.services.email_code_service.get_redis", return_value=None):
        raised = False
        try:
            issue_code(TEST_EMAIL_A)
        except RedisUnavailableError:
            raised = True
        assert_true(raised, "Redis 不可用时应抛 RedisUnavailableError")


def test_issue_sets_positive_ttl_immediately() -> None:
    """发码成功后立即检查 TTL：必须 >0、≠-1，且不超过 300。"""

    issued = issue_code(TEST_EMAIL_A)
    try:
        client = get_redis()
        assert_true(client is not None, "Redis 应可用")
        key = f"ai_assistant:register:code:{issued.email}"
        ttl = client.ttl(key)
        assert_true(ttl != -1, f"Hash 必须带过期时间，不能为 -1（无 TTL），实际={ttl}")
        assert_true(ttl != -2, f"Key 应存在，不能为 -2，实际={ttl}")
        assert_true(
            isinstance(ttl, int) and 0 < ttl <= CODE_TTL_SECONDS,
            f"TTL 应满足 0 < ttl <= 300，实际={ttl}",
        )
        assert_true(client.exists(key) == 1, "code Hash 应存在")
    finally:
        _cleanup_email(TEST_EMAIL_A)


def test_store_failure_rolls_back_by_request_id() -> None:
    """
    模拟原子写入 Lua（含 EXPIRE）失败：应抛 RedisError，
    并按 request_id 清掉本请求冷却；不得留下无 TTL 的 code Hash。
    """

    client = get_redis()
    assert_true(client is not None, "Redis")
    email = normalize_email(TEST_EMAIL_A)
    real_eval = client.eval

    def eval_fail_store(script: str, numkeys: int, *args: object):
        # 仅打断「写入 Hash+TTL」脚本；校验/回滚脚本仍可用
        if "EXPIRE" in script and "code_hash" in script:
            raise RedisError("simulated atomic store failure")
        return real_eval(script, numkeys, *args)

    with patch.object(client, "eval", side_effect=eval_fail_store):
        raised = False
        try:
            issue_code(TEST_EMAIL_A)
        except RedisError:
            raised = True
        assert_true(raised, "原子写入失败应抛出 RedisError")

    assert_true(
        client.exists(f"ai_assistant:register:code:{email}") == 0,
        "失败回滚后不应留下 code Hash",
    )
    assert_true(
        client.exists(f"ai_assistant:register:cooldown:{email}") == 0,
        "失败回滚后本请求 cooldown 应被清除",
    )


def test_store_failure_rollback_does_not_touch_other_request() -> None:
    """issue 失败回滚不得删除其他 request_id 的冷却/验证码。"""

    client = get_redis()
    assert_true(client is not None, "Redis")
    email_b = normalize_email(TEST_EMAIL_B)
    other_rid = uuid.uuid4().hex
    # 预先写入「他人」状态
    client.set(
        f"ai_assistant:register:cooldown:{email_b}",
        other_rid,
        ex=60,
    )
    client.hset(
        f"ai_assistant:register:code:{email_b}",
        mapping={
            "code_hash": "deadbeef" * 8,
            "attempts": "0",
            "request_id": other_rid,
        },
    )
    client.expire(f"ai_assistant:register:code:{email_b}", 300)

    real_eval = client.eval

    def eval_fail_store(script: str, numkeys: int, *args: object):
        if "EXPIRE" in script and "code_hash" in script:
            raise RedisError("simulated atomic store failure")
        return real_eval(script, numkeys, *args)

    try:
        with patch.object(client, "eval", side_effect=eval_fail_store):
            try:
                issue_code(TEST_EMAIL_A)
            except RedisError:
                pass

        assert_true(
            client.get(f"ai_assistant:register:cooldown:{email_b}") == other_rid,
            "他人 cooldown 不得被误删",
        )
        assert_true(
            client.hget(
                f"ai_assistant:register:code:{email_b}",
                "request_id",
            )
            == other_rid,
            "他人 code Hash 不得被误删",
        )
    finally:
        _cleanup_email(TEST_EMAIL_A)
        _cleanup_email(TEST_EMAIL_B)


def main() -> int:
    if not init_redis():
        print("FAIL: 无法连接 Redis，请确认 Docker Redis 在 127.0.0.1:6379")
        return 1

    cases = [
        ("generate_code_format", test_generate_code_format),
        ("leading_zero_preserved", test_leading_zero_preserved),
        ("redis_stores_hash_not_plaintext", test_redis_stores_hash_not_plaintext),
        ("code_ttl_about_300", test_code_ttl_about_300),
        ("cooldown_60s", test_cooldown_60s),
        ("verify_success_and_consume_once", test_verify_success_and_consume_once),
        ("wrong_code_increments_attempts", test_wrong_code_increments_attempts),
        ("five_wrong_exhausts", test_five_wrong_exhausts),
        ("expired_code_unusable", test_expired_code_unusable),
        ("concurrent_consume_at_most_one_success", test_concurrent_consume_at_most_one_success),
        ("cancel_does_not_remove_others_cooldown", test_cancel_does_not_remove_others_cooldown),
        ("redis_unavailable_behavior", test_redis_unavailable_behavior),
        ("issue_sets_positive_ttl_immediately", test_issue_sets_positive_ttl_immediately),
        ("store_failure_rolls_back_by_request_id", test_store_failure_rolls_back_by_request_id),
        (
            "store_failure_rollback_does_not_touch_other_request",
            test_store_failure_rollback_does_not_touch_other_request,
        ),
    ]

    results = [run_case(name, fn) for name, fn in cases]
    # 保险清理
    _cleanup_email(TEST_EMAIL_A)
    _cleanup_email(TEST_EMAIL_B)

    passed = sum(1 for _, ok, _ in results if ok)
    print("=== email_code_service phase-2 ===")
    for name, ok, detail in results:
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {name}")
        if not ok:
            print(detail)
    print(f"total: {passed}/{len(results)}")
    close_redis()
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
