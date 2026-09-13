import type { Artifact, ChatMessage, ChatMessagePart, Session } from '../../types'
import { canonicalToolName } from '../../shared/toolIdentity'

export type TranscriptRenderItem =
  | { type: 'message', message: ChatMessage }
  | { type: 'final_artifacts', artifacts: Artifact[] }

export interface TranscriptRenderModelInput {
  messages: ChatMessage[]
  artifacts: Artifact[]
  finalArtifacts: Artifact[]
  showThinking: boolean
  sessionStatus: Session['status'] | null
}

export interface TranscriptRenderModel {
  items: TranscriptRenderItem[]
  messages: ChatMessage[]
  visibleMessages: ChatMessage[]
}

const STRUCTURED_PART_TYPES = new Set(['todo', 'verification', 'artifact', 'question', 'issue', 'skill_use'])

function messageTimestamp(message: ChatMessage): number | null {
  const timestamp = Date.parse(message.created_at)
  return Number.isFinite(timestamp) ? timestamp : null
}

function sortMessagesForDisplay(entries: ChatMessage[]): ChatMessage[] {
  return entries
    .map((message, index) => ({
      message,
      index,
      timestamp: messageTimestamp(message),
    }))
    .sort((left, right) => {
      if (left.timestamp === null || right.timestamp === null || left.timestamp === right.timestamp) {
        return left.index - right.index
      }
      return left.timestamp - right.timestamp
    })
    .map(({ message }) => message)
}

function textParts(message: ChatMessage): ChatMessagePart[] {
  return message.parts.filter((part) => part.type === 'text' && (part.text?.trim() ?? '').length > 0)
}

function reasoningParts(message: ChatMessage): ChatMessagePart[] {
  return message.parts.filter((part) => part.type === 'reasoning' && (part.text?.trim() ?? '').length > 0)
}

function visibleReasoningParts(message: ChatMessage, showThinking: boolean): ChatMessagePart[] {
  return showThinking ? reasoningParts(message) : []
}

function structuredParts(message: ChatMessage): ChatMessagePart[] {
  return message.parts.filter((part) => STRUCTURED_PART_TYPES.has(part.type))
}

function toolFamily(part: ChatMessagePart): string {
  const meta = part.state && typeof part.state === 'object' ? part.state.meta : null
  const record = meta && typeof meta === 'object' ? meta as Record<string, unknown> : null
  return typeof record?.tool_family === 'string' ? record.tool_family : ''
}

function visibleToolParts(message: ChatMessage): ChatMessagePart[] {
  return message.parts.filter((part) => (
    part.type === 'tool'
    && !['question', 'task'].includes(toolFamily(part))
    && !['question', 'task'].includes(part.tool ?? '')
  ))
}

function latestAssistantMessageId(messages: ChatMessage[]): string | null {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    if (messages[index]?.role === 'assistant') {
      return messages[index].id
    }
  }
  return null
}

function hasBubbleContent(message: ChatMessage, showThinking: boolean): boolean {
  return textParts(message).length > 0
    || visibleReasoningParts(message, showThinking).length > 0
    || structuredParts(message).length > 0
    || message.parts.some((part) => part.type === 'subtask')
    || message.role === 'user'
}

function shouldShowStreamingPlaceholder(message: ChatMessage, messages: ChatMessage[], sessionStatus: Session['status'] | null, showThinking: boolean): boolean {
  return sessionStatus === 'running'
    && message.role === 'assistant'
    && message.id === latestAssistantMessageId(messages)
    && !hasBubbleContent(message, showThinking)
    && visibleToolParts(message).length === 0
}

function shouldRenderMessage(message: ChatMessage, messages: ChatMessage[], sessionStatus: Session['status'] | null, showThinking: boolean): boolean {
  return hasBubbleContent(message, showThinking)
    || visibleToolParts(message).length > 0
    || shouldShowStreamingPlaceholder(message, messages, sessionStatus, showThinking)
}

function toolInput(part: ChatMessagePart): Record<string, unknown> | null {
  const input = part.state && typeof part.state === 'object' ? part.state.input : null
  return input && typeof input === 'object' ? input as Record<string, unknown> : null
}

function toolOutput(part: ChatMessagePart): unknown {
  return part.state && typeof part.state === 'object' ? part.state.output : null
}

