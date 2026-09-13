import { nextTick } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

import ChatWorkspace from './ChatWorkspace.vue'

class FakeResizeObserver {
  static callback: ResizeObserverCallback | null = null
  static observedElement: Element | null = null

  constructor(callback: ResizeObserverCallback) {
    FakeResizeObserver.callback = callback
  }

  observe(element: Element): void {
    FakeResizeObserver.observedElement = element
  }

  disconnect(): void {}
}

function resizeComposer(height: number): void {
  FakeResizeObserver.callback?.(
    [
      {
        contentRect: { height },
      } as ResizeObserverEntry,
    ],
    {} as ResizeObserver,
  )
}

describe('ChatWorkspace', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    FakeResizeObserver.callback = null
    FakeResizeObserver.observedElement = null
  })

  it('sizes message padding from the floating composer height', async () => {
    vi.stubGlobal('ResizeObserver', FakeResizeObserver)

    const wrapper = mount(ChatWorkspace, {
      props: {
        activeSessionId: null,
        isDraft: true,
        sessionStatus: 'idle',
        messages: [],
        recentMessages: [],
        activeQuestion: null,
        attachedDataDirectories: [],
        workspacePath: null,
      },
    })

    const overlay = wrapper.get('[data-testid="composer-overlay"]')
    expect(FakeResizeObserver.observedElement).toBe(overlay.element)
    expect(wrapper.get('[data-testid="message-list-scroller"]').classes()).toContain('pb-[var(--composer-overlay-offset)]')

    await nextTick()
    const workspace = wrapper.get('[data-testid="chat-workspace"]').element as HTMLElement
    expect(workspace.style.getPropertyValue('--composer-overlay-offset')).toBe('192px')

    resizeComposer(268)
    await nextTick()

    expect(workspace.style.getPropertyValue('--composer-overlay-offset')).toBe('268px')
  })

  it('hides the floating composer for read-only sessions', () => {
    const wrapper = mount(ChatWorkspace, {
      props: {
        activeSessionId: 'imported-session-1',
        isDraft: false,
        sessionStatus: 'completed',
        readOnly: true,
        messages: [],
        recentMessages: [],
        activeQuestion: null,
        attachedDataDirectories: [],
        workspacePath: null,
      },
    })

    expect(wrapper.find('[data-testid="composer-overlay"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="composer-shell"]').exists()).toBe(false)
    expect((wrapper.get('[data-testid="chat-workspace"]').element as HTMLElement).style.getPropertyValue('--composer-overlay-offset')).toBe('0px')
  })
})
