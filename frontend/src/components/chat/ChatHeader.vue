<script setup lang="ts">
/**
 * 顶部栏：产品名、页面导航、当前标题、用户信息、退出登录。
 * 认证逻辑复用 userStore.logout，不在此重复实现。
 */
defineProps<{
  conversationTitle: string
  username: string
}>()

const emit = defineEmits<{
  logout: []
}>()
</script>

<template>
  <header class="chat-header">
    <div class="brand">
      <span class="brand-mark" aria-hidden="true" />
      <div class="brand-text">
        <strong class="brand-name">AI 学习助手</strong>
        <span class="session-title">{{ conversationTitle }}</span>
      </div>
    </div>

    <nav class="header-nav" aria-label="主导航">
      <RouterLink
        class="nav-link"
        to="/chat"
        active-class="active"
      >
        对话
      </RouterLink>
      <RouterLink
        class="nav-link"
        to="/knowledge"
        active-class="active"
      >
        知识库
      </RouterLink>
    </nav>

    <div class="header-actions">
      <div class="user-chip" :title="username">
        <span class="avatar">{{ username.slice(0, 1).toUpperCase() || 'U' }}</span>
        <span class="username">{{ username || '用户' }}</span>
      </div>
      <button type="button" class="logout-btn" @click="emit('logout')">
        退出登录
      </button>
    </div>
  </header>
</template>

<style scoped>
.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  height: 56px;
  padding: 0 20px;
  border-bottom: 1px solid var(--chat-border);
  background: var(--chat-surface);
  flex-shrink: 0;
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.brand-mark {
  width: 28px;
  height: 28px;
  border-radius: 8px;
  background: var(--chat-accent);
  flex-shrink: 0;
}

.brand-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
  gap: 2px;
}

.brand-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--chat-text);
  line-height: 1.2;
}

.session-title {
  font-size: 12px;
  color: var(--chat-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 360px;
}

.header-nav {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.nav-link {
  padding: 6px 12px;
  border-radius: 8px;
  font-size: 13px;
  color: var(--chat-muted);
  text-decoration: none;
  transition: color 0.15s ease, background 0.15s ease;
}

.nav-link:hover {
  color: var(--chat-text);
  background: #f3f4f6;
}

.nav-link.active {
  color: var(--chat-accent);
  background: var(--chat-accent-soft);
  font-weight: 600;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
  margin-left: auto;
}

.user-chip {
  display: flex;
  align-items: center;
  gap: 8px;
  max-width: 160px;
}

.avatar {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--chat-accent-soft);
  color: var(--chat-accent);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 600;
}

.username {
  font-size: 13px;
  color: var(--chat-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.logout-btn {
  border: 1px solid var(--chat-border);
  background: transparent;
  color: var(--chat-muted);
  border-radius: 8px;
  padding: 6px 12px;
  font-size: 13px;
  cursor: pointer;
  transition: color 0.15s ease, border-color 0.15s ease, background 0.15s ease;
}

.logout-btn:hover {
  color: var(--chat-text);
  border-color: #c5cad3;
  background: #f3f4f6;
}

@media (max-width: 720px) {
  .username {
    display: none;
  }

  .session-title {
    max-width: 140px;
  }
}
</style>