function toolOutputIsError(part: ChatMessagePart): boolean {
  const output = toolOutput(part)
  return typeof output === 'string' && output.trimStart().startsWith('<error ')
}

function outputRecordId(output: unknown): string | null {
  if (typeof output === 'string') {
    const xmlMatch = output.match(/<record_id>\s*([^<]+?)\s*<\/record_id>/)
    if (xmlMatch?.[1]) {
      return xmlMatch[1].trim()
    }
    try {
      const parsed = JSON.parse(output) as Record<string, unknown>
      return typeof parsed.record_id === 'string' ? parsed.record_id : null
    } catch {
      return null
    }
  }
  if (output && typeof output === 'object' && typeof (output as Record<string, unknown>).record_id === 'string') {
    return (output as Record<string, string>).record_id
  }
  return null
}

function pathKey(value: unknown): string {
  return typeof value === 'string'
    ? value.trim().replace(/^\.\/+/, '').replace(/\/+$/g, '')
    : ''
}

function matchingIntermediateArtifact(part: ChatMessagePart, artifacts: Artifact[]): Artifact | null {
  if (canonicalToolName(part.tool) !== 'record_run_evidence' || toolOutputIsError(part)) {
    return null
  }
  const input = toolInput(part)
  if (!input || input.record_type !== 'artifact' || input.artifact_stage !== 'intermediate') {
    return null
  }

  const recordId = outputRecordId(toolOutput(part))
  const requestedPath = pathKey(input.path)
  const candidates = artifacts.filter((artifact) => artifact.artifact_stage === 'intermediate')

  if (recordId) {
    const byRecord = candidates.find((artifact) => artifact.evidence_record_id === recordId)
    if (byRecord) {
      return byRecord
    }
    if (candidates.some((artifact) => artifact.evidence_record_id)) {
      return null
    }
  }

  if (!requestedPath) {
    return null
  }

  return candidates.find((artifact) => pathKey(artifact.path) === requestedPath) ?? null
}

function skillNameFromInput(input: Record<string, unknown> | null): string {
  if (!input) {
    return '运行时技能'
  }
  for (const key of ['skill', 'name', 'skill_name', 'path']) {
    const value = input[key]
    if (typeof value === 'string' && value.trim()) {
      return value.trim()
    }
  }
  return '运行时技能'
}

function transformPart(part: ChatMessagePart, artifacts: Artifact[]): ChatMessagePart {
  if (part.type !== 'tool') {
    return part
  }

  const matchedArtifact = matchingIntermediateArtifact(part, artifacts)
  if (matchedArtifact) {
    return {
      type: 'artifact',
      state: matchedArtifact as unknown as Record<string, unknown>,
    }
  }

  if (canonicalToolName(part.tool) === 'skill') {
    const input = toolInput(part)
    return {
      type: 'skill_use',
      state: {
        skill: skillNameFromInput(input),
        input: input ?? {},
      },
    }
  }

  return part
}

function isSyntheticInlineArtifactMessage(message: ChatMessage): boolean {
  return message.id.startsWith('inline-intermediate-artifact-')
    && message.parts.some((part) => part.type === 'artifact')
}

function transformMessage(message: ChatMessage, artifacts: Artifact[]): ChatMessage | null {
  if (isSyntheticInlineArtifactMessage(message)) {
    return null
  }
  return {
    ...message,
    parts: message.parts.map((part) => transformPart(part, artifacts)),
  }
}

export function buildTranscriptRenderModel(input: TranscriptRenderModelInput): TranscriptRenderModel {
  const sortedMessages = sortMessagesForDisplay(input.messages)
  const transformedMessages = sortedMessages
    .map((message) => transformMessage(message, input.artifacts))
    .filter((message): message is ChatMessage => message !== null)
  const visibleMessages = transformedMessages.filter((message) => shouldRenderMessage(message, transformedMessages, input.sessionStatus, input.showThinking))
  const items: TranscriptRenderItem[] = visibleMessages.map((message) => ({ type: 'message', message }))

  if (input.finalArtifacts.length) {
    items.push({ type: 'final_artifacts', artifacts: input.finalArtifacts })
  }

  return {
    items,
    messages: transformedMessages,
    visibleMessages,
  }
}
