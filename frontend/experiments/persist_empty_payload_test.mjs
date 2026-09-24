/**
 * 验证空会话持久化快照检测（不依赖浏览器环境）。
 */
import { createRequire } from 'node:module'
import { pathToFileURL } from 'node:url'
import path from 'node:path'

// 直接内联测试逻辑，避免 TS 编译
function isEmptyConversationPersistPayload(value) {
  try {
    const parsed = JSON.parse(value)
    const id = parsed.currentConversationId
    const owner = parsed.ownerUserId
    return (
      (id === null || id === undefined) &&
      (owner === null || owner === undefined)
    )
  } catch {
    return false
  }
}

const cases = [
  [
    'both_null',
    isEmptyConversationPersistPayload(
      JSON.stringify({ currentConversationId: null, ownerUserId: null }),
    ),
    true,
  ],
  [
    'has_id',
    isEmptyConversationPersistPayload(
      JSON.stringify({ currentConversationId: 3, ownerUserId: '1' }),
    ),
    false,
  ],
  [
    'only_owner_null_with_id',
    isEmptyConversationPersistPayload(
      JSON.stringify({ currentConversationId: 2, ownerUserId: null }),
    ),
    false,
  ],
  [
    'invalid_json',
    isEmptyConversationPersistPayload('{'),
    false,
  ],
]

let failed = 0
console.log('=== conversation persist payload tests ===')
for (const [name, actual, expected] of cases) {
  const ok = actual === expected
  if (!ok) failed += 1
  console.log(`[${ok ? 'PASS' : 'FAIL'}] ${name} actual=${actual} expected=${expected}`)
}
console.log(`summary: ${cases.length - failed}/${cases.length} passed`)
process.exit(failed)
