import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import FinalArtifactCarousel from './FinalArtifactCarousel.vue'

describe('FinalArtifactCarousel', () => {
  it('offers previews only for supported final artifacts', async () => {
    const wrapper = mount(FinalArtifactCarousel, {
      props: {
        artifacts: [
          { id: 'artifact-map', title: '热力图', path: 'haidian_heatmap.png', display_hint: 'map', kind: 'map' },
          { id: 'artifact-json', title: '运行清单', path: 'manifest.json', display_hint: 'json', kind: 'json' },
        ],
      },
    })

    expect(wrapper.find('[data-testid="final-artifact-preview-artifact-map"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="final-artifact-preview-artifact-json"]').exists()).toBe(false)

    await wrapper.get('[data-testid="final-artifact-preview-artifact-map"]').trigger('click')

    expect(wrapper.emitted('preview-artifact')?.[0]?.[0]).toMatchObject({ id: 'artifact-map' })
  })
})
