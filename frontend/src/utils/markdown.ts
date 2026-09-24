import MarkdownIt from 'markdown-it'

/**
 * Markdown 渲染器。
 * html: false 防止模型输出被当成 HTML 注入。
 * 代码块保留 language class，样式侧负责横向滚动与高亮观感。
 */
const md = new MarkdownIt({
  html: false,
  breaks: true,
  linkify: true,
  highlight(str: string, lang: string): string {
    // 不做第三方语法高亮库依赖；转义后交给 CSS 呈现代码块
    const escaped = md.utils.escapeHtml(str)
    const language = lang ? md.utils.escapeHtml(lang) : ''

    if (language) {
      return (
        `<pre class="md-code-block" data-lang="${language}">` +
        `<code class="language-${language}">${escaped}</code>` +
        `</pre>`
      )
    }

    return (
      `<pre class="md-code-block">` +
      `<code>${escaped}</code>` +
      `</pre>`
    )
  },
})

export function renderMarkdown(content: string): string {
  if (!content) {
    return ''
  }

  return md.render(content)
}
