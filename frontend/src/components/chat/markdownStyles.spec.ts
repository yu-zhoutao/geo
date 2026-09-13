import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const cssPath = resolve('src/components/chat/markdownStyles.css')

describe('markdownStyles', () => {
  it('does not put default theme variables on the base markdown element', () => {
    const css = readFileSync(cssPath, 'utf8')
    const baseRule = css.match(/\.message-markdown\s*\{(?<body>[^}]*)\}/)?.groups?.body ?? ''

    expect(baseRule).not.toMatch(/--markdown-body\s*:/)
    expect(css).toContain('.message-markdown--assistant-theme')
  })
})
