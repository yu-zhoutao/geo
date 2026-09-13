import { describe, expect, it } from 'vitest'

import type { Artifact, ChatMessage } from '../../types'
import { buildTranscriptRenderModel } from './transcriptRenderModel'

const baseMessage: ChatMessage = {
  id: 'msg-1',
  role: 'assistant',
  agent: 'geo',
  created_at: '2026-04-27T10:00:00.000Z',
  parts: [],
}

function message(overrides: Partial<ChatMessage>): ChatMessage {
  return {
    ...baseMessage,
    ...overrides,
    parts: overrides.parts ?? [],
  }
}

function artifact(overrides: Partial<Artifact>): Artifact {
  return {
    id: 'artifact-1',
    title: '中间产物',
    path: 'outputs/params.md',
    artifact_stage: 'intermediate',
    display_hint: 'markdown',
    evidence_record_id: 'evidence-1234',
    ...overrides,
  }
}

describe('transcript render model', () => {
  it('removes completed thinking-only messages when thinking is hidden', () => {
    const model = buildTranscriptRenderModel({
      messages: [
        message({
          id: 'msg-thinking',
          parts: [{ type: 'reasoning', text: '检查 CRS。' }],
        }),
      ],
      artifacts: [],
      finalArtifacts: [],
      showThinking: false,
      sessionStatus: 'completed',
    })

    expect(model.visibleMessages).toHaveLength(0)
    expect(model.items).toHaveLength(0)
  })

  it('keeps the latest thinking-only assistant placeholder while a session is running', () => {
    const model = buildTranscriptRenderModel({
      messages: [
        message({
          id: 'msg-thinking',
          parts: [{ type: 'reasoning', text: '检查 CRS。' }],
        }),
      ],
      artifacts: [],
      finalArtifacts: [],
      showThinking: false,
      sessionStatus: 'running',
    })

    expect(model.visibleMessages.map((entry) => entry.id)).toEqual(['msg-thinking'])
    expect(model.items.map((entry) => entry.type)).toEqual(['message'])
  })

  it('replaces a matched intermediate artifact registration tool part at its original position', () => {
    const model = buildTranscriptRenderModel({
      messages: [
        message({
          id: 'msg-evidence-tool',
          parts: [
            { type: 'text', text: '先登记参数。' },
            {
              type: 'tool',
              tool: 'geospatial_record_run_evidence',
              state: {
                input: {
                  record_type: 'artifact',
                  artifact_stage: 'intermediate',
                  path: 'outputs/params.md',
                },
                output: '<evidence status="recorded" type="artifact"><record_id>evidence-1234</record_id></evidence>',
              },
            },
            { type: 'text', text: '继续执行。' },
          ],
        }),
      ],
      artifacts: [artifact({})],
      finalArtifacts: [],
      showThinking: false,
      sessionStatus: 'completed',
    })

    expect(model.visibleMessages).toHaveLength(1)
    expect(model.visibleMessages[0].parts.map((part) => part.type)).toEqual(['text', 'artifact', 'text'])
    expect(model.visibleMessages[0].parts[1].state).toMatchObject({
      id: 'artifact-1',
      path: 'outputs/params.md',
    })
  })

  it('keeps an ambiguous intermediate artifact tool row instead of appending a synthetic artifact', () => {
    const model = buildTranscriptRenderModel({
      messages: [
        message({
          id: 'msg-evidence-tool',
          parts: [
            {
              type: 'tool',
              tool: 'geospatial_record_run_evidence',
              state: {
                input: {
                  record_type: 'artifact',
                  artifact_stage: 'intermediate',
                  path: 'outputs/params.md',
                },
                output: '<evidence status="recorded" type="artifact"><record_id>different</record_id></evidence>',
              },
            },
          ],
        }),
      ],
      artifacts: [artifact({ evidence_record_id: 'evidence-1234' })],
      finalArtifacts: [],
      showThinking: false,
      sessionStatus: 'completed',
    })

    expect(model.visibleMessages).toHaveLength(1)
    expect(model.visibleMessages[0].parts.map((part) => part.type)).toEqual(['tool'])
    expect(model.items).toHaveLength(1)
  })

  it('does not replace final artifact registration tools inline', () => {
    const finalArtifact = artifact({
      id: 'artifact-final',
      artifact_stage: 'final',
      evidence_record_id: 'evidence-final',
      path: 'outputs/report.md',
    })
    const model = buildTranscriptRenderModel({
      messages: [
        message({
          id: 'msg-final-tool',
          parts: [
            {
              type: 'tool',
              tool: 'geospatial_record_run_evidence',
              state: {
                input: {
                  record_type: 'artifact',
                  artifact_stage: 'final',
                  path: 'outputs/report.md',
                },
                output: '<record_id>evidence-final</record_id>',
              },
            },
          ],
        }),
      ],
      artifacts: [finalArtifact],
      finalArtifacts: [finalArtifact],
      showThinking: false,
      sessionStatus: 'completed',
    })

    expect(model.visibleMessages[0].parts.map((part) => part.type)).toEqual(['tool'])
    expect(model.items.map((item) => item.type)).toEqual(['message', 'final_artifacts'])
  })

  it('renders explicit skill tool use as a compact skill-use part', () => {
    const model = buildTranscriptRenderModel({
      messages: [
        message({
          id: 'msg-skill',
          parts: [
            {
              type: 'tool',
              tool: 'skill',
              state: {
                input: {
                  skill: 'geospatial-crs-projection-safety',
                },
                output: 'loaded',
              },
            },
          ],
        }),
      ],
      artifacts: [],
      finalArtifacts: [],
      showThinking: false,
      sessionStatus: 'completed',
    })

    expect(model.visibleMessages[0].parts).toEqual([
      expect.objectContaining({
        type: 'skill_use',
        state: expect.objectContaining({ skill: 'geospatial-crs-projection-safety' }),
      }),
    ])
  })
})
