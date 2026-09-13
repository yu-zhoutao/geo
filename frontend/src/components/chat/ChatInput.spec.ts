import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { flushPromises } from '@vue/test-utils'

import ChatInput from './ChatInput.vue'

function setTextareaCursorToEnd(wrapper: ReturnType<typeof mount>): void {
  const input = wrapper.get('[data-testid="message-input"]').element as HTMLTextAreaElement
  input.selectionStart = input.value.length
  input.selectionEnd = input.value.length
}

function setTextareaCursorToStart(wrapper: ReturnType<typeof mount>): void {
  const input = wrapper.get('[data-testid="message-input"]').element as HTMLTextAreaElement
  input.selectionStart = 0
  input.selectionEnd = 0
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


describe('ChatInput', () => {
  it('renders the updated send icon without text label clutter', () => {
    const wrapper = mount(ChatInput, {
      props: {
        disabled: false,
        isDraft: false,
        activeQuestion: null,
        attachedDataDirectories: [],
        workspacePath: null,
      },
    })

    expect(wrapper.find('[data-testid="send-button-icon"]').exists()).toBe(true)
  })

  it('uses the refined composer surface without a top divider', () => {
    const wrapper = mount(ChatInput, {
      props: {
        disabled: false,
        isDraft: false,
        activeQuestion: null,
        attachedDataDirectories: [],
        workspacePath: null,
      },
    })

    expect(wrapper.get('[data-testid="composer-shell"]').classes()).toContain('bg-transparent')
    expect(wrapper.get('[data-testid="send-message"]').classes()).toContain('pointer-events-auto')
    expect(wrapper.get('[data-testid="message-input"]').classes()).toContain('bg-transparent')
    expect(wrapper.get('[data-testid="message-input"]').attributes('rows')).toBe('1')
    expect(wrapper.get('[data-testid="message-input"]').classes()).toContain('overflow-y-auto')
    expect(wrapper.find('div').classes().join(' ')).not.toContain('border-t')
  })

  it('keeps the composer neutral while a question is pending', () => {
    const wrapper = mount(ChatInput, {
      props: {
        disabled: false,
        isDraft: false,
        activeQuestion: {
          id: 'question-1',
          prompt: '请确认研究区范围。',
        },
        attachedDataDirectories: [],
        workspacePath: null,
      },
    })

    expect(wrapper.find('[data-testid="composer-question-chip"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="message-input"]').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).not.toContain('请确认研究区范围。')
  })

  it('keeps structured runtime questions out of the composer surface', async () => {
    const wrapper = mount(ChatInput, {
      props: {
        disabled: false,
        isDraft: false,
        activeQuestion: {
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
            {
              header: '输出语言',
              question: '最终报告使用什么语言？',
              options: [
                { label: '中文', description: '使用简体中文生成最终结果' },
              ],
            },
          ],
        },
        attachedDataDirectories: [],
        workspacePath: null,
      } as never,
    })

    expect(wrapper.find('[data-testid="structured-question-card"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="composer-question-chip"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="message-input"]').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).not.toContain('使用默认北京市区县边界')
    expect(wrapper.text()).not.toContain('最终报告使用什么语言？')
  })

  it('loads recent directories into the composer attachment menu', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        text: async () => JSON.stringify({
          items: [{ id: 'dir-1', path: '/data/beijing-fcd', enabled: true, label: '北京 FCD' }],
        }),
      }),
    )

    const wrapper = mount(ChatInput, {
      props: {
        disabled: false,
        isDraft: true,
        activeQuestion: null,
        attachedDataDirectories: [],
        workspacePath: null,
      },
    })

    await wrapper.get('[data-testid="composer-attach-trigger"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="composer-attach-menu"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('北京 FCD')
    vi.unstubAllGlobals()
  })

  it('opens a directory browser modal from the attachment dropdown', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce({
          ok: true,
          text: async () => JSON.stringify({ items: [] }),
        })
        .mockResolvedValueOnce({
          ok: true,
          text: async () => JSON.stringify({
            current_path: '/tmp/workspaces',
            parent_path: '/tmp',
            home_path: '/Users/jingbh',
            cwd_path: '/Users/jingbh/learning-code/geo-agent',
            entries: [{ name: 'inputs', path: '/tmp/workspaces/inputs', is_dir: true }],
          }),
        }),
    )

    const wrapper = mount(ChatInput, {
      attachTo: document.body,
      props: {
        disabled: false,
        isDraft: true,
        activeQuestion: null,
        attachedDataDirectories: [],
        workspacePath: null,
      },
    })

    await wrapper.get('[data-testid="composer-attach-trigger"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="composer-open-browser"]').trigger('click')
    await flushPromises()

    expect(document.body.querySelector('[data-testid="composer-directory-modal"]')).not.toBeNull()
    expect(document.body.textContent).toContain('inputs')
    expect(document.body.querySelector('[data-testid="directory-shortcut-home"]')).not.toBeNull()
    expect(document.body.querySelector('[data-testid="directory-shortcut-cwd"]')).not.toBeNull()
    expect(document.body.querySelector('[data-testid="directory-path-display"]')).not.toBeNull()
    expect(document.body.querySelector('[data-testid="directory-cancel"]')).not.toBeNull()
    expect(document.body.querySelector('[data-testid="directory-select-current"]')).not.toBeNull()
    wrapper.unmount()
    vi.unstubAllGlobals()
  })

  it('navigates into a directory row and uses an explicit action to attach the current directory', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        text: async () => JSON.stringify({ items: [] }),
      })
      .mockResolvedValueOnce({
        ok: true,
        text: async () => JSON.stringify({
          current_path: '/tmp/workspaces',
          parent_path: '/tmp',
          home_path: '/Users/jingbh',
          cwd_path: '/Users/jingbh/learning-code/geo-agent',
          entries: [{ name: 'inputs', path: '/tmp/workspaces/inputs', is_dir: true }],
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        text: async () => JSON.stringify({
          current_path: '/tmp/workspaces/inputs',
          parent_path: '/tmp/workspaces',
          home_path: '/Users/jingbh',
          cwd_path: '/Users/jingbh/learning-code/geo-agent',
          entries: [{ name: 'points', path: '/tmp/workspaces/inputs/points', is_dir: true }],
        }),
      })

    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(ChatInput, {
      attachTo: document.body,
      props: {
        disabled: false,
        isDraft: true,
        activeQuestion: null,
        attachedDataDirectories: [],
        workspacePath: null,
      },
    })

    await wrapper.get('[data-testid="composer-attach-trigger"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="composer-open-browser"]').trigger('click')
    await flushPromises()

    ;(document.body.querySelector('[data-testid="browser-directory-inputs"]') as HTMLElement).click()
    await flushPromises()

    expect(fetchMock).toHaveBeenCalledWith('/api/data-directories/browser?path=%2Ftmp%2Fworkspaces%2Finputs', expect.any(Object))
    expect(document.body.textContent).toContain('points')
    expect(wrapper.emitted('attach-directory')).toBeUndefined()

    ;(document.body.querySelector('[data-testid="directory-select-current"]') as HTMLElement).click()

    expect(wrapper.emitted('attach-directory')).toEqual([[{ path: '/tmp/workspaces/inputs', label: 'inputs' }]])
    wrapper.unmount()
    vi.unstubAllGlobals()
  })

  it('dismisses the attachment dropdown with escape', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        text: async () => JSON.stringify({ items: [{ id: 'dir-1', path: '/data/beijing-fcd', enabled: true, label: '北京 FCD' }] }),
      }),
    )

    const wrapper = mount(ChatInput, {
      attachTo: document.body,
      props: {
        disabled: false,
        isDraft: true,
        activeQuestion: null,
        attachedDataDirectories: [],
        workspacePath: null,
      },
    })

    await wrapper.get('[data-testid="composer-attach-trigger"]').trigger('click')
    await flushPromises()
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await flushPromises()

    expect(wrapper.find('[data-testid="composer-attach-menu"]').exists()).toBe(false)
    wrapper.unmount()
    vi.unstubAllGlobals()
  })

  it('dismisses the directory browser modal with escape', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce({
          ok: true,
          text: async () => JSON.stringify({ items: [] }),
        })
        .mockResolvedValueOnce({
          ok: true,
          text: async () => JSON.stringify({
            current_path: '/tmp/workspaces',
            parent_path: '/tmp',
            home_path: '/Users/jingbh',
            cwd_path: '/Users/jingbh/learning-code/geo-agent',
            entries: [{ name: 'inputs', path: '/tmp/workspaces/inputs', is_dir: true }],
          }),
        }),
    )

    const wrapper = mount(ChatInput, {
      attachTo: document.body,
      props: {
        disabled: false,
        isDraft: true,
        activeQuestion: null,
        attachedDataDirectories: [],
        workspacePath: null,
      },
    })

    await wrapper.get('[data-testid="composer-attach-trigger"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="composer-open-browser"]').trigger('click')
    await flushPromises()
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await flushPromises()

    expect(document.body.querySelector('[data-testid="composer-directory-modal"]')).toBeNull()
    wrapper.unmount()
    vi.unstubAllGlobals()
  })

  it('dismisses the directory browser modal with the footer cancel button', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce({
          ok: true,
          text: async () => JSON.stringify({ items: [] }),
        })
        .mockResolvedValueOnce({
          ok: true,
          text: async () => JSON.stringify({
            current_path: '/tmp/workspaces',
            parent_path: '/tmp',
            home_path: '/Users/jingbh',
            cwd_path: '/Users/jingbh/learning-code/geo-agent',
            entries: [{ name: 'inputs', path: '/tmp/workspaces/inputs', is_dir: true }],
          }),
        }),
    )

    const wrapper = mount(ChatInput, {
      attachTo: document.body,
      props: {
        disabled: false,
        isDraft: true,
        activeQuestion: null,
        attachedDataDirectories: [],
        workspacePath: null,
      },
    })

    await wrapper.get('[data-testid="composer-attach-trigger"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="composer-open-browser"]').trigger('click')
    await flushPromises()
    ;(document.body.querySelector('[data-testid="directory-cancel"]') as HTMLElement).click()
    await flushPromises()

    expect(document.body.querySelector('[data-testid="composer-directory-modal"]')).toBeNull()
    wrapper.unmount()
    vi.unstubAllGlobals()
  })

  it('uses command or control enter as a send shortcut', async () => {
    const wrapper = mount(ChatInput, {
      props: {
        disabled: false,
        isDraft: false,
        sessionStatus: 'idle',
        activeQuestion: null,
        attachedDataDirectories: [],
        workspacePath: null,
      },
    })

    await wrapper.get('[data-testid="message-input"]').setValue('Run with shortcut')
    await wrapper.get('[data-testid="message-input"]').trigger('keydown', { key: 'Enter', metaKey: true })

    expect(wrapper.emitted('send-message')).toEqual([['Run with shortcut']])
  })

  it('shows an interrupt action while the session is running and allows interrupt without draft text', async () => {
    const wrapper = mount(ChatInput, {
      props: {
        disabled: false,
        isDraft: false,
        sessionStatus: 'running',
        activeQuestion: null,
        attachedDataDirectories: [],
        workspacePath: null,
      },
    })

    expect(wrapper.find('[data-testid="send-button-icon"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="interrupt-task-button"]').text()).toBe('')
    expect(wrapper.get('[data-testid="interrupt-task-button"]').classes()).toContain('w-10')

    await wrapper.get('[data-testid="interrupt-task-button"]').trigger('click')

    expect(wrapper.emitted('interrupt-task')).toEqual([[]])
  })

  it('does not send the draft with enter while the session is running', async () => {
    const wrapper = mount(ChatInput, {
      props: {
        disabled: false,
        isDraft: false,
        sessionStatus: 'running',
        activeQuestion: null,
        attachedDataDirectories: [],
        workspacePath: null,
      },
    })

    await wrapper.get('[data-testid="message-input"]').setValue('follow-up draft')
    await wrapper.get('[data-testid="message-input"]').trigger('keydown', { key: 'Enter' })
    await flushPromises()

    expect(wrapper.emitted('send-message')).toBeUndefined()
    expect((wrapper.get('[data-testid="message-input"]').element as HTMLTextAreaElement).value).toBe('follow-up draft')
  })

  it('does not submit while Chinese IME composition is still active', async () => {
    const wrapper = mount(ChatInput, {
      props: {
        disabled: false,
        isDraft: false,
        sessionStatus: 'idle',
        activeQuestion: null,
        attachedDataDirectories: [],
        workspacePath: null,
      },
    })

    const input = wrapper.get('[data-testid="message-input"]')
    await input.setValue('北京市')
    await input.trigger('compositionstart')
    await input.trigger('keydown', { key: 'Enter', isComposing: true })

    expect(wrapper.emitted('send-message')).toBeUndefined()
    expect((input.element as HTMLTextAreaElement).value).toBe('北京市')

    await input.trigger('compositionend')
    await input.trigger('keydown', { key: 'Enter' })

    expect(wrapper.emitted('send-message')).toEqual([['北京市']])
  })

  it('cycles through recent user messages with arrow up and arrow down', async () => {
    const wrapper = mount(ChatInput, {
      props: {
        disabled: false,
        isDraft: false,
        activeQuestion: null,
        attachedDataDirectories: [],
        workspacePath: null,
        recentMessages: ['first prompt', 'second prompt'],
      },
    })

    await wrapper.get('[data-testid="message-input"]').setValue('draft text')
    setTextareaCursorToStart(wrapper)
    await wrapper.get('[data-testid="message-input"]').trigger('keydown', { key: 'ArrowUp' })
    await flushPromises()
    expect((wrapper.get('[data-testid="message-input"]').element as HTMLTextAreaElement).value).toBe('second prompt')

    setTextareaCursorToStart(wrapper)
    await wrapper.get('[data-testid="message-input"]').trigger('keydown', { key: 'ArrowUp' })
    await flushPromises()
    expect((wrapper.get('[data-testid="message-input"]').element as HTMLTextAreaElement).value).toBe('first prompt')

    const input = wrapper.get('[data-testid="message-input"]').element as HTMLTextAreaElement
    input.selectionStart = input.value.length
    input.selectionEnd = input.value.length
    await wrapper.get('[data-testid="message-input"]').trigger('keydown', { key: 'ArrowDown' })
    await flushPromises()
    expect(input.value).toBe('second prompt')

    input.selectionStart = input.value.length
    input.selectionEnd = input.value.length
    await wrapper.get('[data-testid="message-input"]').trigger('keydown', { key: 'ArrowDown' })
    await flushPromises()
    expect(input.value).toBe('draft text')
  })

  it('does not hijack arrow history when the caret is not at the boundary', async () => {
    const wrapper = mount(ChatInput, {
      props: {
        disabled: false,
        isDraft: false,
        activeQuestion: null,
        attachedDataDirectories: [],
        workspacePath: null,
        recentMessages: ['first prompt'],
      },
    })

    await wrapper.get('[data-testid="message-input"]').setValue('draft text')
    const input = wrapper.get('[data-testid="message-input"]').element as HTMLTextAreaElement
    input.selectionStart = 3
    input.selectionEnd = 3
    await wrapper.get('[data-testid="message-input"]').trigger('keydown', { key: 'ArrowUp' })
    await flushPromises()

    expect(input.value).toBe('draft text')
  })

  it('persists submitted prompt history across remounts', async () => {
    const storage = createFakeStorage()
    vi.stubGlobal('localStorage', storage)

    const firstWrapper = mount(ChatInput, {
      props: {
        disabled: false,
        isDraft: true,
        activeQuestion: null,
        attachedDataDirectories: [],
        workspacePath: null,
      },
    })

    await firstWrapper.get('[data-testid="message-input"]').setValue('persisted prompt')
    await firstWrapper.get('[data-testid="send-message"]').trigger('submit')
    firstWrapper.unmount()

    const secondWrapper = mount(ChatInput, {
      props: {
        disabled: false,
        isDraft: true,
        activeQuestion: null,
        attachedDataDirectories: [],
        workspacePath: null,
      },
    })

    setTextareaCursorToStart(secondWrapper)
    await secondWrapper.get('[data-testid="message-input"]').trigger('keydown', { key: 'ArrowUp' })
    await flushPromises()

    expect((secondWrapper.get('[data-testid="message-input"]').element as HTMLTextAreaElement).value).toBe('persisted prompt')
    secondWrapper.unmount()
    vi.unstubAllGlobals()
  })

  it('does not persist question replies into prompt history', async () => {
    const storage = createFakeStorage()
    vi.stubGlobal('localStorage', storage)

    const firstWrapper = mount(ChatInput, {
      props: {
        disabled: false,
        isDraft: false,
        activeQuestion: {
          id: 'question-1',
          prompt: '是否继续执行？',
        },
        attachedDataDirectories: [],
        workspacePath: null,
      },
    })

    await firstWrapper.get('[data-testid="message-input"]').setValue('继续执行')
    await firstWrapper.get('[data-testid="send-message"]').trigger('submit')
    firstWrapper.unmount()

    const secondWrapper = mount(ChatInput, {
      props: {
        disabled: false,
        isDraft: true,
        activeQuestion: null,
        attachedDataDirectories: [],
        workspacePath: null,
      },
    })

    setTextareaCursorToStart(secondWrapper)
    await secondWrapper.get('[data-testid="message-input"]').trigger('keydown', { key: 'ArrowUp' })
    await flushPromises()

    expect((secondWrapper.get('[data-testid="message-input"]').element as HTMLTextAreaElement).value).toBe('')
    secondWrapper.unmount()
    vi.unstubAllGlobals()
  })

  it('exits path editing with escape without closing the directory browser modal', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce({
          ok: true,
          text: async () => JSON.stringify({ items: [] }),
        })
        .mockResolvedValueOnce({
          ok: true,
          text: async () => JSON.stringify({
            current_path: '/tmp/workspaces',
            parent_path: '/tmp',
            home_path: '/Users/jingbh',
            cwd_path: '/Users/jingbh/learning-code/geo-agent',
            entries: [{ name: 'inputs', path: '/tmp/workspaces/inputs', is_dir: true }],
          }),
        }),
    )

    const wrapper = mount(ChatInput, {
      attachTo: document.body,
      props: {
        disabled: false,
        isDraft: true,
        activeQuestion: null,
        attachedDataDirectories: [],
        workspacePath: null,
      },
    })

    await wrapper.get('[data-testid="composer-attach-trigger"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="composer-open-browser"]').trigger('click')
    await flushPromises()
    ;(document.body.querySelector('[data-testid="directory-path-display"]') as HTMLElement).click()
    await flushPromises()
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await flushPromises()

    expect(document.body.querySelector('[data-testid="directory-path-input"]')).toBeNull()
    expect(document.body.querySelector('[data-testid="composer-directory-modal"]')).not.toBeNull()
    wrapper.unmount()
    vi.unstubAllGlobals()
  })

  it('allows manually entering a directory path in the browser modal', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        text: async () => JSON.stringify({ items: [] }),
      })
      .mockResolvedValueOnce({
        ok: true,
        text: async () => JSON.stringify({
          current_path: '/tmp/workspaces',
          parent_path: '/tmp',
          home_path: '/Users/jingbh',
          cwd_path: '/Users/jingbh/learning-code/geo-agent',
          entries: [],
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        text: async () => JSON.stringify({
          current_path: '/tmp/custom-data',
          parent_path: '/tmp',
          home_path: '/Users/jingbh',
          cwd_path: '/Users/jingbh/learning-code/geo-agent',
          entries: [{ name: 'points', path: '/tmp/custom-data/points', is_dir: true }],
        }),
      })

    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(ChatInput, {
      attachTo: document.body,
      props: {
        disabled: false,
        isDraft: true,
        activeQuestion: null,
        attachedDataDirectories: [],
        workspacePath: null,
      },
    })

    await wrapper.get('[data-testid="composer-attach-trigger"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="composer-open-browser"]').trigger('click')
    await flushPromises()
    ;(document.body.querySelector('[data-testid="directory-path-display"]') as HTMLElement).click()
    await flushPromises()
    ;(document.body.querySelector('[data-testid="directory-path-input"]') as HTMLInputElement).value = '/tmp/custom-data'
    ;(document.body.querySelector('[data-testid="directory-path-input"]') as HTMLInputElement).dispatchEvent(new Event('input'))
    await flushPromises()
    ;(document.body.querySelector('[data-testid="directory-path-submit"]') as HTMLElement).click()
    await flushPromises()

    expect(fetchMock).toHaveBeenCalledWith('/api/data-directories/browser?path=%2Ftmp%2Fcustom-data', expect.any(Object))
    expect(document.body.textContent).toContain('points')
    wrapper.unmount()
    vi.unstubAllGlobals()
  })

  it('shows an inline error when a manually entered path does not exist', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        text: async () => JSON.stringify({ items: [] }),
      })
      .mockResolvedValueOnce({
        ok: true,
        text: async () => JSON.stringify({
          current_path: '/tmp/workspaces',
          parent_path: '/tmp',
          home_path: '/Users/jingbh',
          cwd_path: '/Users/jingbh/learning-code/geo-agent',
          entries: [],
        }),
      })
      .mockResolvedValueOnce({
        ok: false,
        text: async () => JSON.stringify({ detail: 'Directory not found' }),
      })

    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(ChatInput, {
      attachTo: document.body,
      props: {
        disabled: false,
        isDraft: true,
        activeQuestion: null,
        attachedDataDirectories: [],
        workspacePath: null,
      },
    })

    await wrapper.get('[data-testid="composer-attach-trigger"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="composer-open-browser"]').trigger('click')
    await flushPromises()
    ;(document.body.querySelector('[data-testid="directory-path-display"]') as HTMLElement).click()
    await flushPromises()
    ;(document.body.querySelector('[data-testid="directory-path-input"]') as HTMLInputElement).value = '/tmp/missing-dir'
    ;(document.body.querySelector('[data-testid="directory-path-input"]') as HTMLInputElement).dispatchEvent(new Event('input'))
    await flushPromises()
    ;(document.body.querySelector('[data-testid="directory-path-submit"]') as HTMLElement).click()
    await flushPromises()

    expect(document.body.textContent).toContain('目录不存在或无法访问。')
    expect((document.body.querySelector('[data-testid="directory-path-input"]') as HTMLInputElement).value).toBe('/tmp/missing-dir')
    wrapper.unmount()
    vi.unstubAllGlobals()
  })

  it('renders the workspace action inside the composer action row', async () => {
    const wrapper = mount(ChatInput, {
      props: {
        disabled: false,
        isDraft: false,
        activeQuestion: null,
        attachedDataDirectories: [],
        workspacePath: '/tmp/workspaces/session-1',
      },
    })

    await wrapper.get('[data-testid="composer-open-workspace"]').trigger('click')

    expect(wrapper.emitted('open-workspace')).toBeTruthy()
  })

  it('emits open and remove actions for attached directory chips', async () => {
    const wrapper = mount(ChatInput, {
      props: {
        disabled: false,
        isDraft: false,
        activeQuestion: null,
        attachedDataDirectories: [
          { id: 'dir-1', path: '/data/beijing-fcd', enabled: true, label: '默认数据目录' },
        ],
        workspacePath: null,
      },
    })

    await wrapper.get('[data-testid="attached-directory-open-dir-1"]').trigger('click')
    await wrapper.get('[data-testid="attached-directory-remove-dir-1"]').trigger('click')

    expect(wrapper.emitted('open-directory')).toEqual([[{ path: '/data/beijing-fcd' }]])
    expect(wrapper.emitted('remove-directory')).toEqual([['dir-1']])
  })
})
