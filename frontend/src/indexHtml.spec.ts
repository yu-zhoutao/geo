import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

describe('index.html', () => {
  it('uses the official project name as the browser title', () => {
    const html = readFileSync(resolve(process.cwd(), 'index.html'), 'utf8')

    expect(html).toContain('<title>多智能体协作智能地理空间数据强化分析系统</title>')
  })
})
