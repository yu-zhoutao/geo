import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import StatusPanel from './StatusPanel.vue'


describe('StatusPanel', () => {
  it('focuses the sidebar on task and evidence state without workspace controls', () => {
    const wrapper = mount(StatusPanel, {
      props: {
        planGroups: [],
        planEntries: [],
        timelineEntries: [],
        artifacts: [],
      },
    })

    expect(wrapper.text()).not.toContain('打开工作区')
    expect(wrapper.find('[data-testid="open-workspace"]').exists()).toBe(false)
  })

  it('keeps the sidebar focused on global state instead of recent timeline activity', () => {
    const wrapper = mount(StatusPanel, {
      props: {
        planGroups: [],
        planEntries: [{ id: 'plan-1', label: '执行通用预处理', status: 'in_progress' }],
        timelineEntries: [{ id: 'timeline-1', kind: 'status', text: '已启动通用预处理工具', created_at: '' }],
        artifacts: [{ id: 'artifact-1', title: 'KDE 运行清单', path: '/tmp/run-manifest.json', kind: 'manifest', analysis_type: 'kde' }],
        showThinking: false,
      },
    })

    expect(wrapper.text()).toContain('执行通用预处理')
    expect(wrapper.text()).toContain('KDE 运行清单')
    expect(wrapper.text().indexOf('执行计划')).toBeLessThan(wrapper.text().indexOf('工作区产物'))
    expect(wrapper.text().indexOf('工作区产物')).toBeLessThan(wrapper.text().indexOf('地理任务摘要'))
    expect(wrapper.text()).not.toContain('最近活动')
    expect(wrapper.text()).not.toContain('已启动通用预处理工具')
  })

  it('keeps the settings area minimal with a single inline toggle row', () => {
    const wrapper = mount(StatusPanel, {
      props: {
        planGroups: [],
        planEntries: [],
        timelineEntries: [],
        artifacts: [],
        showThinking: false,
      },
    })

    expect(wrapper.text()).toContain('设置')
    expect(wrapper.text()).toContain('显示思考内容')
    expect(wrapper.text()).not.toContain('控制当前应用内的展示偏好')
    expect(wrapper.text()).not.toContain('在 agent 消息中以内联折叠块展示 reasoning 流')
    expect(wrapper.get('[data-testid="sidebar-setting-show-thinking"]').attributes('role')).toBe('switch')
    expect(wrapper.get('[data-testid="sidebar-setting-show-thinking"]').attributes('aria-checked')).toBe('false')
  })
})
