import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { nextTick } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

import MessageList from './MessageList.vue'

function installScrollMetrics(element: HTMLElement, values: { scrollHeight: number, clientHeight: number, scrollTop: number }) {
  const metrics = {
    scrollHeight: values.scrollHeight,
    clientHeight: values.clientHeight,
    scrollTop: values.scrollTop,
  }

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

describe('MessageList', () => {
  it('opens a context menu for actionable assistant messages and copies their text', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal('navigator', { clipboard: { writeText } })

    const wrapper = mount(MessageList, {
      props: {
        isDraft: false,
        sessionStatus: 'completed',
        messages: [
          {
            id: 'msg-assistant-1',
            role: 'assistant',
            agent: 'geo',
            created_at: '',
            parts: [
              {
                type: 'text',
                text: '## KDE\n\n- **状态**: 已完成',
              },
            ],
          },
        ],
      },
    })

    expect(wrapper.get('h2').classes()).toContain('message-markdown__heading')
    expect(wrapper.get('h2').classes()).toContain('message-markdown__heading--h2')
    expect(wrapper.get('strong').classes()).toContain('message-markdown__strong')
    expect(wrapper.text()).not.toContain('Copy')
    expect(wrapper.find('[data-testid="copy-assistant-message-msg-assistant-1"]').exists()).toBe(false)

    const bubble = wrapper.get('[data-testid="message-bubble-msg-assistant-1"]')
    await bubble.trigger('contextmenu', { button: 2, clientX: 120, clientY: 64 })

    expect(wrapper.find('[data-testid="message-context-menu"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="message-context-menu"]').classes()).toContain('z-[80]')

    await wrapper.get('[data-testid="message-context-menu-copy-msg-assistant-1"]').trigger('click')
    expect(writeText).toHaveBeenCalledWith('## KDE\n\n- **状态**: 已完成')
    vi.unstubAllGlobals()
  })

  it('falls back to legacy copy when the async clipboard API rejects', async () => {
    const writeText = vi.fn().mockRejectedValue(new Error('denied'))
    const originalExecCommand = document.execCommand
    const execCommand = vi.fn().mockReturnValue(true)
    vi.stubGlobal('navigator', { clipboard: { writeText } })
    Object.defineProperty(document, 'execCommand', {
      configurable: true,
      value: execCommand,
    })

    const wrapper = mount(MessageList, {
      props: {
        isDraft: false,
        sessionStatus: 'completed',
        messages: [
          {
            id: 'msg-assistant-fallback',
            role: 'assistant',
            agent: 'geo',
            created_at: '',
            parts: [
              {
                type: 'text',
                text: '# 原始 Markdown\n\n第二段内容',
              },
            ],
          },
        ],
      },
      attachTo: document.body,
    })

    try {
      const bubble = wrapper.get('[data-testid="message-bubble-msg-assistant-fallback"]')
      await bubble.trigger('contextmenu', { button: 2, clientX: 120, clientY: 64 })
      await wrapper.get('[data-testid="message-context-menu-copy-msg-assistant-fallback"]').trigger('click')
      await nextTick()

      expect(writeText).toHaveBeenCalledWith('# 原始 Markdown\n\n第二段内容')
      expect(execCommand).toHaveBeenCalledWith('copy')
      expect(wrapper.find('[data-testid="message-context-menu"]').exists()).toBe(false)
      expect(document.body.querySelector('textarea[readonly]')).toBeNull()
    } finally {
      wrapper.unmount()
      vi.unstubAllGlobals()
      if (typeof originalExecCommand === 'function') {
        Object.defineProperty(document, 'execCommand', {
          configurable: true,
          value: originalExecCommand,
        })
      } else {
        Reflect.deleteProperty(document, 'execCommand')
      }
    }
  })

  it('does not open a context menu for structured runtime question cards', async () => {
    const wrapper = mount(MessageList, {
      props: {
        isDraft: false,
        sessionStatus: 'waiting_for_input',
        messages: [
          {
            id: 'msg-study-design-question-tool',
            role: 'assistant',
            agent: 'study-design',
            created_at: '2026-04-21T12:00:00.000Z',
            parts: [
              {
                type: 'tool',
                tool: 'question',
                state: {
                  input: {
                    questions: [
                      {
                        header: '研究区',
                        question: '请选择研究区范围',
                        options: [{ label: '北京市全域' }],
                      },
                    ],
                  },
                },
              },
            ],
          },
          {
            id: 'msg-runtime-question',
            role: 'system',
            agent: 'geo',
            created_at: '2026-04-21T12:00:01.000Z',
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
                      options: [{ label: '北京市全域' }],
                    },
                  ],
                },
              },
            ],
          },
        ],
      } as never,
    })

    const questionCard = wrapper.get('[data-testid="standalone-question-message-msg-runtime-question"]').element as HTMLElement
    const event = new MouseEvent('contextmenu', { bubbles: true, cancelable: true, clientX: 24, clientY: 24 })

    expect(questionCard.dispatchEvent(event)).toBe(true)
    expect(wrapper.find('[data-testid="message-context-menu"]').exists()).toBe(false)
  })

  it('keeps streaming tool-only assistant output visible without a context menu', () => {
    const wrapper = mount(MessageList, {
      props: {
        isDraft: false,
        sessionStatus: 'running',
        messages: [
          {
            id: 'msg-empty-assistant',
            role: 'assistant',
            agent: 'geo',
            created_at: '',
            parts: [
              { type: 'text', text: '' },
            ],
          },
          {
            id: 'msg-tool-only',
            role: 'assistant',
            agent: 'geo',
            created_at: '',
            parts: [
              {
                type: 'tool',
                tool: 'geospatial_record_run_evidence',
                state: {
                  input: { prompt: 'Need KDE' },
                  output: '{"status":"completed"}',
                },
              },
            ],
          },
          {
            id: 'msg-streaming-assistant',
            role: 'assistant',
            agent: 'geo',
            created_at: '',
            parts: [
              { type: 'text', text: 'still streaming' },
            ],
          },
        ],
      },
    })

    expect(wrapper.text()).not.toContain('msg-empty-assistant')
    expect(wrapper.find('[data-testid="message-context-menu"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('记录证据')
    expect(wrapper.findAll('.message-markdown')).toHaveLength(1)
  })

  it('renders final artifacts at the bottom of the transcript flow', () => {
    const wrapper = mount(MessageList, {
      props: {
        isDraft: false,
        sessionStatus: 'completed',
        messages: [
          {
            id: 'msg-assistant-final',
            role: 'assistant',
            agent: 'geo',
            created_at: '2026-04-21T10:00:00.000Z',
            parts: [{ type: 'text', text: '最终消息。' }],
          },
        ],
        finalArtifacts: [
          {
            id: 'artifact-final',
            title: '海淀区FCD热力图',
            path: 'haidian_heatmap.png',
            kind: 'map',
            artifact_stage: 'final',
            display_hint: 'map',
          },
        ],
      },
    })

    expect(wrapper.find('[data-testid="final-artifact-carousel"]').exists()).toBe(true)
    expect(wrapper.text().indexOf('最终消息。')).toBeLessThan(wrapper.text().indexOf('海淀区FCD热力图'))
  })

  it('uses matched artifact metadata instead of showing successful intermediate artifact tool rows', () => {
    const wrapper = mount(MessageList, {
      props: {
        isDraft: false,
        sessionStatus: 'completed',
        artifacts: [
          {
            id: 'artifact-1',
            title: '中间参数快照',
            path: 'outputs/params.md',
            artifact_stage: 'intermediate',
            display_hint: 'markdown',
            evidence_record_id: 'evidence-params',
          },
        ],
        messages: [
          {
            id: 'msg-tool-intermediate',
            role: 'assistant',
            agent: 'geo',
            created_at: '2026-04-21T10:00:00.000Z',
            parts: [
              {
                type: 'tool',
                tool: 'geospatial_record_run_evidence',
                state: {
                  input: {
                    record_type: 'artifact',
                    artifact_stage: 'intermediate',
                    path: 'outputs/params.md',
                    title: '中间参数快照',
                  },
                  output: '<evidence status="recorded" type="artifact"><record_id>evidence-params</record_id></evidence>',
                },
              },
            ],
          },
        ],
      } as never,
    })

    expect(wrapper.text()).not.toContain('记录中间产物')
    expect(wrapper.findAll('[data-testid="inline-artifact-block"]')).toHaveLength(1)
    expect(wrapper.text()).toContain('outputs/params.md')
  })

  it('groups consecutive same-agent transcript entries under one shared header', () => {
    const wrapper = mount(MessageList, {
      props: {
        isDraft: false,
        sessionStatus: 'completed',
        messages: [
          {
            id: 'msg-geo-1',
            role: 'assistant',
            agent: 'geo',
            created_at: '2026-04-21T10:00:00.000Z',
            parts: [
              {
                type: 'text',
                text: '先检查输入数据。',
              },
            ],
          },
          {
            id: 'msg-geo-2',
            role: 'assistant',
            agent: 'geo',
            created_at: '2026-04-21T10:00:01.000Z',
            parts: [
              {
                type: 'tool',
                tool: 'geospatial_record_run_evidence',
                state: {
                  input: { prompt: 'Need KDE' },
                  output: '{"status":"completed"}',
                },
              },
            ],
          },
          {
            id: 'msg-geo-3',
            role: 'system',
            agent: 'geo',
            created_at: '2026-04-21T10:00:02.000Z',
            parts: [
              {
                type: 'todo',
                state: {
                  entries: [
                    { id: 'plan-1', label: '执行通用预处理', status: 'completed' },
                  ],
                },
              },
            ],
          },
          {
            id: 'msg-geo-4',
            role: 'assistant',
            agent: 'geo',
            created_at: '2026-04-21T10:00:03.000Z',
            parts: [
              {
                type: 'text',
                text: '预处理已完成。',
              },
            ],
          },
          {
            id: 'msg-review-1',
            role: 'assistant',
            agent: 'skeptical-review',
            created_at: '2026-04-21T10:00:04.000Z',
            parts: [
              {
                type: 'text',
                text: '请确认 CRS 是否统一。',
              },
            ],
          },
        ],
      },
    })

    expect(wrapper.get('[data-testid="message-agent-label-msg-geo-1"]').text()).toBe('空间主理人')
    expect(wrapper.find('[data-testid="message-agent-label-msg-geo-2"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="message-agent-label-msg-geo-3"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="message-agent-label-msg-geo-4"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="message-agent-label-msg-review-1"]').text()).toBe('结果审查官')
    expect(wrapper.text()).toContain('先检查输入数据。')
    expect(wrapper.text()).toContain('记录证据')
    expect(wrapper.text()).toContain('执行通用预处理')
    expect(wrapper.text()).toContain('预处理已完成。')
  })

  it('renders truly unowned system events as centered muted notices', () => {
    const wrapper = mount(MessageList, {
      props: {
        isDraft: false,
        sessionStatus: 'completed',
        messages: [
          {
            id: 'msg-system-notice',
            role: 'system',
            created_at: '2026-04-21T10:00:00.000Z',
            parts: [
              {
                type: 'text',
                text: '运行已恢复',
              },
            ],
          },
        ],
      },
    })

    expect(wrapper.get('[data-testid="system-notice-msg-system-notice"]').text()).toContain('运行已恢复')
    expect(wrapper.find('[data-testid="message-agent-label-msg-system-notice"]').exists()).toBe(false)
  })

  it('renders inline todo, verification, artifact, and subagent transcript blocks', () => {
    const wrapper = mount(MessageList, {
      props: {
        isDraft: false,
        sessionStatus: 'completed',
        messages: [
          {
            id: 'msg-planner-1',
            role: 'system',
            agent: 'geo',
            created_at: '',
            parts: [
              {
                type: 'todo',
                state: {
                  entries: [
                    { id: 'plan-1', label: '规范化地理分析任务', status: 'completed' },
                    { id: 'plan-2', label: '执行通用预处理', status: 'in_progress' },
                  ],
                },
              },
            ],
          },
          {
            id: 'msg-reflection-1',
            role: 'system',
            agent: 'skeptical-review',
            created_at: '',
            parts: [
              {
                type: 'verification',
                state: {
                  entries: [
                    { id: 'verification-1', title: '已完成投影归一化', status: 'passed', detail: 'detail' },
                  ],
                },
              },
            ],
          },
          {
            id: 'msg-report-1',
            role: 'system',
            agent: 'report-synthesizer',
            created_at: '',
            parts: [
              {
                type: 'artifact',
                state: {
                  id: 'artifact-1',
                  title: 'KDE 运行清单',
                  path: '/tmp/run-manifest.json',
                  kind: 'manifest',
                  analysis_type: 'kde',
                  description: '可复现运行清单',
                },
              },
            ],
          },
        ],
      },
    })

    expect(wrapper.text()).toContain('空间主理人')
    expect(wrapper.text()).toContain('结果审查官')
    expect(wrapper.text()).toContain('报告整编师')
    expect(wrapper.text()).toContain('规范化地理分析任务')
    expect(wrapper.text()).toContain('执行通用预处理')
    expect(wrapper.text()).toContain('已完成投影归一化')
    expect(wrapper.text()).toContain('KDE 运行清单')
    expect(wrapper.text()).toContain('可复现运行清单')
    expect(wrapper.text()).toContain('任务更新')
    expect(wrapper.text()).toContain('验证')
    expect(wrapper.find('[data-testid="inline-artifact-block"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="message-agent-avatar-msg-planner-1"]').attributes('src')).toBe('/agent-avatar/geo-orchestrator.png')
    expect(wrapper.get('[data-testid="message-agent-avatar-msg-reflection-1"]').attributes('src')).toBe('/agent-avatar/skeptical-review.png')
    expect(wrapper.get('[data-testid="message-agent-avatar-msg-report-1"]').attributes('src')).toBe('/agent-avatar/report-synthesizer.png')
  })

  it('renders issue parts as compact inline notices', () => {
    const wrapper = mount(MessageList, {
      props: {
        isDraft: false,
        sessionStatus: 'completed',
        messages: [
          {
            id: 'msg-issue-1',
            role: 'system',
            agent: 'geo',
            created_at: '',
            parts: [
              {
                type: 'issue',
                text: '待办更新失败',
                state: {
                  title: '待办更新失败',
                  detail: '待办更新工具返回错误，当前任务列表可能不是最新状态。',
                  severity: 'error',
                  source: 'mcp',
                },
              },
            ],
          },
        ],
      },
    })

    const issue = wrapper.get('[data-testid="inline-issue-msg-issue-1"]')
    const classes = issue.classes().join(' ')
    const rowClasses = wrapper.get('[data-testid="inline-issue-row-msg-issue-1"]').classes().join(' ')
    const bubbleClasses = wrapper.get('[data-testid="message-bubble-msg-issue-1"]').classes().join(' ')

    expect(issue.text()).toContain('错误')
    expect(issue.text()).toContain('待办更新工具返回错误，当前任务列表可能不是最新状态。')
    expect(issue.text()).not.toContain('待办更新失败')
    expect(issue.text()).not.toContain('·工具')
    expect(rowClasses).toContain('mx-auto')
    expect(rowClasses).toContain('max-w-[88%]')
    expect(rowClasses).not.toContain('gap-3')
    expect(classes).toContain('w-full')
    expect(classes).toContain('justify-center')
    expect(classes).toContain('text-center')
    expect(classes).toContain('whitespace-nowrap')
    expect(classes).not.toMatch(/\brounded/)
    expect(classes).not.toMatch(/\bring/)
    expect(classes).not.toMatch(/\bbg-/)
    expect(classes).not.toMatch(/\bborder/)
    expect(bubbleClasses).toContain('bg-transparent')
    expect(bubbleClasses).not.toMatch(/\brounded/)
    expect(bubbleClasses).not.toContain('bg-white')
    expect(bubbleClasses).not.toContain('ring-slate')
    expect(wrapper.find('[data-testid="issue-block-msg-issue-1"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="message-agent-avatar-msg-issue-1"]').exists()).toBe(false)
  })

  it('opens an agent profile popover from the avatar button', async () => {
    const wrapper = mount(MessageList, {
      props: {
        isDraft: false,
        sessionStatus: 'completed',
        messages: [
          {
            id: 'msg-review-1',
            role: 'assistant',
            agent: 'skeptical-review',
            created_at: '2026-04-21T10:00:04.000Z',
            parts: [
              {
                type: 'text',
                text: '我来检查这条分析链是否足够可靠。',
              },
            ],
          },
        ],
      },
      attachTo: document.body,
    })

    await wrapper.get('[data-testid="message-agent-avatar-button-msg-review-1"]').trigger('click')

    expect(wrapper.find('[data-testid="agent-profile-popover"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="agent-profile-popover-label"]').text()).toBe('结果审查官')
    expect(wrapper.text()).toContain('负责用对抗式视角检查方法、证据和表述是否站得住脚。')
    expect(wrapper.text()).not.toContain('@skeptical-review')
    expect(wrapper.text()).not.toContain('主要职责')

    await wrapper.get('[data-testid="message-agent-avatar-button-msg-review-1"]').trigger('click')

    expect(wrapper.find('[data-testid="agent-profile-popover"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('renders interpolation and hotspot specialist identities distinctly', () => {
    const wrapper = mount(MessageList, {
      props: {
        isDraft: false,
        sessionStatus: 'completed',
        messages: [
          {
            id: 'msg-idw-operator',
            role: 'assistant',
            agent: 'operator-interpolation',
            created_at: '2026-04-21T10:00:00.000Z',
            parts: [{ type: 'text', text: '执行 IDW 插值。' }],
          },
          {
            id: 'msg-gistar-operator',
            role: 'assistant',
            agent: 'operator-spatial-hotspot',
            created_at: '2026-04-21T10:00:01.000Z',
            parts: [{ type: 'text', text: '执行 Gi* 统计热点分析。' }],
          },
        ],
      },
    })

    expect(wrapper.get('[data-testid="message-agent-label-msg-idw-operator"]').text()).toBe('插值分析师')
    expect(wrapper.get('[data-testid="message-agent-label-msg-gistar-operator"]').text()).toBe('统计热点分析师')
    expect(wrapper.text()).toContain('执行 IDW 插值。')
    expect(wrapper.text()).toContain('执行 Gi* 统计热点分析。')
  })

  it('renders structured question cards and hides raw question tool parts', () => {
    const wrapper = mount(MessageList, {
      props: {
        isDraft: false,
        sessionStatus: 'waiting_for_input',
        messages: [
          {
            id: 'msg-assistant-question-tool',
            role: 'assistant',
            agent: 'geo',
            created_at: '',
            parts: [
              {
                type: 'tool',
                tool: 'question',
                state: {
                  meta: {
                    tool_family: 'question',
                    tool_label: '询问用户',
                  },
                  input: {
                    questions: [
                      {
                        header: '研究区',
                        question: '请选择研究区范围',
                        options: [{ label: '使用默认北京市区县边界', description: '使用系统默认行政区边界继续执行' }],
                      },
                    ],
                  },
                },
              },
            ],
          },
          {
            id: 'msg-runtime-question',
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
                      options: [{ label: '使用默认北京市区县边界', description: '使用系统默认行政区边界继续执行' }],
                    },
                  ],
                },
              },
            ],
          },
        ],
      } as never,
    })

    expect(wrapper.text()).toContain('请选择研究区范围')
    expect(wrapper.text()).not.toContain('使用默认北京市区县边界')
    expect(wrapper.text()).not.toContain('询问用户')
    expect(wrapper.find('[data-testid="toggle-tool-details"]').exists()).toBe(false)
  })

  it('renders child task dispatches as a minimal system notice and inlines the child agent reply', () => {
    const wrapper = mount(MessageList, {
      props: {
        isDraft: false,
        sessionStatus: 'completed',
        messages: [
          {
            id: 'msg-parent-dispatch',
            role: 'assistant',
            agent: 'geo',
            created_at: '2026-04-21T12:00:00.000Z',
            parts: [
              {
                type: 'text',
                text: '好的，我来调用 request-triage agent 让它做个自我介绍。',
              },
              {
                type: 'tool',
                tool: 'task',
                state: {
                  input: {
                    description: 'Request-triage agent 自我介绍',
                    prompt: '请做一个自我介绍，说明你的角色、职责和能力。',
                    subagent_type: 'request-triage',
                  },
                  output: 'task_id: ses_child_task\n\n<task_result>done</task_result>',
                },
              },
            ],
          },
          {
            id: 'inline-subtask-ses_child_task',
            role: 'system',
            created_at: '2026-04-21T12:00:00.500Z',
            parts: [
              {
                type: 'subtask',
                state: {
                  parent_agent: 'geo',
                  child_agent: 'request-triage',
                  description: 'Request-triage agent 自我介绍',
                  prompt: '请做一个自我介绍，说明你的角色、职责和能力。',
                  task_session_id: 'ses_child_task',
                },
              },
            ],
          },
          {
            id: 'msg-child-request-triage',
            role: 'assistant',
            agent: 'request-triage',
            created_at: '2026-04-21T12:00:01.000Z',
            parts: [
              {
                type: 'text',
                text: '我是 Request Triage，负责识别请求目标并补齐执行前缺失的信息。',
              },
            ],
          },
        ],
      } as never,
    })

    expect(wrapper.text()).toContain('好的，我来调用 request-triage agent 让它做个自我介绍。')
    expect(wrapper.find('[data-testid="subtask-notice-inline-subtask-ses_child_task"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="message-agent-label-inline-subtask-ses_child_task"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="subtask-notice-inline-subtask-ses_child_task"]').text()).toContain('@需求分诊师')
    expect(wrapper.get('[data-testid="subtask-notice-inline-subtask-ses_child_task"]').text()).toContain('请做一个自我介绍，说明你的角色、职责和能力。')
    expect(wrapper.get('[data-testid="subtask-notice-inline-subtask-ses_child_task"]').text()).not.toContain('Request-triage agent 自我介绍')
    expect(wrapper.get('[data-testid="subtask-notice-inline-subtask-ses_child_task"]').text()).not.toContain('@request-triage')
    expect(wrapper.get('[data-testid="subtask-mention-inline-subtask-ses_child_task"]').classes()).toContain('p-0')
    expect(wrapper.get('[data-testid="subtask-mention-inline-subtask-ses_child_task"]').classes()).not.toContain('rounded-full')
    expect(wrapper.get('[data-testid="message-bubble-msg-parent-dispatch"]').element.closest('div[class*="mb-"]')?.className).toContain('mb-1.5')
    expect(wrapper.get('[data-testid="message-bubble-inline-subtask-ses_child_task"]').element.closest('div[class*="mb-"]')?.className).toContain('mb-3')
    expect(wrapper.text()).toContain('我是 Request Triage，负责识别请求目标并补齐执行前缺失的信息。')
    expect(wrapper.get('[data-testid="message-agent-avatar-msg-child-request-triage"]').classes()).toEqual(
      expect.arrayContaining(['h-10', 'w-10']),
    )
    expect(wrapper.text()).not.toContain('<task_result>')
    expect(wrapper.text()).not.toContain('task_id: ses_child_task')
  })

  it('renders subagent mention prompts as markdown', () => {
    const wrapper = mount(MessageList, {
      props: {
        isDraft: false,
        sessionStatus: 'completed',
        messages: [
          {
            id: 'inline-subtask-ses_child_task',
            role: 'system',
            created_at: '2026-04-21T12:00:00.500Z',
            parts: [
              {
                type: 'subtask',
                state: {
                  parent_agent: 'geo',
                  child_agent: 'data-audit',
                  prompt: '请检查 `CRS`。\n\n- **数据质量**\n- EPSG:32650',
                  task_session_id: 'ses_child_task',
                },
              },
            ],
          },
        ],
      } as never,
    })

    const notice = wrapper.get('[data-testid="subtask-notice-inline-subtask-ses_child_task"]')

    expect(notice.find('.message-markdown').exists()).toBe(true)
    expect(notice.get('code').classes()).toContain('message-markdown__code--inline')
    expect(notice.get('strong').classes()).toContain('message-markdown__strong')
    expect(notice.get('ul').classes()).toContain('message-markdown__list')
  })

  it('renders the active runtime question inline, advances one question at a time, and auto-submits the last answer', async () => {
    const wrapper = mount(MessageList, {
      props: {
        isDraft: false,
        sessionStatus: 'waiting_for_input',
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
        messages: [
          {
            id: 'msg-analysis-question-tool',
            role: 'assistant',
            agent: 'study-design',
            created_at: '',
            parts: [
              {
                type: 'tool',
                tool: 'question',
                state: {
                  input: {
                    questions: [
                      {
                        header: '研究区',
                        question: '请选择研究区范围',
                        options: [{ label: '使用默认北京市区县边界', description: '使用系统默认行政区边界继续执行' }],
                      },
                      {
                        header: '输出语言',
                        question: '最终报告使用什么语言？',
                        options: [{ label: '中文', description: '使用简体中文生成最终结果' }],
                      },
                    ],
                  },
                },
              },
            ],
          },
          {
            id: 'msg-runtime-question',
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
                      options: [{ label: '使用默认北京市区县边界', description: '使用系统默认行政区边界继续执行' }],
                    },
                    {
                      header: '输出语言',
                      question: '最终报告使用什么语言？',
                      options: [{ label: '中文', description: '使用简体中文生成最终结果' }],
                    },
                  ],
                },
              },
            ],
          },
        ],
      } as never,
    })

    expect(wrapper.get('[data-testid="message-agent-label-msg-runtime-question"]').text()).toBe('研究策划师')
    expect(wrapper.get('[data-testid="message-agent-avatar-msg-runtime-question"]').attributes('src')).toBe('/agent-avatar/study-design.png')
    expect(wrapper.get('[data-testid="standalone-question-message-msg-runtime-question"]').classes()).toEqual(
      expect.arrayContaining(['w-full', 'max-w-[88%]']),
    )
    expect(wrapper.get('.message-bubble').classes()).toEqual(
      expect.arrayContaining(['bg-transparent', 'px-0', 'py-0', 'shadow-none', 'ring-0']),
    )
    expect(wrapper.text()).toContain('1/2 个问题')
    expect(wrapper.text()).toContain('请选择研究区范围')
    expect(wrapper.text()).not.toContain('最终报告使用什么语言？')
    expect(wrapper.text()).not.toContain('Human In The Loop')
    expect(wrapper.text()).not.toContain('需要你的回答后才能继续')
    expect(wrapper.text()).not.toContain('可以直接点选建议答案，也可以改成自定义内容后再提交。')

    await wrapper.get('[data-testid="structured-question-option-0-0"]').trigger('click')

    expect(wrapper.text()).toContain('2/2 个问题')
    expect(wrapper.text()).not.toContain('请选择研究区范围')
    expect(wrapper.text()).toContain('最终报告使用什么语言？')

    await wrapper.get('[data-testid="structured-question-option-1-0"]').trigger('click')

    expect(wrapper.emitted('reply-question')).toEqual([[{ answers: ['使用默认北京市区县边界', '中文'] }]])
  })

  it('advances custom answers with Tab and ignores Enter while IME composition is still active', async () => {
    const wrapper = mount(MessageList, {
      props: {
        isDraft: false,
        sessionStatus: 'waiting_for_input',
        activeQuestion: {
          id: 'question-request-inline-ime',
          prompt: '研究区范围',
          source: 'runtime',
          questions: [
            {
              header: '研究区范围',
              question: '请输入研究区范围',
              options: [],
            },
            {
              header: '输出语言',
              question: '请输入输出语言',
              options: [],
            },
          ],
        },
        messages: [
          {
            id: 'msg-runtime-question-inline-ime',
            role: 'system',
            agent: 'geo',
            created_at: '',
            parts: [
              {
                type: 'question',
                text: '请输入研究区范围',
                state: {
                  id: 'question-request-inline-ime',
                  prompt: '研究区范围',
                  source: 'runtime',
                  questions: [
                    {
                      header: '研究区范围',
                      question: '请输入研究区范围',
                      options: [],
                    },
                    {
                      header: '输出语言',
                      question: '请输入输出语言',
                      options: [],
                    },
                  ],
                },
              },
            ],
          },
        ],
      } as never,
    })

    const firstInput = wrapper.get('[data-testid="structured-question-input-0"]')
    await firstInput.setValue('北京市')
    await firstInput.trigger('compositionstart')
    await firstInput.trigger('keydown', { key: 'Enter', isComposing: true })

    expect(wrapper.emitted('reply-question')).toBeUndefined()
    expect(wrapper.text()).toContain('1/2 个问题')

    await firstInput.trigger('compositionend')
    await firstInput.trigger('keydown', { key: 'Tab' })

    expect(wrapper.text()).toContain('2/2 个问题')
    expect(wrapper.text()).toContain('请输入输出语言')

    const secondInput = wrapper.get('[data-testid="structured-question-input-1"]')
    await secondInput.setValue('中文')
    await secondInput.trigger('keydown', { key: 'Tab' })

    expect(wrapper.emitted('reply-question')).toEqual([[{ answers: ['北京市', '中文'] }]])
  })

  it('renders answered runtime question cards as a minimal question and final-answer summary', () => {
    const wrapper = mount(MessageList, {
      props: {
        isDraft: false,
        sessionStatus: 'completed',
        messages: [
          {
            id: 'msg-runtime-question',
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
                      header: '研究区范围',
                      question: '请选择研究区范围',
                      options: [{ label: '北京市全域' }, { label: '上海市全域' }],
                    },
                    {
                      header: '输出语言',
                      question: '请选择输出语言',
                      options: [{ label: '中文' }, { label: '英文' }],
                    },
                  ],
                },
              },
            ],
          },
          {
            id: 'msg-question-tool',
            role: 'assistant',
            agent: 'geo',
            created_at: '',
            parts: [
              {
                type: 'tool',
                tool: 'question',
                state: {
                  input: {
                    questions: [
                      {
                        header: '研究区范围',
                        question: '请选择研究区范围',
                        options: [{ label: '北京市全域' }, { label: '上海市全域' }],
                      },
                      {
                        header: '输出语言',
                        question: '请选择输出语言',
                        options: [{ label: '中文' }, { label: '英文' }],
                      },
                    ],
                  },
                  metadata: {
                    answers: [['北京市全域'], ['中文']],
                  },
                },
              },
            ],
          },
        ],
      } as never,
    })

    expect(wrapper.text()).toContain('研究区范围')
    expect(wrapper.text()).toContain('北京市全域')
    expect(wrapper.text()).toContain('输出语言')
    expect(wrapper.text()).toContain('中文')
    expect(wrapper.get('[data-testid="answered-question-header-msg-runtime-question"]').text()).toContain('提问')
    expect(wrapper.get('[data-testid="standalone-question-message-msg-runtime-question"]').classes()).not.toContain('w-full')
    expect(wrapper.text()).not.toContain('上海市全域')
    expect(wrapper.text()).not.toContain('英文')
    expect(wrapper.text()).not.toContain('已回答')
    expect(wrapper.text()).not.toContain('已回传')
    expect(wrapper.text()).not.toContain('已提交答案')
  })

  it('renders answered runtime questions at their original chronological position instead of leaving them at the end', () => {
    const wrapper = mount(MessageList, {
      props: {
        isDraft: false,
        sessionStatus: 'completed',
        messages: [
          {
            id: 'msg-user-question-request',
            role: 'user',
            agent: 'geo',
            created_at: '2026-04-20T15:00:00.000Z',
            parts: [
              {
                type: 'text',
                text: '用 ask user question tool 随便问我两个问题',
              },
            ],
          },
          {
            id: 'msg-question-tool',
            role: 'assistant',
            agent: 'geo',
            created_at: '2026-04-20T15:00:01.000Z',
            parts: [
              {
                type: 'tool',
                tool: 'question',
                state: {
                  input: {
                    questions: [
                      {
                        header: '兴趣爱好',
                        question: '你最喜欢的兴趣爱好是什么？',
                        options: [{ label: '旅行探险' }],
                      },
                      {
                        header: '天气偏好',
                        question: '你最喜欢什么天气？',
                        options: [{ label: '晴天' }],
                      },
                    ],
                  },
                  metadata: {
                    answers: [['旅行探险'], ['晴天']],
                  },
                },
              },
            ],
          },
          {
            id: 'msg-assistant-summary',
            role: 'assistant',
            agent: 'geo',
            created_at: '2026-04-20T15:00:05.000Z',
            parts: [
              {
                type: 'text',
                text: '太好了！根据你的回答：旅行探险，晴天。',
              },
            ],
          },
          {
            id: 'msg-runtime-question-late-in-array',
            role: 'system',
            agent: 'geo',
            created_at: '2026-04-20T15:00:02.000Z',
            parts: [
              {
                type: 'question',
                text: '你最喜欢的兴趣爱好是什么？',
                state: {
                  id: 'question-request-history-order',
                  prompt: '你最喜欢的兴趣爱好是什么？',
                  source: 'runtime',
                  questions: [
                    {
                      header: '兴趣爱好',
                      question: '你最喜欢的兴趣爱好是什么？',
                      options: [{ label: '旅行探险' }],
                    },
                    {
                      header: '天气偏好',
                      question: '你最喜欢什么天气？',
                      options: [{ label: '晴天' }],
                    },
                  ],
                },
              },
            ],
          },
        ],
      } as never,
    })

    const transcriptText = wrapper.text()
    expect(transcriptText.indexOf('你最喜欢什么天气？')).toBeGreaterThan(-1)
    expect(transcriptText.indexOf('太好了！根据你的回答：旅行探险，晴天。')).toBeGreaterThan(-1)
    expect(transcriptText.indexOf('你最喜欢什么天气？')).toBeLessThan(transcriptText.indexOf('太好了！根据你的回答：旅行探险，晴天。'))
  })

  it('renders fenced code blocks for streaming-friendly markdown output', () => {
    const wrapper = mount(MessageList, {
      props: {
        isDraft: false,
        sessionStatus: 'running',
        messages: [
          {
            id: 'msg-assistant-code',
            role: 'assistant',
            agent: 'geo',
            created_at: '',
            parts: [
              {
                type: 'text',
                text: '```python\nprint("hello")\n```',
              },
            ],
          },
        ],
      },
    })

    expect(wrapper.html()).toContain('<pre')
    expect(wrapper.html()).toContain('<code')
    expect(wrapper.text()).toContain('print("hello")')
  })

  it('applies styled markdown classes across rich transcript elements', () => {
    const wrapper = mount(MessageList, {
      props: {
        isDraft: false,
        sessionStatus: 'completed',
        messages: [
          {
            id: 'msg-assistant-rich-markdown',
            role: 'assistant',
            agent: 'geo',
            created_at: '',
            parts: [
              {
                type: 'text',
                text: '# Heading\n\nParagraph with [link](https://example.com), `inline`, **strong**, *emphasis*, and ~~delete~~.\n\n> Quoted line\n\n1. First\n2. Second\n\n- Bullet\n\n---\n\n| Name | Value |\n| --- | --- |\n| KDE | Ready |\n\n![Map](https://example.com/map.png)\n\n```python\nprint("hello")\n```',
              },
            ],
          },
        ],
      },
    })

    expect(wrapper.get('h1').classes()).toContain('message-markdown__heading')
    expect(wrapper.get('h1').classes()).toContain('message-markdown__heading--h1')
    expect(wrapper.get('p').classes()).toContain('message-markdown__paragraph')
    expect(wrapper.get('a').classes()).toContain('message-markdown__link')
    expect(wrapper.get('blockquote').classes()).toContain('message-markdown__blockquote')
    expect(wrapper.get('ol').classes()).toContain('message-markdown__list')
    expect(wrapper.get('ol').classes()).toContain('message-markdown__list--ordered')
    expect(wrapper.get('ul').classes()).toContain('message-markdown__list')
    expect(wrapper.get('ul').classes()).toContain('message-markdown__list--bullet')
    expect(wrapper.get('hr').classes()).toContain('message-markdown__rule')
    expect(wrapper.get('table').classes()).toContain('message-markdown__table')
    expect(wrapper.get('th').classes()).toContain('message-markdown__table-head-cell')
    expect(wrapper.get('td').classes()).toContain('message-markdown__table-cell')
    expect(wrapper.get('.message-markdown__image').classes()).toContain('message-markdown__image')
    expect(wrapper.get('pre').classes()).toContain('message-markdown__pre')
    expect(wrapper.get('code').classes()).toContain('message-markdown__code')
    const source = readFileSync(resolve(process.cwd(), 'src/components/chat/MessageList.vue'), 'utf8')
    expect(source).toContain('.message-markdown :deep(.message-markdown__list--bullet)')
    expect(source).toContain('list-style-type: disc;')
    expect(source).toContain('.message-markdown :deep(.message-markdown__list--ordered)')
    expect(source).toContain('list-style-type: decimal;')
  })

  it('defines a dedicated muted markdown typography profile for thinking text', () => {
    const source = readFileSync(resolve(process.cwd(), 'src/components/chat/MessageList.vue'), 'utf8')

    expect(source).toContain('.message-markdown.message-reasoning')
    expect(source).toContain('font-size: 11px;')
    expect(source).toContain('--markdown-body: rgb(148 163 184);')
    expect(source).toContain('.message-markdown.message-reasoning :deep(.message-markdown__paragraph)')
  })

  it('renders rich markdown with the same token classes inside user bubbles', () => {
    const wrapper = mount(MessageList, {
      props: {
        isDraft: false,
        sessionStatus: 'completed',
        messages: [
          {
            id: 'msg-user-markdown',
            role: 'user',
            agent: 'geo',
            created_at: '',
            parts: [
              {
                type: 'text',
                text: '## User Markdown\n\n- item\n\n`code`',
              },
            ],
          },
        ],
      },
    })

    expect(wrapper.find('.message-bubble--user').exists()).toBe(true)
    expect(wrapper.get('h2').classes()).toContain('message-markdown__heading')
    expect(wrapper.get('ul').classes()).toContain('message-markdown__list')
    expect(wrapper.get('code').classes()).toContain('message-markdown__code--inline')
  })

  it('keeps the latest assistant turn visible while the runtime is still streaming hidden parts', async () => {
    const wrapper = mount(MessageList, {
      props: {
        isDraft: false,
        sessionStatus: 'running',
        messages: [
          {
            id: 'msg-user-1',
            role: 'user',
            agent: 'geo',
            created_at: '',
            parts: [
              {
                type: 'text',
                text: '请简单回复一句“测试成功”。',
              },
            ],
          },
          {
            id: 'msg-assistant-1',
            role: 'assistant',
            agent: 'geo',
            created_at: '',
            parts: [
              { type: 'step-start' },
              { type: 'reasoning', text: '正在形成最终回复。' },
            ],
          },
        ],
      },
    })

    expect(wrapper.text()).toContain('空间主理人')
    expect(wrapper.text()).toContain('正在思考...')

    await wrapper.setProps({
      messages: [
        {
          id: 'msg-user-1',
          role: 'user',
          agent: 'geo',
          created_at: '',
          parts: [
            {
              type: 'text',
              text: '请简单回复一句“测试成功”。',
            },
          ],
        },
        {
          id: 'msg-assistant-1',
          role: 'assistant',
          agent: 'geo',
          created_at: '',
          parts: [
            { type: 'step-start' },
            { type: 'reasoning', text: '正在形成最终回复。' },
            { type: 'text', text: '测试成功' },
            { type: 'step-finish' },
          ],
        },
      ],
    })

    expect(wrapper.text()).not.toContain('正在思考...')
    expect(wrapper.text()).toContain('测试成功')
  })

  it('renders streamed reasoning before the formal assistant reply when enabled', () => {
    const wrapper = mount(MessageList, {
      props: {
        isDraft: false,
        sessionStatus: 'running',
        showThinking: true,
        messages: [
          {
            id: 'msg-assistant-thinking',
            role: 'assistant',
            agent: 'geo',
            created_at: '',
            parts: [
              { type: 'step-start' },
              { type: 'reasoning', text: '正在形成最终回复。' },
              { type: 'text', text: '测试成功' },
            ],
          },
        ],
      } as never,
    })

    expect(wrapper.text()).toContain('正在形成最终回复。')
    expect(wrapper.text()).toContain('测试成功')
    expect(wrapper.text()).not.toContain('正在思考...')
    expect(wrapper.get('[data-testid="message-reasoning-toggle-msg-assistant-thinking"]').attributes('aria-expanded')).toBe('true')
    expect(wrapper.find('[data-testid="message-reasoning-toggle-icon-msg-assistant-thinking"]').exists()).toBe(true)
    expect(wrapper.html().indexOf('正在形成最终回复。')).toBeLessThan(wrapper.html().indexOf('测试成功'))
  })

  it('toggles inline thinking text without affecting the formal assistant reply', async () => {
    const wrapper = mount(MessageList, {
      props: {
        isDraft: false,
        sessionStatus: 'completed',
        showThinking: true,
        messages: [
          {
            id: 'msg-assistant-toggle-thinking',
            role: 'assistant',
            agent: 'geo',
            created_at: '',
            parts: [
              { type: 'reasoning', text: '正在检查输入点分布。' },
              { type: 'text', text: '分析完成。' },
            ],
          },
        ],
      } as never,
    })

    expect(wrapper.text()).toContain('正在检查输入点分布。')
    expect(wrapper.text()).toContain('分析完成。')

    await wrapper.get('[data-testid="message-reasoning-toggle-msg-assistant-toggle-thinking"]').trigger('click')

    expect(wrapper.text()).not.toContain('正在检查输入点分布。')
    expect(wrapper.text()).toContain('分析完成。')
    expect(wrapper.get('[data-testid="message-reasoning-toggle-msg-assistant-toggle-thinking"]').attributes('aria-expanded')).toBe('false')
  })

  it('renders reasoning-only assistant turns when enabled and keeps them hidden when disabled', () => {
    const enabledWrapper = mount(MessageList, {
      props: {
        isDraft: false,
        sessionStatus: 'completed',
        showThinking: true,
        messages: [
          {
            id: 'msg-assistant-reasoning-only',
            role: 'assistant',
            agent: 'geo',
            created_at: '',
            parts: [
              { type: 'reasoning', text: '正在检查 CRS 与带宽设置。' },
            ],
          },
        ],
      } as never,
    })

    expect(enabledWrapper.text()).toContain('正在检查 CRS 与带宽设置。')

    const disabledWrapper = mount(MessageList, {
      props: {
        isDraft: false,
        sessionStatus: 'completed',
        showThinking: false,
        messages: [
          {
            id: 'msg-assistant-reasoning-only',
            role: 'assistant',
            agent: 'geo',
            created_at: '',
            parts: [
              { type: 'reasoning', text: '正在检查 CRS 与带宽设置。' },
            ],
          },
        ],
      } as never,
    })

    expect(disabledWrapper.text()).not.toContain('正在检查 CRS 与带宽设置。')
  })

  it('keeps following the stream when the user is already at the bottom', async () => {
    const wrapper = mount(MessageList, {
      props: {
        isDraft: false,
        sessionStatus: 'running',
        messages: [
          {
            id: 'msg-assistant-1',
            role: 'assistant',
            agent: 'geo',
            created_at: '',
            parts: [
              {
                type: 'text',
                text: '第一条回复',
              },
            ],
          },
        ],
      },
    })

    const scroller = wrapper.get('[data-testid="message-list-scroller"]').element as HTMLElement
    const metrics = installScrollMetrics(scroller, {
      scrollHeight: 600,
      clientHeight: 200,
      scrollTop: 400,
    })

    await wrapper.get('[data-testid="message-list-scroller"]').trigger('scroll')

    metrics.scrollHeight = 900
    await wrapper.setProps({
      messages: [
        {
          id: 'msg-assistant-1',
          role: 'assistant',
          agent: 'geo',
          created_at: '',
          parts: [
            {
              type: 'text',
              text: '第一条回复',
            },
          ],
        },
        {
          id: 'msg-assistant-2',
          role: 'assistant',
          agent: 'geo',
          created_at: '',
          parts: [
            {
              type: 'text',
              text: '第二条回复',
            },
          ],
        },
      ],
    })
    await nextTick()

    expect(metrics.scrollTop).toBe(700)
  })

  it('does not auto-scroll while the user is reading older transcript content', async () => {
    const wrapper = mount(MessageList, {
      props: {
        isDraft: false,
        sessionStatus: 'running',
        messages: [
          {
            id: 'msg-assistant-1',
            role: 'assistant',
            agent: 'geo',
            created_at: '',
            parts: [
              {
                type: 'text',
                text: '第一条回复',
              },
            ],
          },
        ],
      },
    })

    const scroller = wrapper.get('[data-testid="message-list-scroller"]').element as HTMLElement
    const metrics = installScrollMetrics(scroller, {
      scrollHeight: 600,
      clientHeight: 200,
      scrollTop: 180,
    })

    await wrapper.get('[data-testid="message-list-scroller"]').trigger('scroll')

    metrics.scrollHeight = 900
    await wrapper.setProps({
      messages: [
        {
          id: 'msg-assistant-1',
          role: 'assistant',
          agent: 'geo',
          created_at: '',
          parts: [
            {
              type: 'text',
              text: '第一条回复',
            },
          ],
        },
        {
          id: 'msg-assistant-2',
          role: 'assistant',
          agent: 'geo',
          created_at: '',
          parts: [
            {
              type: 'text',
              text: '第二条回复',
            },
          ],
        },
      ],
    })
    await nextTick()

    expect(metrics.scrollTop).toBe(180)
  })

  it('keeps bottom-pinned transcript viewers attached when markdown images load later', async () => {
    const wrapper = mount(MessageList, {
      props: {
        isDraft: false,
        sessionStatus: 'running',
        messages: [
          {
            id: 'msg-assistant-image',
            role: 'assistant',
            agent: 'geo',
            created_at: '',
            parts: [
              {
                type: 'text',
                text: '![Map](https://example.com/map.png)',
              },
            ],
          },
        ],
      },
    })

    const scroller = wrapper.get('[data-testid="message-list-scroller"]').element as HTMLElement
    const metrics = installScrollMetrics(scroller, {
      scrollHeight: 600,
      clientHeight: 200,
      scrollTop: 400,
    })

    await wrapper.get('[data-testid="message-list-scroller"]').trigger('scroll')

    metrics.scrollHeight = 900
    await wrapper.get('.message-markdown__image').trigger('load')

    expect(metrics.scrollTop).toBe(700)
  })
})
