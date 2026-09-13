import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'

import ArtifactInlineBlock from './ArtifactInlineBlock.vue'
import type { Artifact } from '../../types'

const markdownArtifact: Artifact = {
  id: 'artifact-md',
  title: '参数快照',
  path: 'outputs/params.md',
  format: 'md',
  display_hint: 'markdown',
  artifact_stage: 'intermediate',
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('ArtifactInlineBlock', () => {
  it('loads previewable text content only after the preview is opened', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      text: () => Promise.resolve('# 参数\n\n- bandwidth: 968m'),
    })
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(ArtifactInlineBlock, {
      props: {
        artifact: markdownArtifact,
        sessionId: 'session-1',
      },
    })

    expect(fetchMock).not.toHaveBeenCalled()

    await wrapper.get('[data-testid="inline-artifact-preview"]').trigger('click')
    await vi.waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(1)
    })
    await vi.waitFor(() => {
      expect(wrapper.text()).toContain('bandwidth')
    })

    expect(fetchMock).toHaveBeenCalledWith('/api/sessions/session-1/artifacts/artifact-md/content')
  })

  it('does not offer inline previews for open-only artifact formats', () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(ArtifactInlineBlock, {
      props: {
        artifact: {
          id: 'artifact-json',
          title: '机器可读清单',
          path: 'outputs/run.json',
          format: 'json',
          display_hint: 'json',
          kind: 'json',
        },
        sessionId: 'session-1',
      },
    })

    expect(wrapper.find('[data-testid="inline-artifact-preview"]').exists()).toBe(false)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('renders table artifacts as compact tables after preview opens', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      text: () => Promise.resolve('fid,count\nBJ001,12\nBJ002,7\n'),
    })
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(ArtifactInlineBlock, {
      props: {
        artifact: {
          id: 'artifact-csv-inline',
          title: '投影点',
          path: 'outputs/projected.csv',
          format: 'csv',
          display_hint: 'table',
          artifact_stage: 'intermediate',
        },
        sessionId: 'session-1',
      },
    })

    await wrapper.get('[data-testid="inline-artifact-preview"]').trigger('click')

    await vi.waitFor(() => {
      expect(wrapper.find('[data-testid="artifact-table-preview"]').exists()).toBe(true)
    })
    expect(wrapper.find('pre').exists()).toBe(false)
    expect(wrapper.text()).toContain('BJ001')
  })
})
