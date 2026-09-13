import MarkdownIt from 'markdown-it'

const markdown = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
})

type MarkdownRule = NonNullable<(typeof markdown.renderer.rules)['text']>
type MarkdownToken = Parameters<MarkdownRule>[0][number]

function addTokenClass(token: MarkdownToken, ...classes: string[]): void {
  for (const value of classes) {
    token.attrJoin('class', value)
  }
}

function installClassRule(tokenType: string, getClasses: (token: MarkdownToken) => string[]): void {
  const defaultRule = markdown.renderer.rules[tokenType] as MarkdownRule | undefined

  markdown.renderer.rules[tokenType] = (tokens, idx, options, env, self) => {
    addTokenClass(tokens[idx], ...getClasses(tokens[idx]))

    if (defaultRule) {
      return defaultRule(tokens, idx, options, env, self)
    }

    return self.renderToken(tokens, idx, options)
  }
}

function renderCodeBlock(token: MarkdownToken): string {
  const language = token.info.trim().split(/\s+/)[0]
  const classes = ['message-markdown__code', 'message-markdown__code--block']

  if (language) {
    classes.push(`language-${markdown.utils.escapeHtml(language)}`)
  }

  return `<pre class="message-markdown__pre"><code class="${classes.join(' ')}">${markdown.utils.escapeHtml(token.content)}</code></pre>\n`
}

installClassRule('paragraph_open', () => ['message-markdown__paragraph'])
installClassRule('heading_open', (token) => ['message-markdown__heading', `message-markdown__heading--${token.tag}`])
installClassRule('bullet_list_open', () => ['message-markdown__list', 'message-markdown__list--bullet'])
installClassRule('ordered_list_open', () => ['message-markdown__list', 'message-markdown__list--ordered'])
installClassRule('list_item_open', () => ['message-markdown__list-item'])
installClassRule('blockquote_open', () => ['message-markdown__blockquote'])
installClassRule('link_open', () => ['message-markdown__link'])
installClassRule('strong_open', () => ['message-markdown__strong'])
installClassRule('em_open', () => ['message-markdown__emphasis'])
installClassRule('s_open', () => ['message-markdown__delete'])
installClassRule('hr', () => ['message-markdown__rule'])
installClassRule('table_open', () => ['message-markdown__table'])
installClassRule('thead_open', () => ['message-markdown__table-head'])
installClassRule('tbody_open', () => ['message-markdown__table-body'])
installClassRule('tr_open', () => ['message-markdown__table-row'])
installClassRule('th_open', () => ['message-markdown__table-head-cell'])
installClassRule('td_open', () => ['message-markdown__table-cell'])
installClassRule('image', () => ['message-markdown__image'])

markdown.renderer.rules.code_inline = (tokens, idx) => {
  return `<code class="message-markdown__code message-markdown__code--inline">${markdown.utils.escapeHtml(tokens[idx].content)}</code>`
}

markdown.renderer.rules.code_block = (tokens, idx) => renderCodeBlock(tokens[idx])
markdown.renderer.rules.fence = (tokens, idx) => renderCodeBlock(tokens[idx])

export function renderMarkdown(value: string): string {
  const trimmed = value.trim()
  if (!trimmed) {
    return ''
  }

  return markdown.render(trimmed)
}
