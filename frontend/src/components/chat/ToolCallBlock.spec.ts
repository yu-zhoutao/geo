import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

import ToolCallBlock from './ToolCallBlock.vue'

describe('ToolCallBlock', () => {
  it('renders shared Chinese tool labels instead of raw runtime identifiers', async () => {
    const wrapper = mount(ToolCallBlock, {
      props: {
        part: {
          type: 'tool',
          tool: 'geospatial_record_run_evidence',
          state: {
            input: { record_type: 'artifact', title: 'KDE 热点图' },
            output: '{"status":"completed"}',
          },
        },
      },
    })

    expect(wrapper.text()).toContain('记录产物')
    expect(wrapper.text()).not.toContain('geospatial_record_run_evidence')
    expect(wrapper.find('[data-testid="tool-family-icon"]').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('/tmp/workspace')

    await wrapper.get('[data-testid="toggle-tool-details"]').trigger('click')

    expect(wrapper.text()).not.toContain('工具标识')
    expect(wrapper.text()).not.toContain('geospatial_record_run_evidence')
    expect(wrapper.text()).not.toContain('登记智能体脚本生成的产物、数据画像、验证事实、参数快照或声明追踪。')
  })

  it('uses a localized fallback label for unknown tools', async () => {
    const wrapper = mount(ToolCallBlock, {
      props: {
        part: {
          type: 'tool',
          tool: 'runtime_new_tool',
          state: {
            input: { prompt: 'Need a KDE run' },
            output: '{"status":"completed"}',
          },
        },
      },
    })

    expect(wrapper.text()).toContain('运行时工具')
    expect(wrapper.text()).not.toContain('runtime_new_tool')

    await wrapper.get('[data-testid="toggle-tool-details"]').trigger('click')

    expect(wrapper.text()).not.toContain('工具标识')
    expect(wrapper.text()).not.toContain('runtime_new_tool')
    expect(wrapper.text()).not.toContain('未在当前应用工具映射中注册的运行时工具。')
  })

  it('does not fall back to raw tool identifiers when expanded details have no input preview', async () => {
    const wrapper = mount(ToolCallBlock, {
      props: {
        part: {
          type: 'tool',
          tool: 'geospatial_geospatial_get_session_context',
          state: {
            output: '{"status":"ready"}',
          },
        },
      },
    })

    await wrapper.get('[data-testid="toggle-tool-details"]').trigger('click')

    expect(wrapper.text()).toContain('读取上下文')
    expect(wrapper.text()).not.toContain('工具标识')
    expect(wrapper.text()).not.toContain('geospatial_geospatial_get_session_context')
    expect(wrapper.text()).not.toContain('读取后端管理的当前地理会话上下文。')
  })

  it('renders a thin divider between tool input and output', async () => {
    const wrapper = mount(ToolCallBlock, {
      props: {
        part: {
          type: 'tool',
          tool: 'geospatial_record_run_evidence',
          state: {
            input: { record_type: 'artifact', title: 'KDE 热点图' },
            output: '{"status":"completed"}',
          },
        },
      },
    })

    await wrapper.get('[data-testid="toggle-tool-details"]').trigger('click')

    const divider = wrapper.get('[data-testid="tool-input-output-divider"]')
    expect(divider.classes()).toEqual(expect.arrayContaining(['border-t', 'border-gray-200']))
  })

  it('does not render a tool output copy action in expanded details', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal('navigator', { clipboard: { writeText } })

    const wrapper = mount(ToolCallBlock, {
      props: {
        part: {
          type: 'tool',
          tool: 'geospatial_record_run_evidence',
          state: {
            input: { record_type: 'artifact', title: 'KDE 热点图' },
            output: '{"status":"completed"}',
          },
        },
      },
    })

    await wrapper.get('[data-testid="toggle-tool-details"]').trigger('click')

    expect(wrapper.find('[data-testid="copy-tool-output"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('复制工具输出')
    expect(writeText).not.toHaveBeenCalled()
    vi.unstubAllGlobals()
  })
})
