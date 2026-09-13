import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

import SessionSidebar from './SessionSidebar.vue'


describe('SessionSidebar', () => {
  const sessions = [
    {
      id: 'session-1',
      title: '新建会话 1',
      status: 'running' as const,
      created_at: '',
      updated_at: '',
      workspace_path: '/tmp/workspace/session-1',
    },
    {
      id: 'session-2',
      title: '北京 FCD KDE',
      status: 'idle' as const,
      created_at: '',
      updated_at: '',
      workspace_path: '/tmp/workspace/session-2',
    },
  ]

  it('uses the quieter session-rail wording in the sidebar chrome', () => {
    const wrapper = mount(SessionSidebar, {
      props: {
        sessions: [],
        activeSessionId: null,
      },
    })

    expect(wrapper.text()).toContain('会话')
    expect(wrapper.text()).not.toContain('历史会话')
    expect(wrapper.text()).toContain('暂无会话')
  })

  it('shows session titles, hides raw id/status text, and emits dropdown actions', async () => {
    const wrapper = mount(SessionSidebar, {
      props: {
        sessions: [sessions[0]],
        activeSessionId: 'session-1',
      },
    })

    expect(wrapper.text()).toContain('新建会话 1')
    expect(wrapper.text()).not.toContain('session-1')
    expect(wrapper.text()).not.toContain('running')
    expect(wrapper.get('aside').classes()).toContain('z-40')
    expect(wrapper.get('[data-testid="running-indicator-session-1"]').attributes('aria-label')).toContain('会话运行中')

    await wrapper.get('[data-testid="session-actions-session-1"]').trigger('click')
    expect(wrapper.get('[data-testid="menu-rename-session-1"]').element.parentElement?.className).toContain('z-[80]')
    await wrapper.get('[data-testid="menu-rename-session-1"]').trigger('click')
    await wrapper.get('[data-testid="session-actions-session-1"]').trigger('click')
    await wrapper.get('[data-testid="menu-delete-session-1"]').trigger('click')

    expect(wrapper.emitted('rename-session')?.[0]).toEqual(['session-1'])
    expect(wrapper.emitted('request-delete-session')?.[0]).toEqual(['session-1'])
  })

  it('swaps actions for compact custom checkboxes in batch mode', async () => {
    const wrapper = mount(SessionSidebar, {
      props: {
        sessions,
        activeSessionId: 'session-1',
        batchMode: false,
        selectedSessionIds: [],
      },
    })

    expect(wrapper.find('[data-testid="enter-session-batch-mode"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="session-row-session-1"]').classes()).toContain('py-1.5')
    expect(wrapper.get('[data-testid="session-row-session-1"]').classes()).toContain('mb-1')
    expect(wrapper.get('[data-testid="session-action-slot-session-1"]').classes()).toEqual(expect.arrayContaining(['h-8', 'w-8']))
    await wrapper.get('[data-testid="enter-session-batch-mode"]').trigger('click')
    expect(wrapper.emitted('enter-batch-mode')).toBeTruthy()

    await wrapper.setProps({
      batchMode: true,
      selectedSessionIds: ['session-1'],
    })

    expect(wrapper.find('[data-testid="session-actions-session-1"]').exists()).toBe(false)
    expect(wrapper.find('input[type="checkbox"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="session-checkbox-session-1"]').attributes('aria-checked')).toBe('true')
    expect(wrapper.get('[data-testid="session-checkbox-session-2"]').attributes('aria-checked')).toBe('false')
    expect(wrapper.get('[data-testid="session-row-session-1"]').classes()).toContain('py-1.5')
    expect(wrapper.get('[data-testid="session-row-session-1"]').classes()).toContain('mb-1')
    expect(wrapper.get('[data-testid="session-action-slot-session-1"]').classes()).toEqual(expect.arrayContaining(['h-8', 'w-8']))

    await wrapper.get('[data-testid="session-row-session-2"]').trigger('click')

    expect(wrapper.emitted('toggle-session-selection')?.[0]).toEqual(['session-2'])
    expect(wrapper.emitted('resume-session')).toBeUndefined()

    await wrapper.get('[data-testid="cancel-session-batch-mode"]').trigger('click')
    await wrapper.get('[data-testid="delete-selected-sessions"]').trigger('click')

    expect(wrapper.emitted('cancel-batch-mode')).toBeTruthy()
    expect(wrapper.emitted('request-delete-selected-sessions')).toBeTruthy()
  })

  it('offers a select-all toggle while batch mode is active', async () => {
    const wrapper = mount(SessionSidebar, {
      props: {
        sessions,
        activeSessionId: 'session-1',
        batchMode: true,
        selectedSessionIds: ['session-1'],
      },
    })

    const selectAllButton = wrapper.get('[data-testid="toggle-all-session-selection"]')
    expect(selectAllButton.attributes('title')).toBe('全选会话')
    expect(selectAllButton.attributes('aria-label')).toBe('全选会话')

    await selectAllButton.trigger('click')

    expect(wrapper.emitted('toggle-all-session-selection')).toBeTruthy()

    await wrapper.setProps({
      selectedSessionIds: ['session-1', 'session-2'],
    })

    const clearAllButton = wrapper.get('[data-testid="toggle-all-session-selection"]')
    expect(clearAllButton.attributes('title')).toBe('取消全选')
    expect(clearAllButton.attributes('aria-label')).toBe('取消全选')
  })
})
