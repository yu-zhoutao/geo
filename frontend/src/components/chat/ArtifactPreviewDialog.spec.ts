import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'

import ArtifactPreviewDialog from './ArtifactPreviewDialog.vue'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('ArtifactPreviewDialog', () => {
  it('renders markdown artifact previews on demand inside a modal', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      text: () => Promise.resolve('# 报告\n\n可复核结果'),
    })
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(ArtifactPreviewDialog, {
      props: {
        open: true,
        sessionId: 'session-1',
        artifact: {
          id: 'artifact-report',
          title: 'KDE 报告',
          path: 'report.md',
          display_hint: 'markdown',
        },
      },
      attachTo: document.body,
    })

    try {
      await vi.waitFor(() => {
        expect(fetchMock).toHaveBeenCalledWith('/api/sessions/session-1/artifacts/artifact-report/content')
        expect(document.body.textContent ?? '').toContain('可复核结果')
      })
      expect(document.body.querySelector('.message-markdown')).not.toBeNull()
      expect(document.body.querySelector('.message-markdown--assistant-theme')).not.toBeNull()
      expect(document.body.querySelector('.message-markdown__heading--h1')).not.toBeNull()
    } finally {
      wrapper.unmount()
    }
  })

  it('renders CSV artifact previews as a bounded table', async () => {
    const rows = Array.from({ length: 105 }, (_, index) => `BJ${index},${index}`).join('\n')
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      text: () => Promise.resolve(`fid,count\n${rows}`),
    })
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(ArtifactPreviewDialog, {
      props: {
        open: true,
        sessionId: 'session-1',
        artifact: {
          id: 'artifact-csv',
          title: '投影点',
          path: 'projected.csv',
          format: 'csv',
          display_hint: 'table',
        },
      },
      attachTo: document.body,
    })

    try {
      await vi.waitFor(() => {
        expect(document.body.querySelector('[data-testid="artifact-table-preview"]')).not.toBeNull()
      })

      expect(document.body.querySelector('pre')).toBeNull()
      expect(document.body.querySelectorAll('tbody tr')).toHaveLength(100)
      expect(document.body.textContent ?? '').toContain('fid')
      expect(document.body.textContent ?? '').toContain('仅显示前 100 行')
    } finally {
      wrapper.unmount()
    }
  })
})
