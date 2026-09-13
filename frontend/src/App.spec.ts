import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

import App from './App.vue'
import ConfirmDialog from './components/shared/ConfirmDialog.vue'
import TextInputDialog from './components/shared/TextInputDialog.vue'


function installScrollMetrics(element: HTMLElement, values: { scrollHeight: number, clientHeight: number, scrollTop: number }) {
  const metrics = { ...values }
  Object.defineProperty(element, 'scrollHeight', {
    configurable: true,
    get: () => metrics.scrollHeight,
  })
  Object.defineProperty(element, 'clientHeight', {
    configurable: true,
    get: () => metrics.clientHeight,
  })
  Object.defineProperty(element, 'scrollTop', {
    configurable: true,
    get: () => metrics.scrollTop,
    set: (value: number) => {
      metrics.scrollTop = value
    },
  })
  return metrics
}


class FakeEventSource {
  static instances: FakeEventSource[] = []

  onmessage: ((event: MessageEvent<string>) => void) | null = null
  onerror: (() => void) | null = null
  private listeners = new Map<string, Array<(event: MessageEvent<string>) => void>>()
  readonly url: string

  constructor(url: string) {
    this.url = url
    FakeEventSource.instances.push(this)
  }

  emit(data: unknown): void {
    this.onmessage?.(new MessageEvent('message', { data: JSON.stringify(data) }))
  }

  emitNamed(type: string, data: unknown): void {
    const event = new MessageEvent(type, { data: JSON.stringify(data) })
    for (const listener of this.listeners.get(type) ?? []) {
      listener(event)
    }
  }

  addEventListener(type: string, listener: (event: MessageEvent<string>) => void): void {
    const listeners = this.listeners.get(type) ?? []
    listeners.push(listener)
    this.listeners.set(type, listeners)
  }

  close(): void {}
}

function createFakeStorage() {
  const store = new Map<string, string>()
  return {
    getItem(key: string): string | null {
      return store.get(key) ?? null
    },
    setItem(key: string, value: string): void {
      store.set(key, value)
    },
    removeItem(key: string): void {
      store.delete(key)
    },
    clear(): void {
      store.clear()
    },
  }
}

function sessionPayload(id: string, title: string, status: 'idle' | 'running' | 'waiting_for_input' | 'completed' | 'failed' = 'idle') {
  return {
    id,
    title,
    status,
    messages: [],
    timeline: [],
    artifacts: [],
    plan: [],
    question: null,
    geospatial_task: null,
    verification: [],
    attached_data_directories: [],
    workspace_path: `/tmp/workspaces/${id}`,
  }
}


