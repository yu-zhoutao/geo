import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'
import { loadConfigFromFile } from 'vite'

describe('vite config', () => {
  it('proxies api requests to the backend during development', async () => {
    const result = await loadConfigFromFile(
      { command: 'serve', mode: 'test' },
      resolve(process.cwd(), 'vite.config.ts'),
    )

    expect(result?.config.server?.proxy).toMatchObject({
      '/api': {
        target: 'http://127.0.0.1:8000',
      },
    })
  })
})
