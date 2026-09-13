import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import TaskList from './TaskList.vue'

describe('TaskList', () => {
  it('renders one agent-owned plan group without tabs', () => {
    const wrapper = mount(TaskList, {
      props: {
        planGroups: [
          {
            id: 'geo',
            agent: 'geo',
            label: '空间主理人',
            updated_at: '',
            entries: [
              { id: 'plan-1', label: '自行判断是否需要分派角色', status: 'completed' },
              { id: 'plan-2', label: '等待专门角色回传前置检查', status: 'in_progress' },
            ],
          },
        ],
        planEntries: [],
      },
    })

    expect(wrapper.find('[data-testid="plan-group-tabs"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('自行判断是否需要分派角色')
    expect(wrapper.text()).toContain('等待专门角色回传前置检查')
    expect(wrapper.text()).toContain('已完成')
    expect(wrapper.text()).toContain('进行中')
    expect(wrapper.get('[data-testid="plan-card-plan-1"]').classes()).toEqual(expect.arrayContaining(['rounded-lg', 'border', 'border-slate-200/70', 'bg-white', 'shadow-sm']))
    expect(wrapper.get('[data-testid="plan-status-plan-1"]').classes()).toEqual(expect.arrayContaining(['rounded-full', 'bg-emerald-50']))
    expect(wrapper.text()).not.toContain('completed')
    expect(wrapper.text()).not.toContain('in_progress')
  })

  it('renders multiple agent-owned plan groups as tabs and supports blocked status', async () => {
    const wrapper = mount(TaskList, {
      props: {
        planGroups: [
          {
            id: 'geo',
            agent: 'geo',
            label: '空间主理人',
            updated_at: '',
            entries: [{ id: 'plan-1', label: '统筹角色协作', status: 'completed' }],
          },
          {
            id: 'spatial-prep',
            agent: 'spatial-prep',
            label: '空间整备师',
            updated_at: '',
            entries: [
              { id: 'plan-1', label: '等待用户补齐轨迹目录', status: 'blocked' },
            ],
          },
        ],
        planEntries: [],
      },
    })

    expect(wrapper.find('[data-testid="plan-group-tabs"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('空间主理人')
    expect(wrapper.text()).toContain('空间整备师')
    expect(wrapper.text()).toContain('统筹角色协作')
    expect(wrapper.text()).not.toContain('等待用户补齐轨迹目录')

    await wrapper.get('[data-testid="plan-group-tab-spatial-prep"]').trigger('click')

    expect(wrapper.text()).toContain('等待用户补齐轨迹目录')
    expect(wrapper.text()).toContain('已阻塞')
    expect(wrapper.text()).not.toContain('blocked')
  })

  it('renders runtime plan entries only when there are no plan groups', () => {
    const wrapper = mount(TaskList, {
      props: {
        planGroups: [],
        planEntries: [
          { id: 'plan-1', label: '运行时执行计划', status: 'pending' },
        ],
      },
    })

    expect(wrapper.find('[data-testid="plan-group-tabs"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('运行时执行计划')
    expect(wrapper.text()).toContain('待开始')
  })

  it('keeps an empty agent-owned plan unobtrusive', () => {
    const wrapper = mount(TaskList, {
      props: {
        planGroups: [],
        planEntries: [],
      },
    })

    expect(wrapper.text()).toContain('暂无执行计划。')
    expect(wrapper.find('[data-testid="plan-group-tabs"]').exists()).toBe(false)
  })
})