describe('App', () => {
  beforeEach(() => {
    FakeEventSource.instances = []
    vi.stubGlobal('EventSource', FakeEventSource)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    vi.useRealTimers()
    document.body.innerHTML = ''
  })

  it('shows a non-dismissible modal geospatial provisioning dialog with logs', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          app: 'ready',
          runtime: { status: 'ready' },
          geospatial_environment: {
            status: 'provisioning',
            progress: 0.42,
            logs: ['Installing geopandas', 'Installing rasterio'],
          },
        }),
      })
      .mockResolvedValueOnce({ ok: true, json: async () => [] })

    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(App)
    await flushPromises()

    const overlay = wrapper.get('[data-testid="geospatial-provisioning-overlay"]')
    expect(overlay.attributes('role')).toBe('dialog')
    expect(overlay.attributes('aria-modal')).toBe('true')
    expect(overlay.text()).toContain('地理运行环境准备中')
    expect(overlay.text()).toContain('Installing geopandas')
    expect(overlay.text()).toContain('Installing rasterio')
    await overlay.trigger('click')
    expect(wrapper.find('[data-testid="geospatial-provisioning-overlay"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="geospatial-provisioning-dialog"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="geospatial-provisioning-logs"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="geospatial-provisioning-dismiss"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('keeps provisioning logs scrolled to the newest line while health polling updates', async () => {
    vi.useFakeTimers()
    let healthRequestCount = 0
    const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
      if (String(url) === '/api/health') {
        healthRequestCount += 1
        return {
          ok: true,
          json: async () => ({
            app: 'ready',
            runtime: { status: 'ready' },
            geospatial_environment: {
              status: 'provisioning',
              progress: healthRequestCount === 1 ? 0.1 : 0.6,
              logs: healthRequestCount === 1
                ? ['Resolving packages']
                : ['Resolving packages', 'Installing rasterio', 'Installing geopandas'],
            },
          }),
        }
      }
      if (String(url) === '/api/sessions') {
        return { ok: true, json: async () => [] }
      }
      throw new Error(`unexpected request: ${String(url)}`)
    })

    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(App)
    await flushPromises()
    const logScroller = wrapper.get('[data-testid="geospatial-provisioning-logs"]').element as HTMLElement
    const metrics = installScrollMetrics(logScroller, {
      scrollHeight: 900,
      clientHeight: 200,
      scrollTop: 0,
    })

    await vi.advanceTimersByTimeAsync(1000)
    await flushPromises()

    expect(wrapper.get('[data-testid="geospatial-provisioning-logs"]').text()).toContain('Installing geopandas')
    expect(metrics.scrollTop).toBe(700)
    wrapper.unmount()
  })

  it('does not scroll provisioning logs when only progress changes', async () => {
    vi.useFakeTimers()
    let healthRequestCount = 0
    const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
      if (String(url) === '/api/health') {
        healthRequestCount += 1
        return {
          ok: true,
          json: async () => ({
            app: 'ready',
            runtime: { status: 'ready' },
            geospatial_environment: {
              status: 'provisioning',
              progress: healthRequestCount === 1 ? 0.1 : 0.6,
              logs: ['Resolving packages'],
            },
          }),
        }
      }
      if (String(url) === '/api/sessions') {
        return { ok: true, json: async () => [] }
      }
      throw new Error(`unexpected request: ${String(url)}`)
    })

    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(App)
    await flushPromises()
    const logScroller = wrapper.get('[data-testid="geospatial-provisioning-logs"]').element as HTMLElement
    const metrics = installScrollMetrics(logScroller, {
      scrollHeight: 900,
      clientHeight: 200,
      scrollTop: 111,
    })

    await vi.advanceTimersByTimeAsync(1000)
    await flushPromises()

    expect(wrapper.get('[data-testid="geospatial-provisioning-logs"]').text()).toContain('Resolving packages')
    expect(metrics.scrollTop).toBe(111)
    wrapper.unmount()
  })

  it('dismisses the provisioning modal when installation completes', async () => {
    vi.useFakeTimers()
    let healthRequestCount = 0
    const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
      if (String(url) === '/api/health') {
        healthRequestCount += 1
        return {
          ok: true,
          json: async () => ({
            app: 'ready',
            runtime: { status: 'ready' },
            geospatial_environment: healthRequestCount === 1
              ? {
                  status: 'provisioning',
                  progress: 0.6,
                  logs: ['Installing geopandas'],
                }
              : {
                  status: 'ready',
                  progress: 1,
                  logs: ['Managed geospatial Python environment is ready.'],
                },
          }),
        }
      }
      if (String(url) === '/api/sessions') {
        return { ok: true, json: async () => [] }
      }
      throw new Error(`unexpected request: ${String(url)}`)
    })

    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(App)
    await flushPromises()
    expect(wrapper.find('[data-testid="geospatial-provisioning-overlay"]').exists()).toBe(true)

    await vi.advanceTimersByTimeAsync(1000)
    await flushPromises()

    expect(wrapper.find('[data-testid="geospatial-provisioning-overlay"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('highlights failed provisioning error log lines', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          app: 'ready',
          runtime: { status: 'ready' },
          geospatial_environment: {
            status: 'failed',
            progress: 0.35,
            logs: ['Installing rasterio', 'ERROR: uv sync failed with exit code 1.'],
          },
        }),
      })
      .mockResolvedValueOnce({ ok: true, json: async () => [] })

    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(App)
    await flushPromises()

    const logLines = wrapper.findAll('[data-testid="geospatial-provisioning-log-line"]')
    expect(logLines[0].classes()).not.toContain('text-rose-300')
    expect(logLines[1].text()).toContain('uv sync failed')
    expect(logLines[1].classes()).toContain('text-rose-300')
    wrapper.unmount()
  })

  it('renames and deletes sessions through inline controls and modal confirmation', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ app: 'ready', runtime: { status: 'ready' } }) })
      .mockResolvedValueOnce({ ok: true, json: async () => [{ id: 'session-1', title: '新建会话 1', status: 'idle', created_at: '', updated_at: '', workspace_path: '/tmp/workspaces/session-1' }] })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ id: 'session-1', title: '重命名后的会话', status: 'idle', created_at: '', updated_at: '', workspace_path: '/tmp/workspaces/session-1' }) })
      .mockResolvedValueOnce({ ok: true, text: async () => '' })

    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(App)
    await flushPromises()

    await wrapper.get('[data-testid="session-actions-session-1"]').trigger('click')
    await wrapper.get('[data-testid="menu-rename-session-1"]').trigger('click')
    await flushPromises()
    ;(document.querySelector('[data-testid="rename-session-dialog-input"]') as HTMLInputElement).value = '重命名后的会话'
    ;(document.querySelector('[data-testid="rename-session-dialog-input"]') as HTMLInputElement).dispatchEvent(new Event('input'))
    ;(document.querySelector('[data-testid="confirm-rename-session"]') as HTMLButtonElement).click()
    await flushPromises()
    expect(wrapper.text()).toContain('重命名后的会话')

    await wrapper.get('[data-testid="session-actions-session-1"]').trigger('click')
    await wrapper.get('[data-testid="menu-delete-session-1"]').trigger('click')
    expect(document.body.textContent).toContain('确认删除会话')
    ;(document.querySelector('[data-testid="confirm-delete-session"]') as HTMLButtonElement).click()
    await flushPromises()

    expect(fetchMock).toHaveBeenCalledWith('/api/sessions/session-1', expect.objectContaining({ method: 'PATCH' }))
    expect(fetchMock).toHaveBeenCalledWith('/api/sessions/session-1', expect.objectContaining({ method: 'DELETE' }))
    expect(wrapper.text()).not.toContain('重命名后的会话')
  })

  it('batch deletes selected sessions after confirmation and resets deleted active session', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ app: 'ready', runtime: { status: 'ready' } }) })
      .mockResolvedValueOnce({ ok: true, json: async () => [
        { id: 'session-1', title: '会话一', status: 'idle', created_at: '', updated_at: '', workspace_path: '/tmp/workspaces/session-1' },
        { id: 'session-2', title: '会话二', status: 'idle', created_at: '', updated_at: '', workspace_path: '/tmp/workspaces/session-2' },
      ] })
      .mockResolvedValueOnce({ ok: true, json: async () => sessionPayload('session-1', '会话一') })
      .mockResolvedValueOnce({ ok: true, text: async () => '' })
      .mockResolvedValueOnce({ ok: true, text: async () => '' })

    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(App)
    await flushPromises()

    await wrapper.get('[data-testid="session-row-session-1"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="active-session-title"]').text()).toBe('会话一')

    await wrapper.get('[data-testid="enter-session-batch-mode"]').trigger('click')
    await wrapper.get('[data-testid="session-row-session-1"]').trigger('click')
    await wrapper.get('[data-testid="session-row-session-2"]').trigger('click')
    await wrapper.get('[data-testid="delete-selected-sessions"]').trigger('click')

    expect(document.body.textContent).toContain('确认删除所选会话')
    expect(document.body.textContent).toContain('2 个会话')
    ;(document.querySelector('[data-testid="confirm-delete-session"]') as HTMLButtonElement).click()
    await flushPromises()

    expect(fetchMock).toHaveBeenCalledWith('/api/sessions/session-1', expect.objectContaining({ method: 'DELETE' }))
    expect(fetchMock).toHaveBeenCalledWith('/api/sessions/session-2', expect.objectContaining({ method: 'DELETE' }))
    expect(wrapper.text()).not.toContain('会话一')
    expect(wrapper.text()).not.toContain('会话二')
    expect(wrapper.get('[data-testid="active-session-title"]').text()).toBe('新会话')
    expect(wrapper.find('[data-testid="enter-session-batch-mode"]').exists()).toBe(true)
  })

  it('selects and clears all visible sessions in batch mode', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce({ ok: true, json: async () => ({ app: 'ready', runtime: { status: 'ready' } }) })
        .mockResolvedValueOnce({ ok: true, json: async () => [
          { id: 'session-1', title: '会话一', status: 'idle', created_at: '', updated_at: '', workspace_path: '/tmp/workspaces/session-1' },
          { id: 'session-2', title: '会话二', status: 'idle', created_at: '', updated_at: '', workspace_path: '/tmp/workspaces/session-2' },
        ] }),
    )

    const wrapper = mount(App)
    await flushPromises()

    await wrapper.get('[data-testid="enter-session-batch-mode"]').trigger('click')
    expect(wrapper.get('[data-testid="delete-selected-sessions"]').attributes('disabled')).toBeDefined()

    await wrapper.get('[data-testid="toggle-all-session-selection"]').trigger('click')

    expect(wrapper.get('[data-testid="session-checkbox-session-1"]').attributes('aria-checked')).toBe('true')
    expect(wrapper.get('[data-testid="session-checkbox-session-2"]').attributes('aria-checked')).toBe('true')
    expect(wrapper.get('[data-testid="delete-selected-sessions"]').attributes('disabled')).toBeUndefined()

    await wrapper.get('[data-testid="toggle-all-session-selection"]').trigger('click')

    expect(wrapper.get('[data-testid="session-checkbox-session-1"]').attributes('aria-checked')).toBe('false')
    expect(wrapper.get('[data-testid="session-checkbox-session-2"]').attributes('aria-checked')).toBe('false')
    expect(wrapper.get('[data-testid="delete-selected-sessions"]').attributes('disabled')).toBeDefined()
  })

  it('keeps batch selection visible and shows an error when selected deletion fails', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ app: 'ready', runtime: { status: 'ready' } }) })
      .mockResolvedValueOnce({ ok: true, json: async () => [
        { id: 'session-1', title: '会话一', status: 'idle', created_at: '', updated_at: '', workspace_path: '/tmp/workspaces/session-1' },
      ] })
      .mockResolvedValueOnce({ ok: false, status: 500, text: async () => JSON.stringify({ detail: '删除失败' }) })

    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(App)
    await flushPromises()

    await wrapper.get('[data-testid="enter-session-batch-mode"]').trigger('click')
    await wrapper.get('[data-testid="session-row-session-1"]').trigger('click')
    await wrapper.get('[data-testid="delete-selected-sessions"]').trigger('click')
    ;(document.querySelector('[data-testid="confirm-delete-session"]') as HTMLButtonElement).click()
    await flushPromises()
    await flushPromises()

    expect(fetchMock).toHaveBeenCalledWith('/api/sessions/session-1', expect.objectContaining({ method: 'DELETE' }))
    expect(wrapper.get('[data-testid="app-error"]').text()).toContain('删除失败')
    expect(wrapper.text()).toContain('会话一')
    expect(wrapper.find('[data-testid="cancel-session-batch-mode"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="session-checkbox-session-1"]').attributes('aria-checked')).toBe('true')
  })

  it('dismisses rename and delete dialogs with escape and restores focus', async () => {
    const renameTrigger = document.createElement('button')
    document.body.appendChild(renameTrigger)
    renameTrigger.focus()

    const renameDialog = mount(TextInputDialog, {
      attachTo: document.body,
      props: {
        open: true,
        title: '重命名会话',
        message: '请输入新的会话名称。',
        initialValue: '新建会话 1',
      },
    })
    await flushPromises()

    ;(document.querySelector('[data-testid="rename-session-dialog-input"]') as HTMLInputElement).dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    expect(renameDialog.emitted('cancel')).toBeTruthy()
    await renameDialog.setProps({ open: false })
    await flushPromises()
    expect(document.activeElement).toBe(renameTrigger)
    renameDialog.unmount()
    renameTrigger.remove()

    const deleteTrigger = document.createElement('button')
    document.body.appendChild(deleteTrigger)
    deleteTrigger.focus()

    const deleteDialog = mount(ConfirmDialog, {
      attachTo: document.body,
      props: {
        open: true,
        title: '确认删除会话',
        message: '删除后无法恢复。',
      },
      slots: {
        icon: '<span>!</span>',
      },
    })
    await flushPromises()

    ;(document.querySelector('[data-testid="confirm-delete-session"]') as HTMLButtonElement).dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    expect(deleteDialog.emitted('cancel')).toBeTruthy()
    await deleteDialog.setProps({ open: false })
    await flushPromises()
    expect(document.activeElement).toBe(deleteTrigger)
    deleteDialog.unmount()
    deleteTrigger.remove()
  })

  it('opens in a send-ready draft state before any session starts', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce({ ok: true, json: async () => ({ app: 'ready', runtime: { status: 'ready' } }) })
        .mockResolvedValueOnce({ ok: true, json: async () => [] }),
    )

    const wrapper = mount(App)
    await flushPromises()

    expect(wrapper.get('[data-testid="message-input"]').attributes('disabled')).toBeUndefined()
    expect(wrapper.get('[data-testid="active-session-title"]').text()).toBe('新会话')
    expect(wrapper.text()).not.toContain('请选择一个会话')
    expect(wrapper.text()).toContain('暂无执行计划。')
    expect(wrapper.text()).toContain('从这里开始新的分析会话。')
    expect(wrapper.text()).toContain('暂无生成产物。')
    expect(wrapper.text()).toContain('添加数据')
    expect(wrapper.get('[data-testid="composer-overlay"]').classes()).toEqual(expect.arrayContaining(['absolute', 'bottom-0', 'pointer-events-none', 'bg-gradient-to-b', 'from-transparent', 'to-white']))
    expect(wrapper.get('[data-testid="message-list-scroller"]').classes()).toContain('pb-[var(--composer-overlay-offset)]')
  })

  it('persists the showThinking sidebar setting across remounts', async () => {
    const storage = createFakeStorage()
    vi.stubGlobal('localStorage', storage)

    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input)
        if (url === '/api/health') {
          return { ok: true, text: async () => JSON.stringify({ app: 'ready', runtime: { status: 'ready' } }) }
        }
        if (url === '/api/sessions') {
          return { ok: true, text: async () => JSON.stringify([]) }
        }
        throw new Error(`Unexpected fetch: ${url}`)
      }),
    )

    const firstWrapper = mount(App)
    await flushPromises()

    const firstToggle = firstWrapper.get('[data-testid="sidebar-setting-show-thinking"]')
    expect(firstToggle.attributes('aria-checked')).toBe('false')

    await firstToggle.trigger('click')
    expect(storage.getItem('geo-agent:app-settings')).toBe('{"showThinking":true}')

    firstWrapper.unmount()

    const secondWrapper = mount(App)
    await flushPromises()

    expect(secondWrapper.get('[data-testid="sidebar-setting-show-thinking"]').attributes('aria-checked')).toBe('true')
  })

  it('exposes mobile toggles for session and inspector panels', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce({ ok: true, json: async () => ({ app: 'ready', runtime: { status: 'ready' } }) })
        .mockResolvedValueOnce({ ok: true, json: async () => [] }),
    )

    const wrapper = mount(App)
    await flushPromises()

    await wrapper.get('[data-testid="mobile-inspector-toggle"]').trigger('click')

    expect(wrapper.find('[data-testid="mobile-session-toggle"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="mobile-inspector-panel"]').exists()).toBe(true)
  })

  it('renders the app icon image in the primary header', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce({ ok: true, json: async () => ({ app: 'ready', runtime: { status: 'ready' } }) })
        .mockResolvedValueOnce({ ok: true, json: async () => [] }),
    )

    const wrapper = mount(App)
    await flushPromises()

    const icon = wrapper.get('[data-testid="app-brand-icon"]')
    expect(icon.attributes('src')).toBe('/app-icon-rounded.png')
    expect(icon.attributes('alt')).toBe('多智能体协作智能地理空间数据强化分析系统图标')
  })

  it('renders the official project title in the primary header', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce({ ok: true, json: async () => ({ app: 'ready', runtime: { status: 'ready' } }) })
        .mockResolvedValueOnce({ ok: true, json: async () => [] }),
    )

    const wrapper = mount(App)
    await flushPromises()

    expect(wrapper.text()).toContain('多智能体协作智能地理空间数据强化分析系统')
  })

  it('uses a session header height aligned with the sidebar rail', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce({ ok: true, json: async () => ({ app: 'ready', runtime: { status: 'ready' } }) })
        .mockResolvedValueOnce({ ok: true, json: async () => [] }),
    )

    const wrapper = mount(App)
    await flushPromises()

    expect(wrapper.get('[data-testid="session-header"]').classes()).toContain('h-14')
  })

  it('creates a backend session only when the first draft prompt is sent', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ app: 'ready', runtime: { status: 'ready' } }) })
      .mockResolvedValueOnce({ ok: true, json: async () => [] })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ id: 'session-1', title: '新建会话 1', status: 'idle', messages: [], timeline: [], artifacts: [], plan: [], question: null, geospatial_task: null, verification: [], attached_data_directories: [], workspace_path: '/tmp/workspaces/session-1' }) })
      .mockResolvedValueOnce({ ok: true, json: async () => [{ id: 'session-1', title: '新建会话 1', status: 'idle', created_at: '', updated_at: '', workspace_path: '/tmp/workspaces/session-1' }] })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ accepted: true, question: null }) })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          id: 'session-1',
          title: '北京 FCD KDE 热点分析',
          status: 'completed',
          messages: [
            { id: 'msg-user-1', role: 'user', agent: 'geo', created_at: '', parts: [{ type: 'text', text: 'Bootstrap the shell' }] },
            { id: 'msg-assistant-1', role: 'assistant', agent: 'geo', created_at: '', parts: [{ type: 'text', text: '## KDE\n已完成。' }, { type: 'tool', tool: 'geospatial_record_run_evidence', state: { status: 'completed', input: { record_type: 'artifact', title: 'KDE 运行摘要' }, meta: { tool_family: 'evidence', tool_label: '登记运行证据' }, output: '{"status":"completed"}' } }] },
            { id: 'msg-reflection-1', role: 'system', agent: 'skeptical-review', created_at: '', parts: [{ type: 'verification', state: { entries: [{ id: 'verification-1', code: 'crs_mismatch_detected', title: '检测到 CRS 不一致', status: 'warning', detail: '需要统一到 EPSG:32650。' }] } }] },
          ],
          timeline: [{ id: 'timeline-1', kind: 'artifact', text: 'KDE 运行摘要', created_at: '' }],
          artifacts: [{ id: 'artifact-1', title: 'KDE 运行摘要', path: '/tmp/workspaces/session-1/outputs/kde-run-summary.md', analysis_type: 'kde', description: '概述输入数据与 KDE 参数。' }],
          plan: [{ id: 'plan-1', label: '执行通用预处理', status: 'completed' }],
          question: null,
          geospatial_task: {
            id: 'task-1',
            prompt: 'Bootstrap the shell',
            analysis_type: 'kde',
            stage: 'completed',
            runtime: {
              bundle_id: 'app-geospatial-agent-knowledge',
              label: '地理智能体知识包',
              roles: [],
              tools: ['get_session_context', 'update_todos', 'record_run_evidence'],
            },
            input_layers: [{ id: 'layer-1', label: '北京 FCD 点样本', path: 'data/fcd_points_sample.csv', geometry_type: 'point', crs: 'EPSG:4326' }],
            study_area: { id: 'layer-2', label: '北京市区县边界', path: 'data/beijing.shp', geometry_type: 'polygon', crs: 'EPSG:32650' },
            prepared_layers: [],
            preprocessing: { target_crs: 'EPSG:32650', clip_to_study_area: true, clip_operation: 'mask' },
            operator: { name: 'kde', stage: 'completed', parameters: { bandwidth_meters: 1000 } },
            expected_outputs: ['summary_report', 'run_metadata'],
          },
          verification: [{ id: 'verification-1', code: 'crs_mismatch_detected', title: '检测到 CRS 不一致', status: 'warning', detail: '需要统一到 EPSG:32650。' }],
          attached_data_directories: [{ id: 'dir-1', path: '/data/beijing-fcd', enabled: true, label: '默认数据目录' }],
          workspace_path: '/tmp/workspaces/session-1',
        }),
      })

    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(App)
    await flushPromises()

    const createCallsBeforeSend = fetchMock.mock.calls.filter((call) => call[0] === '/api/sessions' && (call[1] as { method?: string } | undefined)?.method === 'POST')
    expect(createCallsBeforeSend).toHaveLength(0)
    expect(wrapper.text()).toContain('新会话')
    expect(wrapper.text()).not.toContain('草稿会话')
    expect(wrapper.text()).not.toContain('首条提示词发送后创建会话')
    expect(wrapper.text()).not.toContain('草稿模式')
    expect(wrapper.text()).not.toContain('发送首条提示词后才会真正创建会话')

    await wrapper.get('[data-testid="message-input"]').setValue('Bootstrap the shell')
    await wrapper.get('[data-testid="send-message"]').trigger('submit')
    await flushPromises()

    expect(fetchMock).toHaveBeenCalledWith('/api/sessions', expect.any(Object))
    expect(fetchMock).toHaveBeenCalledWith('/api/sessions/session-1/messages', expect.any(Object))
    expect(fetchMock).toHaveBeenCalledWith('/api/sessions/session-1', expect.any(Object))
    expect(wrapper.text()).toContain('北京 FCD KDE 热点分析')
    expect(wrapper.get('[data-testid="active-session-title"]').text()).toBe('北京 FCD KDE 热点分析')
    expect(wrapper.find('[data-testid="active-session-actions-session-1"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('执行通用预处理')
    expect(wrapper.text()).toContain('已完成')
    expect(wrapper.text()).toContain('Bootstrap the shell')
    expect(wrapper.text()).toContain('KDE')
    expect(wrapper.text()).toContain('记录产物')
    expect(wrapper.text()).toContain('EPSG:32650')
    expect(wrapper.text()).toContain('检测到 CRS 不一致')
    expect(wrapper.text()).toContain('警告')
    expect(wrapper.text()).toContain('KDE 运行摘要')
    expect(wrapper.text()).toContain('/tmp/workspaces/session-1')
    expect(wrapper.text()).toContain('默认数据目录')
    expect(wrapper.find('[data-testid="message-agent-label-restored-todo-session-1"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="message-agent-label-restored-artifact-artifact-1"]').exists()).toBe(false)
  })

  it('applies draft attachments before sending the first message', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ app: 'ready', runtime: { status: 'ready' } }) })
      .mockResolvedValueOnce({ ok: true, json: async () => [] })
      .mockResolvedValueOnce({ ok: true, text: async () => JSON.stringify({ items: [{ id: 'recent-1', path: '/data/beijing-fcd', enabled: true, label: '北京 FCD' }] }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ id: 'session-1', title: '新建会话 1', status: 'idle', messages: [], timeline: [], artifacts: [], plan: [], question: null, geospatial_task: null, verification: [], attached_data_directories: [], workspace_path: '/tmp/workspaces/session-1' }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ id: 'session-1', title: '新建会话 1', status: 'idle', messages: [], timeline: [], artifacts: [], plan: [], question: null, geospatial_task: null, verification: [], attached_data_directories: [{ id: 'dir-1', path: '/data/beijing-fcd', enabled: true, label: '北京 FCD' }], workspace_path: '/tmp/workspaces/session-1' }) })
      .mockResolvedValueOnce({ ok: true, json: async () => [{ id: 'session-1', title: '新建会话 1', status: 'idle', created_at: '', updated_at: '', workspace_path: '/tmp/workspaces/session-1', attached_data_directories: [{ id: 'dir-1', path: '/data/beijing-fcd', enabled: true, label: '北京 FCD' }] }] })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ accepted: true, question: null }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ id: 'session-1', title: '北京 FCD KDE 热点分析', status: 'completed', messages: [], timeline: [], artifacts: [], plan: [], question: null, geospatial_task: null, verification: [], attached_data_directories: [{ id: 'dir-1', path: '/data/beijing-fcd', enabled: true, label: '北京 FCD' }], workspace_path: '/tmp/workspaces/session-1' }) })

    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(App)
    await flushPromises()

    await wrapper.get('[data-testid="composer-attach-trigger"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="recent-directory-recent-1"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('北京 FCD')

    await wrapper.get('[data-testid="message-input"]').setValue('Use attached data')
    await wrapper.get('[data-testid="send-message"]').trigger('submit')
    await flushPromises()

    expect(fetchMock).toHaveBeenCalledWith('/api/sessions/session-1/data-directories', expect.objectContaining({ method: 'PUT' }))
    expect(fetchMock).toHaveBeenCalledWith('/api/sessions/session-1/messages', expect.any(Object))
  })

  it('shows the default data directory before session creation and lets the user remove it', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ app: 'ready', runtime: { status: 'ready' }, default_data_directories: [{ id: 'attached-data-root', path: '/workspace/data', enabled: true, label: '默认数据目录' }] }) })
      .mockResolvedValueOnce({ ok: true, json: async () => [] })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ id: 'session-1', title: '新建会话 1', status: 'idle', messages: [], timeline: [], artifacts: [], plan: [], question: null, geospatial_task: null, verification: [], attached_data_directories: [{ id: 'attached-data-root', path: '/workspace/data', enabled: true, label: '默认数据目录' }], workspace_path: '/tmp/workspaces/session-1' }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ id: 'session-1', title: '新建会话 1', status: 'idle', messages: [], timeline: [], artifacts: [], plan: [], question: null, geospatial_task: null, verification: [], attached_data_directories: [], workspace_path: '/tmp/workspaces/session-1' }) })
      .mockResolvedValueOnce({ ok: true, json: async () => [{ id: 'session-1', title: '新建会话 1', status: 'idle', created_at: '', updated_at: '', workspace_path: '/tmp/workspaces/session-1', attached_data_directories: [] }] })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ accepted: true, question: null }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ id: 'session-1', title: '北京 FCD KDE 热点分析', status: 'completed', messages: [], timeline: [], artifacts: [], plan: [], question: null, geospatial_task: null, verification: [], attached_data_directories: [], workspace_path: '/tmp/workspaces/session-1' }) })

    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(App)
    await flushPromises()

    expect(wrapper.text()).toContain('默认数据目录')

    await wrapper.get('[data-testid="attached-directory-remove-attached-data-root"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).not.toContain('默认数据目录')

    await wrapper.get('[data-testid="message-input"]').setValue('Use no default data')
    await wrapper.get('[data-testid="send-message"]').trigger('submit')
    await flushPromises()

    expect(fetchMock).toHaveBeenCalledWith('/api/sessions/session-1/data-directories', expect.objectContaining({ method: 'PUT' }))
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/sessions/session-1/data-directories',
      expect.objectContaining({ body: JSON.stringify({ items: [] }) }),
    )
  })

  it('renders blocked questions and reproducibility artifacts from live SSE updates', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ app: 'ready', runtime: { status: 'ready' } }) })
      .mockResolvedValueOnce({ ok: true, json: async () => [{ id: 'session-1', title: '北京 FCD KDE 会话', status: 'running', created_at: '', updated_at: '', workspace_path: '/tmp/workspaces/session-1' }] })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          id: 'session-1',
          title: '北京 FCD KDE 会话',
          status: 'running',
          messages: [],
          timeline: [],
          artifacts: [],
          plan: [],
          question: null,
          geospatial_task: {
            id: 'task-1',
            prompt: 'Need a KDE run',
            analysis_type: 'kde',
            stage: 'planned',
            runtime: { bundle_id: 'app-geospatial-agent-knowledge', label: '地理智能体知识包', roles: [], tools: ['get_session_context', 'update_todos', 'record_run_evidence'] },
            input_layers: [],
            study_area: null,
            prepared_layers: [],
            preprocessing: { target_crs: 'EPSG:32650', clip_to_study_area: true, clip_operation: 'mask' },
            operator: { name: 'kde', stage: 'planned', parameters: {} },
            expected_outputs: [],
          },
          verification: [],
          attached_data_directories: [],
          workspace_path: '/tmp/workspaces/session-1',
        }),
      })

    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(App)
    await flushPromises()

    await wrapper.get('[data-testid="session-row-session-1"]').trigger('click')
    await flushPromises()

    const eventSource = FakeEventSource.instances[0]
    eventSource.emitNamed('session.plan', {
      type: 'session.plan',
      payload: [
        { id: 'plan-1', label: '规范化地理分析任务', status: 'completed' },
        { id: 'plan-2', label: '执行通用预处理', status: 'in_progress' },
      ],
    })
    eventSource.emitNamed('session.question', {
      type: 'session.question',
      payload: { id: 'question-1', prompt: '是否改用默认北京市区县边界继续执行？' },
    })
    eventSource.emitNamed('session.artifact', {
      type: 'session.artifact',
      payload: {
        id: 'artifact-1',
        title: 'KDE 运行清单',
        path: '/tmp/workspaces/session-1/run-manifest.json',
        analysis_type: 'kde',
        kind: 'manifest',
        description: '旧版运行清单',
      },
    })
    eventSource.emitNamed('session.artifact', {
      type: 'session.artifact',
      payload: {
        id: 'artifact-2',
        title: 'KDE 最新运行清单',
        path: '/tmp/workspaces/session-1/run-manifest.json',
        analysis_type: 'kde',
        kind: 'manifest',
        description: '最新运行清单',
      },
    })
    eventSource.emitNamed('session.messages', {
      type: 'session.messages',
      payload: [
        { id: 'msg-user-1', role: 'user', agent: 'geo', created_at: '', parts: [{ type: 'text', text: 'Need a KDE run' }] },
        { id: 'msg-assistant-1', role: 'assistant', agent: 'geo', created_at: '', parts: [{ type: 'tool', tool: 'geospatial_record_run_evidence', state: { status: 'completed', input: { record_type: 'artifact', title: 'KDE 运行清单' }, meta: { tool_family: 'evidence', tool_label: '登记运行证据' }, output: '{"status":"completed"}' } }, { type: 'text', text: '已开始处理。' }] },
      ],
    })
    eventSource.emitNamed('session.attached_data_directories', {
      type: 'session.attached_data_directories',
      payload: [
        { id: 'dir-1', path: '/data/beijing-fcd', enabled: true, label: '默认数据目录' },
      ],
    })
    await flushPromises()

    expect(wrapper.text()).toContain('执行通用预处理')
    expect(wrapper.text()).toContain('进行中')
    expect(wrapper.text()).toContain('是否改用默认北京市区县边界继续执行？')
    expect(wrapper.text()).toContain('KDE 最新运行清单')
    expect(wrapper.text()).toContain('最新运行清单')
    expect(wrapper.text()).not.toContain('旧版运行清单')
    expect(wrapper.text()).toContain('Need a KDE run')
    expect(wrapper.text()).toContain('记录产物')
    expect(wrapper.text()).toContain('默认数据目录')
  })

  it('renders backend session issues from live SSE updates in the transcript', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ app: 'ready', runtime: { status: 'ready' } }) })
      .mockResolvedValueOnce({ ok: true, json: async () => [{ id: 'session-1', title: '北京 FCD KDE 会话', status: 'running', created_at: '', updated_at: '', workspace_path: '/tmp/workspaces/session-1' }] })
      .mockResolvedValueOnce({ ok: true, json: async () => sessionPayload('session-1', '北京 FCD KDE 会话', 'running') })

    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(App)
    await flushPromises()
    await wrapper.get('[data-testid="session-row-session-1"]').trigger('click')
    await flushPromises()

    FakeEventSource.instances[0].emitNamed('session.issue', {
      type: 'session.issue',
      payload: {
        id: 'issue-runtime-1',
        type: 'runtime_error',
        severity: 'error',
        source: 'runtime',
        title: '运行时执行失败',
        detail: 'runtime exploded',
        created_at: '2026-03-25T00:00:02+00:00',
        runtime_session_id: 'runtime-session-1',
        trace_path: 'runtime/trace.jsonl',
        recoverable: true,
      },
    })
    await flushPromises()

    const issue = wrapper.get('[data-testid="inline-issue-inline-issue-issue-runtime-1"]')
    expect(issue.text()).toContain('错误')
    expect(issue.text()).toContain('runtime exploded')
    expect(issue.text()).not.toContain('运行时执行失败')
    expect(issue.text()).not.toContain('运行时')
    expect(wrapper.find('[data-testid="issue-block-inline-issue-issue-runtime-1"]').exists()).toBe(false)
  })

  it('restores session issue notices for failed sessions without sidebar issue chrome', async () => {
    const failedSession = {
      ...sessionPayload('session-1', '北京 FCD KDE 会话', 'failed'),
      issues: [{
        id: 'issue-runtime-1',
        type: 'runtime_crash',
        severity: 'error',
        source: 'opencode',
        title: 'OpenCode 运行时异常退出',
        detail: 'OpenCode process exited',
        created_at: '2026-03-25T00:00:02+00:00',
        runtime_session_id: 'runtime-session-1',
        trace_path: 'runtime/trace.jsonl',
        recoverable: true,
      }],
    }
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ app: 'ready', runtime: { status: 'ready' } }) })
      .mockResolvedValueOnce({ ok: true, json: async () => [{ id: 'session-1', title: '北京 FCD KDE 会话', status: 'failed', created_at: '', updated_at: '', workspace_path: '/tmp/workspaces/session-1' }] })
      .mockResolvedValueOnce({ ok: true, json: async () => failedSession })

    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(App)
    await flushPromises()
    await wrapper.get('[data-testid="session-row-session-1"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('OpenCode process exited')
    expect(wrapper.find('[data-testid="interrupt-task-button"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="send-button-icon"]').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('最近问题')
  })

  it('renders frontend SSE disconnect as a local stream notice without failing the session', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ app: 'ready', runtime: { status: 'ready' } }) })
      .mockResolvedValueOnce({ ok: true, json: async () => [{ id: 'session-1', title: '北京 FCD KDE 会话', status: 'running', created_at: '', updated_at: '', workspace_path: '/tmp/workspaces/session-1' }] })
      .mockResolvedValueOnce({ ok: true, json: async () => sessionPayload('session-1', '北京 FCD KDE 会话', 'running') })

    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(App)
    await flushPromises()
    await wrapper.get('[data-testid="session-row-session-1"]').trigger('click')
    await flushPromises()

    FakeEventSource.instances[0].onerror?.()
    await flushPromises()

    expect(wrapper.text()).toContain('后台任务可能仍在继续')
    expect(wrapper.find('[data-testid="app-error"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="interrupt-task-button"]').exists()).toBe(true)
  })

  it('updates the sidebar from agent-owned plan group events', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ app: 'ready', runtime: { status: 'ready' } }) })
      .mockResolvedValueOnce({ ok: true, json: async () => [{ id: 'session-1', title: '多 agent 计划演示', status: 'running', created_at: '', updated_at: '', workspace_path: '/tmp/workspaces/session-1' }] })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          id: 'session-1',
          title: '多 agent 计划演示',
          status: 'running',
          messages: [],
          timeline: [],
          artifacts: [],
          plan: [],
          plan_groups: [],
          question: null,
          geospatial_task: null,
          verification: [],
          attached_data_directories: [],
          workspace_path: '/tmp/workspaces/session-1',
        }),
      })

    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(App)
    await flushPromises()

    await wrapper.get('[data-testid="session-row-session-1"]').trigger('click')
    await flushPromises()

    FakeEventSource.instances[0].emitNamed('session.plan_groups', {
      type: 'session.plan_groups',
      payload: [
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
          entries: [{ id: 'plan-1', label: '等待用户补齐轨迹目录', status: 'blocked' }],
        },
      ],
    })
    await flushPromises()

    expect(wrapper.text()).toContain('空间主理人')
    expect(wrapper.text()).toContain('空间整备师')
    expect(wrapper.text()).toContain('统筹角色协作')

    await wrapper.get('[data-testid="plan-group-tab-spatial-prep"]').trigger('click')

    expect(wrapper.text()).toContain('等待用户补齐轨迹目录')
    expect(wrapper.text()).toContain('已阻塞')
  })

  it('submits structured runtime question answers back through the question endpoint', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ app: 'ready', runtime: { status: 'ready' } }) })
      .mockResolvedValueOnce({ ok: true, json: async () => [{ id: 'session-1', title: '北京 FCD KDE 会话', status: 'waiting_for_input', created_at: '', updated_at: '', workspace_path: '/tmp/workspaces/session-1' }] })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          id: 'session-1',
          title: '北京 FCD KDE 会话',
          status: 'waiting_for_input',
          messages: [
            {
              id: 'msg-question-1',
              role: 'system',
              agent: 'geo',
              created_at: '',
              parts: [
                {
                  type: 'question',
                  text: '请选择研究区范围',
                  state: {
                    id: 'question-request-1',
                    prompt: '请选择研究区范围',
                    source: 'runtime',
                    questions: [
                      {
                        header: '研究区',
                        question: '请选择研究区范围',
                        options: [
                          { label: '使用默认北京市区县边界', description: '使用系统默认行政区边界继续执行' },
                        ],
                      },
                    ],
                  },
                },
              ],
            },
          ],
          timeline: [],
          artifacts: [],
          plan: [],
          question: {
            id: 'question-request-1',
            prompt: '请选择研究区范围',
            source: 'runtime',
            questions: [
              {
                header: '研究区',
                question: '请选择研究区范围',
                options: [
                  { label: '使用默认北京市区县边界', description: '使用系统默认行政区边界继续执行' },
                ],
              },
            ],
          },
          geospatial_task: null,
          verification: [],
          attached_data_directories: [],
          workspace_path: '/tmp/workspaces/session-1',
        }),
      })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ accepted: true }) })

    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(App)
    await flushPromises()

    await wrapper.get('[data-testid="session-row-session-1"]').trigger('click')
    await flushPromises()

    await wrapper.get('[data-testid="structured-question-option-0-0"]').trigger('click')
    await flushPromises()

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/sessions/session-1/questions/question-request-1/answers',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ answers: ['使用默认北京市区县边界'] }),
      }),
    )
    expect(wrapper.get('[data-testid="message-agent-label-msg-question-1"]').text()).toBe('空间主理人')
  })

  it('shows verification evidence for restored sessions even when older data has no inline verification message yet', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ app: 'ready', runtime: { status: 'ready' } }) })
      .mockResolvedValueOnce({ ok: true, json: async () => [{ id: 'session-1', title: '北京 FCD KDE 会话', status: 'completed', created_at: '', updated_at: '', workspace_path: '/tmp/workspaces/session-1' }] })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          id: 'session-1',
          title: '北京 FCD KDE 会话',
          status: 'completed',
          messages: [
            { id: 'msg-user-1', role: 'user', agent: 'geo', created_at: '', parts: [{ type: 'text', text: 'Need a KDE run' }] },
          ],
          timeline: [],
          artifacts: [],
          plan: [],
          question: null,
          geospatial_task: null,
          verification: [{ id: 'verification-1', code: 'crs_mismatch_detected', title: '检测到 CRS 不一致', status: 'warning', detail: '需要统一到 EPSG:32650。' }],
          attached_data_directories: [],
          workspace_path: '/tmp/workspaces/session-1',
        }),
      })

    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(App)
    await flushPromises()

    await wrapper.get('[data-testid="session-row-session-1"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('检测到 CRS 不一致')
    expect(wrapper.text()).toContain('警告')
    expect(wrapper.get('[data-testid="message-agent-label-restored-verification-session-1"]').text()).toBe('结果审查官')
  })

  it('merges streamed assistant updates without showing a recent-activity sidebar panel', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ app: 'ready', runtime: { status: 'ready' } }) })
      .mockResolvedValueOnce({ ok: true, json: async () => [{ id: 'session-1', title: '北京 FCD KDE 会话', status: 'running', created_at: '', updated_at: '', workspace_path: '/tmp/workspaces/session-1' }] })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          id: 'session-1',
          title: '北京 FCD KDE 会话',
          status: 'running',
          messages: [],
          timeline: [],
          artifacts: [],
          plan: [],
          question: null,
          geospatial_task: null,
          verification: [],
          attached_data_directories: [],
          workspace_path: '/tmp/workspaces/session-1',
        }),
      })

    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(App)
    await flushPromises()

    await wrapper.get('[data-testid="session-row-session-1"]').trigger('click')
    await flushPromises()

    const eventSource = FakeEventSource.instances[0]
    eventSource.emitNamed('session.message_delta', {
      type: 'session.message_delta',
      payload: {
        id: 'msg-assistant-1',
        role: 'assistant',
        agent: 'geo',
        created_at: '',
        parts: [{ type: 'text', text: '正在分析北京 FCD 数据' }],
      },
    })
    eventSource.emitNamed('session.timeline_entry', {
      type: 'session.timeline_entry',
      payload: {
        id: 'timeline-1',
        kind: 'status',
        text: '已启动通用预处理工具',
        created_at: '',
      },
    })
    eventSource.emitNamed('session.message_delta', {
      type: 'session.message_delta',
      payload: {
        id: 'msg-assistant-1',
        role: 'assistant',
        agent: 'geo',
        created_at: '',
        parts: [{ type: 'text', text: '正在分析北京 FCD 数据\n\n已完成 KDE 算子。' }],
      },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('正在分析北京 FCD 数据')
    expect(wrapper.text()).toContain('已完成 KDE 算子。')
    expect(wrapper.text()).not.toContain('最近活动')
  })

  it('excludes question replies from composer prompt history inside the current session', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ app: 'ready', runtime: { status: 'ready' } }) })
      .mockResolvedValueOnce({ ok: true, json: async () => [{ id: 'session-1', title: '北京 FCD KDE 会话', status: 'completed', created_at: '', updated_at: '', workspace_path: '/tmp/workspaces/session-1' }] })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          id: 'session-1',
          title: '北京 FCD KDE 会话',
          status: 'completed',
          messages: [
            { id: 'msg-user-1', role: 'user', agent: 'geo', created_at: '', parts: [{ type: 'text', text: 'Need a KDE run' }] },
            { id: 'msg-question-1', role: 'system', agent: 'geo', created_at: '', parts: [{ type: 'question', text: '是否改用默认北京市区县边界继续执行？', state: { id: 'question-1', prompt: '是否改用默认北京市区县边界继续执行？' } }] },
            { id: 'msg-user-2', role: 'user', agent: 'geo', created_at: '', parts: [{ type: 'text', text: '继续执行', state: { history_excluded: true, question_id: 'question-1' } }] },
          ],
          timeline: [],
          artifacts: [],
          plan: [],
          question: null,
          geospatial_task: null,
          verification: [],
          attached_data_directories: [],
          workspace_path: '/tmp/workspaces/session-1',
        }),
      })

    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(App)
    await flushPromises()

    await wrapper.get('[data-testid="session-row-session-1"]').trigger('click')
    await flushPromises()

    const input = wrapper.get('[data-testid="message-input"]').element as HTMLTextAreaElement
    input.selectionStart = 0
    input.selectionEnd = 0
    await wrapper.get('[data-testid="message-input"]').trigger('keydown', { key: 'ArrowUp' })
    await flushPromises()

    expect(input.value).toBe('Need a KDE run')
  })

  it('opens the workspace from the composer action row', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ app: 'ready', runtime: { status: 'ready' } }) })
      .mockResolvedValueOnce({ ok: true, json: async () => [{ id: 'session-1', title: '北京 FCD KDE 会话', status: 'running', created_at: '', updated_at: '', workspace_path: '/tmp/workspaces/session-1', attached_data_directories: [{ id: 'dir-1', path: '/data/beijing-fcd', enabled: true, label: '默认数据目录' }] }] })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          id: 'session-1',
          title: '北京 FCD KDE 会话',
          status: 'running',
          messages: [],
          timeline: [],
          artifacts: [],
          plan: [],
          question: null,
          geospatial_task: null,
          verification: [],
          attached_data_directories: [{ id: 'dir-1', path: '/data/beijing-fcd-updated', enabled: true, label: '默认数据目录' }],
          workspace_path: '/tmp/workspaces/session-1',
        }),
      })
      .mockResolvedValueOnce({ ok: true, text: async () => '' })

    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(App)
    await flushPromises()
    await wrapper.get('[data-testid="session-row-session-1"]').trigger('click')
    await flushPromises()

    await wrapper.get('[data-testid="composer-open-workspace"]').trigger('click')
    await flushPromises()

    expect(fetchMock).toHaveBeenCalledWith('/api/sessions/session-1/workspace/open', expect.objectContaining({ method: 'POST' }))
  })

  it('keeps a draft user message visible immediately while the first request is still in flight', async () => {
    let resolveSubmit!: (value: { ok: true, json: () => Promise<{ accepted: true, question: null }> }) => void
    const submitPromise = new Promise<{ ok: true, json: () => Promise<{ accepted: true, question: null }> }>((resolve) => {
      resolveSubmit = resolve
    })

    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ app: 'ready', runtime: { status: 'ready' } }) })
      .mockResolvedValueOnce({ ok: true, json: async () => [] })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ id: 'session-1', title: '新建会话 1', status: 'idle', messages: [], timeline: [], artifacts: [], plan: [], question: null, geospatial_task: null, verification: [], attached_data_directories: [], workspace_path: '/tmp/workspaces/session-1' }) })
      .mockResolvedValueOnce({ ok: true, json: async () => [{ id: 'session-1', title: '新建会话 1', status: 'idle', created_at: '', updated_at: '', workspace_path: '/tmp/workspaces/session-1', attached_data_directories: [] }] })
      .mockImplementationOnce(() => submitPromise)
      .mockResolvedValueOnce({ ok: true, json: async () => ({ id: 'session-1', title: '新建会话 1', status: 'running', messages: [{ id: 'msg-user-1', role: 'user', agent: 'geo', created_at: '', parts: [{ type: 'text', text: 'Need a KDE run now' }] }], timeline: [], artifacts: [], plan: [], question: null, geospatial_task: null, verification: [], attached_data_directories: [], workspace_path: '/tmp/workspaces/session-1' }) })

    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(App)
    await flushPromises()

    await wrapper.get('[data-testid="message-input"]').setValue('Need a KDE run now')
    await wrapper.get('[data-testid="send-message"]').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain('Need a KDE run now')

    resolveSubmit({ ok: true, json: async () => ({ accepted: true, question: null }) })
    await flushPromises()
  })

  it('calls the interrupt endpoint for a running session and returns the composer to send mode after SSE status update', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ app: 'ready', runtime: { status: 'ready' } }) })
      .mockResolvedValueOnce({ ok: true, json: async () => [{ id: 'session-1', title: '北京 FCD KDE 会话', status: 'running', created_at: '', updated_at: '', workspace_path: '/tmp/workspaces/session-1', attached_data_directories: [] }] })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          id: 'session-1',
          title: '北京 FCD KDE 会话',
          status: 'running',
          messages: [],
          timeline: [],
          artifacts: [],
          plan: [],
          question: null,
          geospatial_task: null,
          verification: [],
          attached_data_directories: [],
          workspace_path: '/tmp/workspaces/session-1',
        }),
      })
      .mockResolvedValueOnce({ ok: true, text: async () => '' })

    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(App)
    await flushPromises()
    await wrapper.get('[data-testid="session-row-session-1"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="interrupt-task-button"]').exists()).toBe(true)

    await wrapper.get('[data-testid="interrupt-task-button"]').trigger('click')
    await flushPromises()

    expect(fetchMock).toHaveBeenCalledWith('/api/sessions/session-1/interrupt', expect.objectContaining({ method: 'POST' }))

    FakeEventSource.instances[0].emitNamed('session.status', {
      type: 'session.status',
      payload: { status: 'idle' },
    })
    await flushPromises()

    expect(wrapper.find('[data-testid="interrupt-task-button"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="send-button-icon"]').exists()).toBe(true)
  })

  it('re-enables the interrupt control when the interrupt request fails', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ app: 'ready', runtime: { status: 'ready' } }) })
      .mockResolvedValueOnce({ ok: true, json: async () => [{ id: 'session-1', title: '北京 FCD KDE 会话', status: 'running', created_at: '', updated_at: '', workspace_path: '/tmp/workspaces/session-1', attached_data_directories: [] }] })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          id: 'session-1',
          title: '北京 FCD KDE 会话',
          status: 'running',
          messages: [],
          timeline: [],
          artifacts: [],
          plan: [],
          question: null,
          geospatial_task: null,
          verification: [],
          attached_data_directories: [],
          workspace_path: '/tmp/workspaces/session-1',
        }),
      })
      .mockResolvedValueOnce({ ok: false, text: async () => JSON.stringify({ detail: 'interrupt failed' }) })

    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(App)
    await flushPromises()
    await wrapper.get('[data-testid="session-row-session-1"]').trigger('click')
    await flushPromises()

    await wrapper.get('[data-testid="interrupt-task-button"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-testid="interrupt-task-button"]').attributes('disabled')).toBeUndefined()
  })

  it('preserves the draft text across an interrupt round trip', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ app: 'ready', runtime: { status: 'ready' } }) })
      .mockResolvedValueOnce({ ok: true, json: async () => [{ id: 'session-1', title: '北京 FCD KDE 会话', status: 'running', created_at: '', updated_at: '', workspace_path: '/tmp/workspaces/session-1', attached_data_directories: [] }] })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          id: 'session-1',
          title: '北京 FCD KDE 会话',
          status: 'running',
          messages: [],
          timeline: [],
          artifacts: [],
          plan: [],
          question: null,
          geospatial_task: null,
          verification: [],
          attached_data_directories: [],
          workspace_path: '/tmp/workspaces/session-1',
        }),
      })
      .mockResolvedValueOnce({ ok: true, text: async () => '' })

    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(App)
    await flushPromises()
    await wrapper.get('[data-testid="session-row-session-1"]').trigger('click')
    await flushPromises()

    await wrapper.get('[data-testid="message-input"]').setValue('interrupt 后继续执行')
    await wrapper.get('[data-testid="interrupt-task-button"]').trigger('click')
    await flushPromises()

    FakeEventSource.instances[0].emitNamed('session.status', {
      type: 'session.status',
      payload: { status: 'idle' },
    })
    await flushPromises()

    expect((wrapper.get('[data-testid="message-input"]').element as HTMLTextAreaElement).value).toBe('interrupt 后继续执行')
    expect(wrapper.find('[data-testid="send-button-icon"]').exists()).toBe(true)
  })

  it('collapses overlapping draft attachments to the parent directory immediately', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ app: 'ready', runtime: { status: 'ready' } }) })
      .mockResolvedValueOnce({ ok: true, json: async () => [] })
      .mockResolvedValueOnce({ ok: true, text: async () => JSON.stringify({ items: [{ id: 'dir-child', path: '/data/root/nested', enabled: true, label: '子目录' }] }) })
      .mockResolvedValueOnce({ ok: true, text: async () => JSON.stringify({ items: [{ id: 'dir-parent', path: '/data/root', enabled: true, label: '父目录' }] }) })

    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(App)
    await flushPromises()

    await wrapper.get('[data-testid="composer-attach-trigger"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="recent-directory-dir-child"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('子目录')

    await wrapper.get('[data-testid="composer-attach-trigger"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="recent-directory-dir-parent"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('父目录')
    expect(wrapper.text()).not.toContain('子目录')
  })

  it('opens and removes attached directories from composer chips', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ app: 'ready', runtime: { status: 'ready' } }) })
      .mockResolvedValueOnce({ ok: true, json: async () => [{ id: 'session-1', title: '北京 FCD KDE 会话', status: 'running', created_at: '', updated_at: '', workspace_path: '/tmp/workspaces/session-1', attached_data_directories: [{ id: 'dir-1', path: '/data/root', enabled: true, label: '默认数据目录' }] }] })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          id: 'session-1',
          title: '北京 FCD KDE 会话',
          status: 'running',
          messages: [],
          timeline: [],
          artifacts: [],
          plan: [],
          question: null,
          geospatial_task: null,
          verification: [],
          attached_data_directories: [{ id: 'dir-1', path: '/data/root', enabled: true, label: '默认数据目录' }],
          workspace_path: '/tmp/workspaces/session-1',
        }),
      })
      .mockResolvedValueOnce({ ok: true, text: async () => '' })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          id: 'session-1',
          title: '北京 FCD KDE 会话',
          status: 'running',
          messages: [],
          timeline: [],
          artifacts: [],
          plan: [],
          question: null,
          geospatial_task: null,
          verification: [],
          attached_data_directories: [],
          workspace_path: '/tmp/workspaces/session-1',
        }),
      })

    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(App)
    await flushPromises()
    await wrapper.get('[data-testid="session-row-session-1"]').trigger('click')
    await flushPromises()

    await wrapper.get('[data-testid="attached-directory-open-dir-1"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="attached-directory-remove-dir-1"]').trigger('click')
    await flushPromises()

    expect(fetchMock).toHaveBeenCalledWith('/api/data-directories/open', expect.objectContaining({ method: 'POST' }))
    expect(fetchMock).toHaveBeenCalledWith('/api/sessions/session-1/data-directories', expect.objectContaining({ method: 'PUT' }))
    expect(wrapper.text()).not.toContain('默认数据目录')
  })

  it('imports a session archive as a read-only transcript with artifact actions disabled', async () => {
    const importedSession = {
      id: 'imported-session-1',
      title: '北京 FCD KDE 会话',
      status: 'completed',
      read_only: true,
      archive_metadata: { schema: 'geo-agent.session-archive.v1' },
      messages: [{ id: 'msg-user-1', role: 'user', agent: 'geo', created_at: '', parts: [{ type: 'text', text: 'Need a KDE run' }] }],
      timeline: [],
      artifacts: [{ id: 'artifact-1', title: 'KDE 热点图', path: 'outputs/kde.png', kind: 'map', display_hint: 'image', artifact_stage: 'final' }],
      plan: [],
      plan_groups: [],
      issues: [],
      question: null,
      geospatial_task: null,
      verification: [],
      attached_data_directories: [],
      workspace_path: null,
      runtime_session_id: null,
      runtime_trace_path: null,
    }
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ app: 'ready', runtime: { status: 'ready' } }) })
      .mockResolvedValueOnce({ ok: true, json: async () => [] })
      .mockResolvedValueOnce({ ok: true, text: async () => JSON.stringify(importedSession) })
      .mockResolvedValueOnce({ ok: true, json: async () => [{ id: 'imported-session-1', title: '北京 FCD KDE 会话', status: 'completed', read_only: true, created_at: '', updated_at: '', workspace_path: null }] })

    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(App)
    await flushPromises()

    const file = new File([JSON.stringify({ schema: 'geo-agent.session-archive.v1' })], 'archive.json', { type: 'application/json' })
    const input = wrapper.get('[data-testid="import-session-archive-input"]').element as HTMLInputElement
    Object.defineProperty(input, 'files', { value: [file] })
    await wrapper.get('[data-testid="import-session-archive-input"]').trigger('change')
    await flushPromises()

    const importCall = fetchMock.mock.calls.find(([url]) => url === '/api/session-archives/import')
    expect(importCall?.[1]).toMatchObject({ method: 'POST' })
    expect(JSON.parse(String(importCall?.[1]?.body)).archive.schema).toBe('geo-agent.session-archive.v1')
    expect(wrapper.text()).toContain('只读归档')
    expect(wrapper.text()).toContain('Need a KDE run')
    expect(wrapper.find('[data-testid="composer-overlay"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="composer-shell"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="message-input"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="composer-open-workspace"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="final-artifact-preview-artifact-1"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="final-artifact-open-artifact-1"]').exists()).toBe(false)
  })

  it('exports the active session archive from the current session menu', async () => {
    const createObjectUrl = vi.fn(() => 'blob:archive')
    const revokeObjectUrl = vi.fn()
    vi.stubGlobal('URL', { ...URL, createObjectURL: createObjectUrl, revokeObjectURL: revokeObjectUrl })
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ app: 'ready', runtime: { status: 'ready' } }) })
      .mockResolvedValueOnce({ ok: true, json: async () => [{ id: 'session-1', title: '北京 FCD KDE 会话', status: 'completed', created_at: '', updated_at: '', workspace_path: '/tmp/workspaces/session-1' }] })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          id: 'session-1',
          title: '北京 FCD KDE 会话',
          status: 'completed',
          messages: [],
          timeline: [],
          artifacts: [],
          plan: [],
          plan_groups: [],
          issues: [],
          question: null,
          geospatial_task: null,
          verification: [],
          attached_data_directories: [],
          workspace_path: '/tmp/workspaces/session-1',
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        blob: async () => new Blob([JSON.stringify({ schema: 'geo-agent.session-archive.v1' })], { type: 'application/json' }),
        headers: new Headers({ 'content-disposition': 'attachment; filename="geo-agent-session-session-1.json"' }),
      })

    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(App)
    await flushPromises()
    await wrapper.get('[data-testid="session-row-session-1"]').trigger('click')
    await flushPromises()

    await wrapper.get('[data-testid="active-session-actions-session-1"]').trigger('click')
    await wrapper.get('[data-testid="menu-export-session-1"]').trigger('click')
    await flushPromises()

    expect(fetchMock).toHaveBeenCalledWith('/api/sessions/session-1/archive', expect.any(Object))
    expect(createObjectUrl).toHaveBeenCalled()
    expect(revokeObjectUrl).toHaveBeenCalledWith('blob:archive')
  })
})
