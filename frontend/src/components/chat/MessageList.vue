<script setup lang="ts">
import ChevronDownIcon from 'bootstrap-icons/icons/chevron-down.svg'
import QuestionCircleIcon from 'bootstrap-icons/icons/question-circle.svg'
import { computed, nextTick, onBeforeUnmount, onMounted, onUpdated, ref, watch } from 'vue'
import type { Artifact, ChatMessage, Question, QuestionItem, QuestionReplyPayload } from '../../types'
import agentIdentity from '../../shared/agentIdentity.json'
import ToolCallBlock from './ToolCallBlock.vue'
import ArtifactInlineBlock from './ArtifactInlineBlock.vue'
import FinalArtifactCarousel from './FinalArtifactCarousel.vue'
import { renderMarkdown } from './markdown'
import { buildTranscriptRenderModel } from './transcriptRenderModel'

const props = defineProps<{
  messages: ChatMessage[]
  isDraft: boolean
  sessionStatus: 'idle' | 'running' | 'waiting_for_input' | 'completed' | 'failed' | null
  showThinking?: boolean
  activeQuestion?: Question | null
  activeSessionId?: string | null
  artifacts?: Artifact[]
  finalArtifacts?: Artifact[]
  artifactActionsDisabled?: boolean
}>()

const emit = defineEmits<{
  (e: 'reply-question', payload: QuestionReplyPayload): void
  (e: 'open-artifact', artifact: Artifact): void
  (e: 'preview-artifact', artifact: Artifact): void
}>()

const isDraft = computed(() => props.isDraft)
const sessionStatus = computed(() => props.sessionStatus)
const showThinking = computed(() => props.showThinking ?? false)
const activeQuestion = computed(() => props.activeQuestion ?? null)

const listRef = ref<HTMLElement | null>(null)
const collapsedReasoningMessageIds = ref<Set<string>>(new Set())
const shouldStickToBottom = ref(true)
const trackedMarkdownImages = new WeakSet<HTMLImageElement>()
const inlineQuestionIndex = ref(0)
const inlineQuestionAnswers = ref<string[]>([])
const inlineQuestionComposing = ref(false)
const inlineQuestionInputRef = ref<HTMLInputElement | null>(null)
const contextMenu = ref<{ messageId: string, left: number, top: number } | null>(null)
const agentProfilePopover = ref<{ agentId: string, left: number, top: number } | null>(null)

const SCROLL_BOTTOM_THRESHOLD = 32
const INLINE_FALLBACK_HEADER = '问题'
const DEFAULT_AGENT_AVATAR = '/agent-avatar/geo-orchestrator.png'
const CONTEXT_MENU_OFFSET = 10
const PROFILE_CARD_GAP = 12
const PROFILE_CARD_WIDTH = 304
const PROFILE_CARD_HEIGHT = 216
const PROFILE_VIEWPORT_PADDING = 16

type AgentPresentation = {
  label: string
  avatar: string
  summary: string
}

type IssuePartState = {
  title?: string
  detail?: string
  severity?: string
  source?: string
  runtime_session_id?: string | null
  trace_path?: string | null
}

const AGENT_PRESENTATIONS: Record<string, AgentPresentation> = agentIdentity

const renderModel = computed(() => buildTranscriptRenderModel({
  messages: props.messages,
  artifacts: props.artifacts ?? [],
  finalArtifacts: props.finalArtifacts ?? [],
  showThinking: showThinking.value,
  sessionStatus: sessionStatus.value,
}))
const messages = computed(() => renderModel.value.messages)
const displayedMessages = computed(() => renderModel.value.visibleMessages)
const displayedMessageIndexes = computed(() => (
  new Map(displayedMessages.value.map((message, index) => [message.id, index]))
))

function bottomScrollTop(element: HTMLElement): number {
  return Math.max(element.scrollHeight - element.clientHeight, 0)
}

function isNearBottom(element: HTMLElement): boolean {
  return element.scrollHeight - element.clientHeight - element.scrollTop <= SCROLL_BOTTOM_THRESHOLD
}

function scrollToBottom(element: HTMLElement): void {
  element.scrollTop = bottomScrollTop(element)
}

function handleScroll(): void {
  if (!listRef.value) {
    return
  }

  shouldStickToBottom.value = isNearBottom(listRef.value)
}

function registerPendingImageLoads(): void {
  if (!listRef.value) {
    return
  }

  const images = listRef.value.querySelectorAll<HTMLImageElement>('.message-markdown__image')

  for (const image of images) {
    if (trackedMarkdownImages.has(image)) {
      continue
    }

    trackedMarkdownImages.add(image)

    if (image.complete) {
      continue
    }

    image.addEventListener('load', () => {
      if (listRef.value && shouldStickToBottom.value) {
        scrollToBottom(listRef.value)
      }
    }, { once: true })
  }
}

function closeMessageContextMenu(): void {
  contextMenu.value = null
}

function closeAgentProfilePopover(): void {
  agentProfilePopover.value = null
}

function handleDocumentPointerdown(event: PointerEvent): void {
  const target = event.target
  if (target instanceof Element && target.closest('[data-testid="message-context-menu"]')) {
    return
  }

  const clickedInsideProfile = target instanceof Element && target.closest('[data-testid="agent-profile-popover"]')
  const clickedAgentTrigger = target instanceof Element && (
    target.closest('[data-testid^="message-agent-avatar-button-"]')
    || target.closest('[data-testid^="subtask-mention-"]')
  )

  if (contextMenu.value) {
    closeMessageContextMenu()
  }

  if (agentProfilePopover.value && !clickedInsideProfile && !clickedAgentTrigger) {
    closeAgentProfilePopover()
  }
}

function handleDocumentKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape') {
    closeMessageContextMenu()
    closeAgentProfilePopover()
  }
}

onMounted(() => {
  document.addEventListener('pointerdown', handleDocumentPointerdown)
  document.addEventListener('keydown', handleDocumentKeydown)

  if (listRef.value) {
    registerPendingImageLoads()
    scrollToBottom(listRef.value)
    shouldStickToBottom.value = true
  }
})

onUpdated(() => {
  registerPendingImageLoads()

  if (listRef.value && shouldStickToBottom.value) {
    scrollToBottom(listRef.value)
  }
})

onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', handleDocumentPointerdown)
  document.removeEventListener('keydown', handleDocumentKeydown)
})

function inlineQuestionItems(question: Question | null | undefined): QuestionItem[] {
  if (!question) {
    return []
  }
  if (question.questions?.length) {
    return question.questions
  }
  return [{
    header: INLINE_FALLBACK_HEADER,
    question: question.prompt,
    options: [],
  }]
}

function resetInlineQuestionState(question: Question | null | undefined): void {
  inlineQuestionAnswers.value = inlineQuestionItems(question).map(() => '')
  inlineQuestionIndex.value = 0
  inlineQuestionComposing.value = false
}

function focusInlineQuestionInput(): void {
  const input = inlineQuestionInputRef.value
  if (input && typeof input.focus === 'function') {
    input.focus()
  }
}

watch(
  () => activeQuestion.value?.id,
  async () => {
    resetInlineQuestionState(activeQuestion.value)
    await nextTick()
    focusInlineQuestionInput()
  },
  { immediate: true },
)

function renderText(text: string | null | undefined): string {
  return renderMarkdown(text ?? '')
}

function agentPresentation(agent: string | null | undefined): AgentPresentation {
  if (!agent) {
    return {
      label: '运行时角色',
      avatar: DEFAULT_AGENT_AVATAR,
      summary: '负责承载会话运行时中的技术性事件。',
    }
  }

  const presentation = AGENT_PRESENTATIONS[agent]
  if (presentation) {
    return presentation
  }

  return {
    label: agent,
    avatar: DEFAULT_AGENT_AVATAR,
    summary: '这是一个未在当前前端角色映射中注册的运行时角色。',
  }
}

function todoEntries(message: ChatMessage, index: number): Array<{ id: string, label: string, status: string }> {
  const entries = message.parts[index]?.state && 'entries' in message.parts[index].state!
    ? (message.parts[index].state?.entries as Array<{ id: string, label: string, status: string }> | undefined)
    : undefined
  return entries ?? []
}

function verificationEntries(message: ChatMessage, index: number): Array<{ id: string, title: string, status: string, detail: string }> {
  const entries = message.parts[index]?.state && 'entries' in message.parts[index].state!
    ? (message.parts[index].state?.entries as Array<{ id: string, title: string, status: string, detail: string }> | undefined)
    : undefined
  return entries ?? []
}

function artifactState(message: ChatMessage, index: number): Artifact {
  const state = message.parts[index]?.state
  if (!state || typeof state !== 'object') {
    return {
      id: `${message.id}-artifact-${index}`,
      title: '运行产物',
      path: '',
    }
  }
  const payload = state as Record<string, unknown>
  return {
    ...payload,
    id: typeof payload.id === 'string' ? payload.id : `${message.id}-artifact-${index}`,
    title: typeof payload.title === 'string' ? payload.title : '运行产物',
    path: typeof payload.path === 'string' ? payload.path : '',
  } as Artifact
}

function skillUseLabel(message: ChatMessage, index: number): string {
  const state = message.parts[index]?.state
  if (!state || typeof state !== 'object' || typeof state.skill !== 'string' || !state.skill.trim()) {
    return '运行时技能'
  }
  return state.skill.trim()
}

function issueState(message: ChatMessage, index: number): IssuePartState {
  const state = message.parts[index]?.state
  if (!state || typeof state !== 'object') {
    return {}
  }
  return state as IssuePartState
}

function issueSeverityLabel(severity: string | undefined): string {
  if (severity === 'error') return '错误'
  if (severity === 'warning') return '提醒'
  return '信息'
}

function issueSourceLabel(source: string | undefined): string {
  if (source === 'opencode') return 'OpenCode'
  if (source === 'runtime') return '运行时'
  if (source === 'mcp') return '工具'
  if (source === 'frontend') return '前端连接'
  return '系统'
}

function issueInlineClass(severity: string | undefined): string {
  if (severity === 'error') {
    return 'text-rose-600 dark:text-rose-300'
  }
  if (severity === 'warning') {
    return 'text-amber-700 dark:text-amber-300'
  }
  return 'text-sky-700 dark:text-cyan-300'
}

function issueTooltip(issue: IssuePartState, fallbackTitle: string | null | undefined): string {
  const parts: string[] = [
    issueSeverityLabel(issue.severity),
    issue.title || fallbackTitle,
    issue.detail,
    issueSourceLabel(issue.source),
    issue.runtime_session_id ?? undefined,
    issue.trace_path ?? undefined,
  ].filter((part): part is string => Boolean(part))

  return parts.join(' · ')
}

function issueDisplayDetail(issue: IssuePartState, fallbackTitle: string | null | undefined): string {
  return issue.detail || issue.title || fallbackTitle || '运行出现问题'
}

function questionText(message: ChatMessage, index: number): string {
  return message.parts[index]?.text ?? ''
}

function questionItems(message: ChatMessage, index: number): Array<{ header: string, question: string, options: Array<{ label: string, description?: string | null }> }> {
  const state = message.parts[index]?.state
  if (!state || typeof state !== 'object' || !Array.isArray(state.questions)) {
    return []
  }
  return state.questions as Array<{ header: string, question: string, options: Array<{ label: string, description?: string | null }> }>
}

function questionRequestId(message: ChatMessage, index: number): string | null {
  const state = message.parts[index]?.state
  if (!state || typeof state !== 'object' || typeof state.id !== 'string') {
    return null
  }
  return state.id
}

function questionToolAnswers(message: ChatMessage, index: number, messages: ChatMessage[]): string[] {
  const prompt = questionText(message, index)
  const items = questionItems(message, index)

  for (let messageIndex = messages.length - 1; messageIndex >= 0; messageIndex -= 1) {
    const candidate = messages[messageIndex]

    for (const part of candidate.parts) {
      if (part.type !== 'tool' || part.tool !== 'question' || !part.state || typeof part.state !== 'object') {
        continue
      }

      const state = part.state as Record<string, unknown>
      const input = state.input && typeof state.input === 'object' ? state.input as Record<string, unknown> : null
      const questions = input && Array.isArray(input.questions)
        ? input.questions as Array<Record<string, unknown>>
        : []

      if (!questions.length || questions[0]?.question !== prompt || questions.length !== items.length) {
        continue
      }

      const metadata = state.metadata && typeof state.metadata === 'object' ? state.metadata as Record<string, unknown> : null
      const rawAnswers = metadata && Array.isArray(metadata.answers) ? metadata.answers : []
      const answers = rawAnswers
        .map((entry) => Array.isArray(entry) ? entry.find((value): value is string => typeof value === 'string' && value.trim().length > 0) : null)
        .filter((value): value is string => Boolean(value))

      if (answers.length) {
        return answers
      }
    }
  }

  return []
}

function questionAnswerEntries(message: ChatMessage, index: number, messages: ChatMessage[]): Array<{ header: string, value: string }> {
  const requestId = questionRequestId(message, index)
  const items = questionItems(message, index)
  if (!requestId) {
    const toolAnswers = questionToolAnswers(message, index, messages)
    return toolAnswers.map((value, answerIndex) => ({
      header: items[answerIndex]?.header ?? `问题 ${answerIndex + 1}`,
      value,
    }))
  }

  for (let messageIndex = messages.length - 1; messageIndex >= 0; messageIndex -= 1) {
    const candidate = messages[messageIndex]
    if (candidate.role !== 'user') {
      continue
    }

    for (const part of candidate.parts) {
      if (part.type !== 'text' || !part.state || typeof part.state !== 'object') {
        continue
      }

      const state = part.state as Record<string, unknown>
      if (state.question_id !== requestId) {
        continue
      }

      const answers = Array.isArray(state.question_answers)
        ? state.question_answers.filter((value): value is string => typeof value === 'string' && value.trim().length > 0)
        : []

      if (!answers.length) {
        const text = part.text?.trim()
        return text ? [{ header: '回答', value: text }] : []
      }

      return answers.map((value, answerIndex) => ({
        header: items[answerIndex]?.header ?? `问题 ${answerIndex + 1}`,
        value,
      }))
    }
  }

  return questionToolAnswers(message, index, messages).map((value, answerIndex) => ({
    header: items[answerIndex]?.header ?? `问题 ${answerIndex + 1}`,
    value,
  }))
}

function questionAnswerEntryAt(message: ChatMessage, index: number, messages: ChatMessage[], answerIndex: number): { header: string, value: string } | null {
  return questionAnswerEntries(message, index, messages)[answerIndex] ?? null
}

function messageHasQuestionPart(message: ChatMessage): boolean {
  return message.parts.some((part) => part.type === 'question')
}

function messageHasSubtaskPart(message: ChatMessage): boolean {
  return message.parts.some((part) => part.type === 'subtask')
}

function issueParts(message: ChatMessage) {
  return message.parts.filter((part) => part.type === 'issue')
}

function inlineIssueNoticeMessage(message: ChatMessage, showThinkingEnabled: boolean): boolean {
  const issues = issueParts(message)
  return message.role !== 'user'
    && issues.length > 0
    && textParts(message).length === 0
    && visibleReasoningParts(message, showThinkingEnabled).length === 0
    && structuredParts(message).length === issues.length
    && visibleToolParts(message).length === 0
    && !messageHasSubtaskPart(message)
}

function standaloneQuestionMessage(message: ChatMessage, showThinkingEnabled: boolean): boolean {
  return messageHasQuestionPart(message)
    && textParts(message).length === 0
    && visibleReasoningParts(message, showThinkingEnabled).length === 0
    && visibleToolParts(message).length === 0
}

function questionMessageHasActivePart(message: ChatMessage): boolean {
  return message.parts.some((part, index) => part.type === 'question' && isActiveQuestionPart(message, index))
}

function standaloneActiveQuestionMessage(message: ChatMessage, showThinkingEnabled: boolean): boolean {
  return standaloneQuestionMessage(message, showThinkingEnabled) && questionMessageHasActivePart(message)
}

function assistantRowClass(message: ChatMessage, showThinkingEnabled: boolean): string {
  return inlineIssueNoticeMessage(message, showThinkingEnabled)
    ? 'mx-auto flex w-full max-w-[88%] items-start'
    : 'flex w-full max-w-[92%] items-start gap-3'
}

function assistantContentClass(message: ChatMessage, showThinkingEnabled: boolean): string {
  if (standaloneActiveQuestionMessage(message, showThinkingEnabled)) {
    return 'w-full max-w-[88%]'
  }
  if (inlineIssueNoticeMessage(message, showThinkingEnabled)) {
    return 'w-full'
  }
  return 'max-w-[88%]'
}

function assistantBubbleClass(message: ChatMessage, showThinkingEnabled: boolean): string {
  if (inlineIssueNoticeMessage(message, showThinkingEnabled)) {
    return 'message-bubble--assistant bg-transparent px-0 py-0 text-slate-900 shadow-none dark:text-slate-100'
  }
  if (standaloneQuestionMessage(message, showThinkingEnabled)) {
    return 'message-bubble--assistant bg-transparent px-0 py-0 text-slate-900 shadow-none ring-0 dark:text-slate-100'
  }
  return 'message-bubble--assistant rounded-xl bg-white/90 px-3 py-2 text-slate-900 shadow-sm ring-1 ring-slate-200/70 dark:bg-zinc-900/80 dark:text-slate-100 dark:ring-white/8'
}

function questionOriginAgent(message: ChatMessage, messages: ChatMessage[]): string | null | undefined {
  const messageIndex = messages.findIndex((candidate) => candidate.id === message.id)
  if (messageIndex <= 0) {
    return null
  }

  for (let index = messageIndex - 1; index >= 0; index -= 1) {
    const candidate = messages[index]
    if (candidate.role !== 'assistant') {
      continue
    }
    if (candidate.parts.some((part) => part.type === 'tool' && part.tool === 'question')) {
      return candidate.agent
    }
  }
  return null
}

function messageAgentId(message: ChatMessage, allMessages: ChatMessage[] = messages.value): string | null | undefined {
  const subtaskPart = message.parts.find((part) => part.type === 'subtask')
  if (subtaskPart?.state && typeof subtaskPart.state === 'object' && typeof subtaskPart.state.parent_agent === 'string') {
    return subtaskPart.state.parent_agent
  }
  if (messageHasQuestionPart(message)) {
    return questionOriginAgent(message, allMessages) ?? message.agent
  }
  return message.agent
}

function messageAgentTitle(message: ChatMessage): string {
  return agentPresentation(messageAgentId(message)).label
}

function messageAgentAvatar(message: ChatMessage): string {
  return agentPresentation(messageAgentId(message)).avatar
}

function isActiveQuestionPart(message: ChatMessage, index: number): boolean {
  const activeQuestionId = activeQuestion.value?.id
  return Boolean(activeQuestionId) && questionRequestId(message, index) === activeQuestionId
}

function activeInlineQuestionItems(): QuestionItem[] {
  return inlineQuestionItems(activeQuestion.value)
}

function activeInlineQuestion(): QuestionItem | null {
  return activeInlineQuestionItems()[inlineQuestionIndex.value] ?? null
}

function activeInlineQuestionProgress(): string {
  const items = activeInlineQuestionItems()
  if (!items.length) {
    return '0/0 个问题'
  }
  return `${inlineQuestionIndex.value + 1}/${items.length} 个问题`
}

function activeInlineQuestionAnswer(index: number): string {
  return inlineQuestionAnswers.value[index] ?? ''
}

function activeInlineQuestionAnswered(index: number): boolean {
  return activeInlineQuestionAnswer(index).trim().length > 0
}

function activeInlineQuestionOptionSelected(label: string): boolean {
  return activeInlineQuestionAnswer(inlineQuestionIndex.value) === label
}

function setActiveInlineQuestionAnswer(index: number, value: string): void {
  const next = [...inlineQuestionAnswers.value]
  next[index] = value
  inlineQuestionAnswers.value = next
}

function activateInlineQuestion(index: number): void {
  if (index < 0 || index >= activeInlineQuestionItems().length) {
    return
  }
  inlineQuestionIndex.value = index
  void nextTick(() => focusInlineQuestionInput())
}

function submitInlineQuestionAnswers(): void {
  const answers = inlineQuestionAnswers.value.map((value) => value.trim())
  if (!activeQuestion.value || answers.some((value) => !value)) {
    return
  }
  emit('reply-question', { answers })
}

function advanceInlineQuestion(): void {
  const items = activeInlineQuestionItems()
  if (!items.length) {
    return
  }
  if (inlineQuestionIndex.value >= items.length - 1) {
    submitInlineQuestionAnswers()
    return
  }
  inlineQuestionIndex.value += 1
  void nextTick(() => focusInlineQuestionInput())
}

function selectInlineQuestionOption(label: string): void {
  setActiveInlineQuestionAnswer(inlineQuestionIndex.value, label)
  advanceInlineQuestion()
}

function updateInlineQuestionAnswer(value: string): void {
  setActiveInlineQuestionAnswer(inlineQuestionIndex.value, value)
}

function isInlineQuestionCompositionEvent(event: KeyboardEvent): boolean {
  const composingEvent = event as KeyboardEvent & { keyCode?: number, which?: number }
  return event.isComposing || inlineQuestionComposing.value || composingEvent.keyCode === 229 || composingEvent.which === 229
}

function handleInlineQuestionInputKeydown(event: KeyboardEvent): void {
  if ((event.key === 'Enter' || event.key === 'Tab') && isInlineQuestionCompositionEvent(event)) {
    return
  }
  if (event.key !== 'Enter' && event.key !== 'Tab') {
    return
  }
  if (!activeInlineQuestionAnswer(inlineQuestionIndex.value).trim()) {
    return
  }
  event.preventDefault()
  advanceInlineQuestion()
}

function statusLabel(status: string): string {
  if (status === 'completed' || status === 'passed') return '已完成'
  if (status === 'in_progress') return '进行中'
  if (status === 'warning') return '警告'
  if (status === 'failed') return '失败'
  return '待开始'
}

function textParts(message: ChatMessage) {
  return message.parts.filter((part) => part.type === 'text' && (part.text?.trim() ?? '').length > 0)
}

function reasoningParts(message: ChatMessage) {
  return message.parts.filter((part) => part.type === 'reasoning' && (part.text?.trim() ?? '').length > 0)
}

function visibleReasoningParts(message: ChatMessage, showThinkingEnabled: boolean) {
  return showThinkingEnabled ? reasoningParts(message) : []
}

function structuredParts(message: ChatMessage) {
  return message.parts.filter((part) => ['todo', 'verification', 'artifact', 'question', 'issue', 'skill_use'].includes(part.type))
}

function toolParts(message: ChatMessage) {
  return message.parts.filter((part) => part.type === 'tool')
}

function toolFamily(part: ChatMessage['parts'][number]): string {
  const meta = part.state && typeof part.state === 'object' ? part.state.meta : null
  const record = meta && typeof meta === 'object' ? meta as Record<string, unknown> : null
  if (record && typeof record.tool_family === 'string') {
    return record.tool_family
  }
  return ''
}

function visibleToolParts(message: ChatMessage) {
  return toolParts(message).filter((part) => !['question', 'task'].includes(toolFamily(part)) && !['question', 'task'].includes(part.tool ?? ''))
}

function hasBubbleContent(message: ChatMessage, showThinkingEnabled: boolean): boolean {
  return textParts(message).length > 0
    || visibleReasoningParts(message, showThinkingEnabled).length > 0
    || structuredParts(message).length > 0
    || messageHasSubtaskPart(message)
    || message.role === 'user'
}

function hasVisibleToolParts(message: ChatMessage): boolean {
  return visibleToolParts(message).length > 0
}

function latestAssistantMessageId(messages: ChatMessage[]): string | null {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    if (messages[index]?.role === 'assistant') {
      return messages[index].id
    }
  }
  return null
}

function shouldShowStreamingPlaceholder(message: ChatMessage, messages: ChatMessage[], sessionStatus: string | null, showThinkingEnabled: boolean): boolean {
  return sessionStatus === 'running'
    && message.role === 'assistant'
    && message.id === latestAssistantMessageId(messages)
    && !hasBubbleContent(message, showThinkingEnabled)
    && !hasVisibleToolParts(message)
}

function shouldRenderMessage(message: ChatMessage, messages: ChatMessage[], sessionStatus: string | null, showThinkingEnabled: boolean): boolean {
  return hasBubbleContent(message, showThinkingEnabled)
    || hasVisibleToolParts(message)
    || shouldShowStreamingPlaceholder(message, messages, sessionStatus, showThinkingEnabled)
}

function displayedMessageIndex(message: ChatMessage): number {
  return displayedMessageIndexes.value.get(message.id) ?? -1
}

function previousDisplayedMessage(message: ChatMessage): ChatMessage | null {
  const index = displayedMessageIndex(message)
  if (index <= 0) {
    return null
  }
  return displayedMessages.value[index - 1] ?? null
}

function nextDisplayedMessage(message: ChatMessage): ChatMessage | null {
  const index = displayedMessageIndex(message)
  if (index < 0) {
    return null
  }
  return displayedMessages.value[index + 1] ?? null
}

function isSystemNoticeMessage(message: ChatMessage): boolean {
  return message.role === 'system'
    && !messageAgentId(message)
    && !messageHasSubtaskPart(message)
    && textParts(message).length > 0
    && visibleReasoningParts(message, showThinking.value).length === 0
    && structuredParts(message).length === 0
    && !hasVisibleToolParts(message)
}

function continuesPreviousAgentRun(message: ChatMessage): boolean {
  if (message.role === 'user' || isSystemNoticeMessage(message) || !messageAgentId(message)) {
    return false
  }

  const previous = previousDisplayedMessage(message)
  if (!previous || previous.role === 'user' || isSystemNoticeMessage(previous)) {
    return false
  }

  return messageAgentId(previous) === messageAgentId(message)
}

function shouldShowMessageHeader(message: ChatMessage): boolean {
  if (
    message.role === 'user'
    || isSystemNoticeMessage(message)
    || inlineIssueNoticeMessage(message, showThinking.value)
    || !messageAgentId(message)
  ) {
    return false
  }

  return !continuesPreviousAgentRun(message)
}

function continuesNextAgentRun(message: ChatMessage): boolean {
  if (message.role === 'user' || isSystemNoticeMessage(message) || !messageAgentId(message)) {
    return false
  }

  const next = nextDisplayedMessage(message)
  if (!next || next.role === 'user' || isSystemNoticeMessage(next)) {
    return false
  }

  return messageAgentId(next) === messageAgentId(message)
}

function messageContainerClass(message: ChatMessage): string {
  if (isSystemNoticeMessage(message)) {
    return 'justify-center'
  }

  return message.role === 'user' ? 'justify-end' : 'justify-start'
}

function messageSpacingClass(message: ChatMessage): string {
  return continuesNextAgentRun(message) ? 'mb-1.5' : 'mb-3'
}

function messageTextContent(message: ChatMessage): string {
  return message.parts
    .filter((part) => part.type === 'text' && (part.text?.trim() ?? '').length > 0)
    .map((part) => part.text?.trim() ?? '')
    .join('\n\n')
    .trim()
}

function messageTextActionAvailable(message: ChatMessage): boolean {
  return messageTextContent(message).length > 0
}

function canOpenMessageContextMenu(message: ChatMessage): boolean {
  return !standaloneQuestionMessage(message, showThinking.value)
    && !isSystemNoticeMessage(message)
    && messageTextActionAvailable(message)
}

function subtaskState(message: ChatMessage, index: number): { parent_agent?: string, child_agent?: string, description?: string, prompt?: string, task_session_id?: string } {
  const state = message.parts[index]?.state
  if (!state || typeof state !== 'object') {
    return {}
  }
  return state as { parent_agent?: string, child_agent?: string, description?: string, prompt?: string, task_session_id?: string }
}

function subtaskChildLabel(message: ChatMessage, index: number): string {
  return agentPresentation(subtaskState(message, index).child_agent).label
}

function subtaskPromptText(message: ChatMessage, index: number): string {
  const { prompt, description } = subtaskState(message, index)
  return prompt?.trim() || description?.trim() || ''
}

function profilePopoverPosition(
  anchorRect: Pick<DOMRect, 'top' | 'right' | 'height'>,
  cardWidth: number = PROFILE_CARD_WIDTH,
  cardHeight: number = PROFILE_CARD_HEIGHT,
): { left: number, top: number } {
  const viewportWidth = window.innerWidth || document.documentElement.clientWidth || (PROFILE_CARD_WIDTH + PROFILE_VIEWPORT_PADDING * 2)
  const viewportHeight = window.innerHeight || document.documentElement.clientHeight || (PROFILE_CARD_HEIGHT + PROFILE_VIEWPORT_PADDING * 2)
  const desiredLeft = anchorRect.right + PROFILE_CARD_GAP
  const maxLeft = Math.max(PROFILE_VIEWPORT_PADDING, viewportWidth - cardWidth - PROFILE_VIEWPORT_PADDING)
  const left = Math.min(Math.max(PROFILE_VIEWPORT_PADDING, desiredLeft), maxLeft)
  const desiredTop = anchorRect.top + (anchorRect.height / 2) - (cardHeight / 2)
  const maxTop = Math.max(PROFILE_VIEWPORT_PADDING, viewportHeight - cardHeight - PROFILE_VIEWPORT_PADDING)
  const top = Math.min(Math.max(PROFILE_VIEWPORT_PADDING, desiredTop), maxTop)

  return { left, top }
}

function openAgentProfile(agentId: string | null | undefined, event: MouseEvent): void {
  if (!agentId) {
    return
  }

  const anchor = event.currentTarget
  if (!(anchor instanceof HTMLElement)) {
    return
  }

  const anchorRect = anchor.getBoundingClientRect()
  const nextPosition = profilePopoverPosition(anchorRect)

  if (
    agentProfilePopover.value?.agentId === agentId
    && agentProfilePopover.value.left === nextPosition.left
    && agentProfilePopover.value.top === nextPosition.top
  ) {
    closeAgentProfilePopover()
    return
  }

  agentProfilePopover.value = {
    agentId,
    ...nextPosition,
  }

  void nextTick(() => {
    const popover = document.querySelector<HTMLElement>('[data-testid="agent-profile-popover"]')
    if (!popover || agentProfilePopover.value?.agentId !== agentId) {
      return
    }

    const measuredPosition = profilePopoverPosition(
      anchorRect,
      popover.offsetWidth || PROFILE_CARD_WIDTH,
      popover.offsetHeight || PROFILE_CARD_HEIGHT,
    )
    agentProfilePopover.value = {
      agentId,
      ...measuredPosition,
    }
  })
}

function openMessageContextMenu(message: ChatMessage, event: MouseEvent): void {
  if (!canOpenMessageContextMenu(message)) {
    return
  }

  event.preventDefault()
  contextMenu.value = {
    messageId: message.id,
    left: event.clientX + CONTEXT_MENU_OFFSET,
    top: event.clientY + CONTEXT_MENU_OFFSET,
  }
}

function isReasoningExpanded(messageId: string): boolean {
  return !collapsedReasoningMessageIds.value.has(messageId)
}

function toggleReasoning(messageId: string): void {
  const next = new Set(collapsedReasoningMessageIds.value)

  if (next.has(messageId)) {
    next.delete(messageId)
  } else {
    next.add(messageId)
  }

  collapsedReasoningMessageIds.value = next
}

const contextMenuMessage = computed<ChatMessage | null>(() => {
  if (!contextMenu.value) {
    return null
  }

  return displayedMessages.value.find((message) => message.id === contextMenu.value?.messageId) ?? null
})

const activeAgentProfile = computed<AgentPresentation | null>(() => (
  agentProfilePopover.value ? agentPresentation(agentProfilePopover.value.agentId) : null
))

async function triggerContextMenuCopy(): Promise<void> {
  const message = contextMenuMessage.value
  const text = message ? messageTextContent(message) : ''
  if (!text) {
    return
  }

  const copied = await copyText(text)
  if (copied) {
    closeMessageContextMenu()
  }
}

function fallbackCopyText(text: string): boolean {
  if (typeof document === 'undefined' || !document.body) {
    return false
  }

  const textarea = document.createElement('textarea')
  const activeElement = document.activeElement instanceof HTMLElement ? document.activeElement : null
  textarea.value = text
  textarea.setAttribute('readonly', '')
  textarea.style.position = 'fixed'
  textarea.style.top = '0'
  textarea.style.left = '0'
  textarea.style.opacity = '0'
  textarea.style.pointerEvents = 'none'
  document.body.appendChild(textarea)
  textarea.focus()
  textarea.select()
  textarea.setSelectionRange(0, textarea.value.length)

  try {
    return typeof document.execCommand === 'function' && document.execCommand('copy')
  } finally {
    document.body.removeChild(textarea)
    activeElement?.focus()
  }
}

async function copyText(text: string): Promise<boolean> {
  if (typeof navigator !== 'undefined' && navigator.clipboard) {
    try {
      await navigator.clipboard.writeText(text)
      return true
    } catch {
      return fallbackCopyText(text)
    }
  }

  return fallbackCopyText(text)
}
</script>

<template>
  <div
    ref="listRef"
    data-testid="message-list-scroller"
    class="flex-1 overflow-y-auto bg-[radial-gradient(circle_at_top,_rgba(0,150,195,0.08),_transparent_38%),linear-gradient(180deg,rgba(248,250,252,0.92),rgba(255,255,255,0.98))] p-4 pb-[var(--composer-overlay-offset)] dark:bg-[radial-gradient(circle_at_top,_rgba(0,150,195,0.12),_transparent_34%),linear-gradient(180deg,rgba(24,24,27,0.92),rgba(9,9,11,0.98))]"
    @scroll.passive="handleScroll"
  >
    <div v-if="!messages.length" class="flex h-full items-center justify-center">
      <div class="max-w-sm text-center space-y-3">
        <div class="inline-flex h-14 w-14 items-center justify-center rounded-3xl bg-white/80 text-slate-400 shadow-sm ring-1 ring-slate-200/70 dark:bg-white/5 dark:text-slate-500 dark:ring-white/8">
          <svg class="h-6 w-6 text-gray-400 dark:text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
          </svg>
        </div>
        <p class="text-sm text-slate-500 italic dark:text-slate-400">{{ isDraft ? '从这里开始新的分析会话。' : '该会话暂无消息。' }}</p>
        <p v-if="isDraft" class="text-xs text-slate-400 dark:text-slate-500">写下你的第一条提示词，系统会在发送时创建会话并开始执行。</p>
      </div>
    </div>
    
    <template v-for="message in displayedMessages" :key="message.id">
      <div class="flex w-full" :class="[messageSpacingClass(message), messageContainerClass(message)]">
        <div
          v-if="isSystemNoticeMessage(message)"
          :data-testid="`system-notice-${message.id}`"
          class="message-system-notice"
        >
          <div class="message-markdown message-system-notice__content" v-html="renderText(messageTextContent(message))"></div>
        </div>

        <div
          v-else-if="message.role === 'user'"
          class="space-y-1.5"
          :data-testid="standaloneQuestionMessage(message, showThinking ?? false) ? `standalone-question-message-${message.id}` : undefined"
          :class="standaloneActiveQuestionMessage(message, showThinking ?? false) ? 'w-full max-w-[88%]' : 'max-w-[88%]'"
        >
          <div
            v-if="hasBubbleContent(message, showThinking ?? false) || shouldShowStreamingPlaceholder(message, messages, sessionStatus, showThinking ?? false)"
            :data-testid="`message-bubble-${message.id}`"
            class="message-bubble message-bubble--user rounded-xl bg-bjut-blue px-3 py-2 text-sm text-white shadow-sm dark:shadow-none"
            @contextmenu="openMessageContextMenu(message, $event)"
          >
            <p v-if="shouldShowStreamingPlaceholder(message, messages, sessionStatus, showThinking ?? false)" class="text-sm italic text-slate-500 dark:text-slate-400">正在思考...</p>
            <div
              v-if="visibleReasoningParts(message, showThinking ?? false).length"
              class="mb-2.5"
            >
              <button
                type="button"
                :data-testid="`message-reasoning-toggle-${message.id}`"
                class="inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-slate-400 transition hover:text-slate-500 dark:text-slate-500 dark:hover:text-slate-400"
                :aria-expanded="isReasoningExpanded(message.id) ? 'true' : 'false'"
                @click="toggleReasoning(message.id)"
              >
                <span>思考过程</span>
                <ChevronDownIcon
                  :data-testid="`message-reasoning-toggle-icon-${message.id}`"
                  class="h-3 w-3 transition-transform duration-150"
                  :class="isReasoningExpanded(message.id) ? 'rotate-0' : '-rotate-90'"
                />
              </button>
              <div v-if="isReasoningExpanded(message.id)" class="mt-1.5 space-y-1.5">
                <div
                  v-for="(part, index) in visibleReasoningParts(message, showThinking ?? false)"
                  :key="`${message.id}-reasoning-${index}`"
                  :data-testid="index === 0 ? `message-reasoning-text-${message.id}` : undefined"
                  class="message-markdown message-reasoning"
                  v-html="renderText(part.text)"
                ></div>
              </div>
            </div>
            <template v-for="(part, index) in message.parts" :key="`${message.id}-${index}`">
              <div v-if="part.type === 'text'" class="message-markdown leading-6" v-html="renderText(part.text)"></div>
              <div v-else-if="part.type === 'todo'" class="space-y-1.5">
                <p class="text-xs font-semibold uppercase tracking-[0.08em] text-bjut-blue dark:text-cyan-400">任务更新</p>
                <ul class="space-y-1.5">
                  <li v-for="entry in todoEntries(message, index)" :key="entry.id" class="rounded-xl bg-slate-50 px-3 py-2 text-sm text-slate-700 ring-1 ring-slate-200/70 dark:bg-white/[0.04] dark:text-slate-200 dark:ring-white/8">
                    <div class="flex items-center justify-between gap-3">
                      <span>{{ entry.label }}</span>
                      <span class="shrink-0 text-[11px] font-medium text-slate-500 dark:text-slate-400">{{ statusLabel(entry.status) }}</span>
                    </div>
                  </li>
                </ul>
              </div>
              <div v-else-if="part.type === 'verification'" class="space-y-1.5">
                <p class="text-xs font-semibold uppercase tracking-[0.08em] text-bjut-blue dark:text-cyan-400">验证</p>
                <ul class="space-y-1.5">
                  <li v-for="entry in verificationEntries(message, index)" :key="entry.id" class="rounded-xl bg-slate-50 px-3 py-2 text-sm text-slate-700 ring-1 ring-slate-200/70 dark:bg-white/[0.04] dark:text-slate-200 dark:ring-white/8">
                    <div class="flex items-center justify-between gap-3">
                      <span class="font-medium">{{ entry.title }}</span>
                      <span class="shrink-0 text-[11px] font-medium text-slate-500 dark:text-slate-400">{{ statusLabel(entry.status) }}</span>
                    </div>
                    <p class="mt-1 text-[12px] text-slate-500 dark:text-slate-400">{{ entry.detail }}</p>
                  </li>
                </ul>
              </div>
              <ArtifactInlineBlock
                v-else-if="part.type === 'artifact'"
                :artifact="artifactState(message, index)"
                :session-id="activeSessionId ?? null"
                :actions-disabled="artifactActionsDisabled ?? false"
                @open-artifact="emit('open-artifact', $event)"
              />
              <div
                v-else-if="part.type === 'skill_use'"
                :data-testid="`skill-use-${message.id}-${index}`"
                class="inline-flex max-w-full items-center gap-2 rounded-lg border border-slate-200/70 bg-slate-50/80 px-2.5 py-1.5 text-xs text-slate-600 dark:border-white/8 dark:bg-white/[0.04] dark:text-slate-300"
              >
                <span class="h-1.5 w-1.5 shrink-0 rounded-full bg-cyan-400"></span>
                <span class="shrink-0 text-slate-400 dark:text-slate-500">技能</span>
                <span class="truncate font-medium text-slate-700 dark:text-slate-200">{{ skillUseLabel(message, index) }}</span>
              </div>
              <div
                v-else-if="part.type === 'issue'"
                :data-testid="`inline-issue-${message.id}`"
                class="flex min-w-0 w-full items-center justify-center gap-1.5 overflow-hidden whitespace-nowrap text-center text-[12px] leading-5"
                :class="issueInlineClass(issueState(message, index).severity)"
                :title="issueTooltip(issueState(message, index), part.text)"
              >
                <span class="shrink-0 font-semibold">{{ issueSeverityLabel(issueState(message, index).severity) }}</span>
                <span class="shrink-0 opacity-50">·</span>
                <span class="min-w-0 truncate opacity-85">{{ issueDisplayDetail(issueState(message, index), part.text) }}</span>
              </div>
              <div v-else-if="part.type === 'question'" class="w-full space-y-1.5">
                <div
                  v-if="isActiveQuestionPart(message, index)"
                  class="w-full rounded-[1.15rem] border border-slate-200/70 bg-white/92 px-4 py-3 text-sm text-slate-800 ring-1 ring-slate-200/60 dark:border-white/10 dark:bg-zinc-900/82 dark:text-slate-100 dark:ring-white/8"
                >
                  <div class="flex items-center justify-between gap-3">
                    <span class="text-[12px] font-semibold text-slate-500 dark:text-slate-400">{{ activeInlineQuestionProgress() }}</span>
                    <div class="flex flex-wrap justify-end gap-1.5">
                      <button
                        v-for="(question, questionIndex) in activeInlineQuestionItems()"
                        :key="`${message.id}-active-question-tab-${questionIndex}`"
                        :data-testid="`structured-question-tab-${questionIndex}`"
                        type="button"
                        class="inline-flex h-7 items-center rounded-full px-2.5 text-[11px] font-medium transition"
                        :class="questionIndex === inlineQuestionIndex
                          ? 'bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900'
                          : activeInlineQuestionAnswered(questionIndex)
                            ? 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200/80 dark:bg-emerald-500/10 dark:text-emerald-200 dark:ring-emerald-400/20'
                            : 'bg-white text-slate-500 ring-1 ring-slate-200/80 hover:text-slate-700 dark:bg-white/5 dark:text-slate-400 dark:ring-white/10 dark:hover:text-slate-200'"
                        @click="activateInlineQuestion(questionIndex)"
                      >
                        {{ question.header || `问题 ${questionIndex + 1}` }}
                      </button>
                    </div>
                  </div>

                  <div v-if="activeInlineQuestion()" class="mt-3 space-y-2.5">
                    <p class="text-[15px] font-semibold leading-6 text-slate-900 dark:text-slate-100">{{ activeInlineQuestion()?.question }}</p>

                    <div class="space-y-2">
                      <button
                        v-for="(option, optionIndex) in activeInlineQuestion()?.options ?? []"
                        :key="`${message.id}-active-question-option-${inlineQuestionIndex}-${optionIndex}`"
                        :data-testid="`structured-question-option-${inlineQuestionIndex}-${optionIndex}`"
                        type="button"
                        class="flex w-full items-start gap-3 rounded-[0.95rem] border px-3 py-2.5 text-left transition"
                        :class="activeInlineQuestionOptionSelected(option.label)
                          ? 'border-bjut-blue/35 bg-bjut-blue/8 text-bjut-blue dark:border-cyan-300/35 dark:bg-cyan-400/10 dark:text-cyan-100'
                          : 'border-slate-200/80 bg-white/90 text-slate-800 hover:border-slate-300 dark:border-white/10 dark:bg-transparent dark:text-slate-100 dark:hover:border-white/20'"
                        @click="selectInlineQuestionOption(option.label)"
                      >
                        <span
                          class="mt-0.5 inline-flex h-4 w-4 shrink-0 rounded-full border transition"
                          :class="activeInlineQuestionOptionSelected(option.label)
                            ? 'border-current bg-current/20'
                            : 'border-slate-300 dark:border-slate-600'"
                        ></span>
                        <span class="min-w-0">
                          <span class="block text-sm font-semibold">{{ option.label }}</span>
                          <span v-if="option.description" class="mt-0.5 block text-[12px] leading-5 text-slate-500 dark:text-slate-400">{{ option.description }}</span>
                        </span>
                      </button>

                      <label class="flex items-start gap-3 rounded-[0.95rem] border border-slate-200/80 bg-white/90 px-3 py-2.5 transition focus-within:border-bjut-blue/35 dark:border-white/10 dark:bg-transparent dark:focus-within:border-cyan-300/35">
                        <span
                          class="mt-0.5 inline-flex h-4 w-4 shrink-0 rounded-full border transition"
                          :class="activeInlineQuestionAnswer(inlineQuestionIndex).trim().length && !(activeInlineQuestion()?.options ?? []).some((option) => option.label === activeInlineQuestionAnswer(inlineQuestionIndex))
                            ? 'border-bjut-blue bg-bjut-blue/20 dark:border-cyan-300 dark:bg-cyan-400/20'
                            : 'border-slate-300 dark:border-slate-600'"
                        ></span>
                        <input
                          :data-testid="`structured-question-input-${inlineQuestionIndex}`"
                          ref="inlineQuestionInputRef"
                          :value="activeInlineQuestionAnswer(inlineQuestionIndex)"
                          type="text"
                          class="min-w-0 flex-1 border-0 bg-transparent p-0 text-sm text-slate-900 outline-none placeholder:text-slate-400 focus:ring-0 dark:text-slate-100 dark:placeholder:text-slate-500"
                          placeholder="输入你的回答..."
                          @input="updateInlineQuestionAnswer(($event.target as HTMLInputElement).value)"
                          @keydown="handleInlineQuestionInputKeydown"
                          @compositionstart="inlineQuestionComposing = true"
                          @compositionend="inlineQuestionComposing = false"
                        />
                      </label>
                    </div>
                  </div>
                </div>

                <template v-else>
                  <div class="inline-flex max-w-full flex-col overflow-hidden rounded-2xl bg-white/90 text-slate-900 ring-1 ring-slate-200/70 shadow-sm dark:bg-zinc-900/80 dark:text-slate-100 dark:ring-white/8 dark:shadow-none">
                    <div
                      :data-testid="`answered-question-header-${message.id}`"
                      class="flex items-center gap-2 border-b border-slate-200/70 bg-slate-50/85 px-3 py-2 dark:border-white/8 dark:bg-white/[0.04]"
                    >
                      <QuestionCircleIcon class="h-4 w-4 shrink-0 text-bjut-blue dark:text-cyan-300" />
                      <span class="truncate font-mono text-sm text-gray-700 dark:text-slate-300">提问</span>
                    </div>
                    <div class="px-3 py-3 text-sm text-slate-700 dark:text-slate-200">
                      <div v-if="questionItems(message, index).length" class="space-y-2.5">
                        <section
                          v-for="(question, questionIndex) in questionItems(message, index)"
                          :key="`${message.id}-question-${questionIndex}`"
                          class="rounded-[0.95rem] border border-slate-200/70 bg-slate-50/85 px-3 py-2.5 dark:border-white/8 dark:bg-white/[0.04]"
                        >
                          <p class="text-sm font-medium text-slate-800 dark:text-slate-100">{{ question.question }}</p>
                          <div
                            v-if="questionAnswerEntryAt(message, index, messages, questionIndex)"
                            class="mt-2"
                          >
                            <span class="text-[13px] font-medium text-emerald-700 dark:text-emerald-200">
                              {{ questionAnswerEntryAt(message, index, messages, questionIndex)?.value }}
                            </span>
                          </div>
                        </section>
                      </div>
                      <p
                        v-else-if="questionAnswerEntries(message, index, messages).length"
                        class="text-[13px] font-medium text-emerald-700 dark:text-emerald-200"
                      >
                        {{ questionAnswerEntries(message, index, messages)[0]?.value }}
                      </p>
                    </div>
                  </div>
                </template>
              </div>
            </template>
          </div>
        </div>

        <div
          v-else
          :class="assistantRowClass(message, showThinking ?? false)"
          :data-testid="inlineIssueNoticeMessage(message, showThinking ?? false) ? `inline-issue-row-${message.id}` : undefined"
        >
          <div v-if="!inlineIssueNoticeMessage(message, showThinking ?? false)" class="w-10 shrink-0">
            <button
              v-if="shouldShowMessageHeader(message)"
              :data-testid="`message-agent-avatar-button-${message.id}`"
              type="button"
              class="block rounded-2xl transition hover:-translate-y-0.5 hover:shadow-md hover:shadow-slate-900/10 focus:outline-none focus-visible:ring-2 focus-visible:ring-bjut-blue/35 dark:hover:shadow-black/20 dark:focus-visible:ring-cyan-300/35"
              @click="openAgentProfile(messageAgentId(message), $event)"
            >
              <img
                :data-testid="`message-agent-avatar-${message.id}`"
                :src="messageAgentAvatar(message)"
                :alt="`${messageAgentTitle(message)} 头像`"
                class="h-10 w-10 shrink-0 rounded-2xl object-cover ring-1 ring-slate-200/80 dark:ring-white/10"
              />
            </button>
          </div>
          <div
            class="min-w-0 flex-1 space-y-1.5"
            :data-testid="standaloneQuestionMessage(message, showThinking ?? false) ? `standalone-question-message-${message.id}` : undefined"
            :class="assistantContentClass(message, showThinking ?? false)"
          >
            <div
              v-if="shouldShowMessageHeader(message)"
              class="flex flex-wrap items-center gap-x-2 gap-y-0.5 px-0.5 text-slate-500 dark:text-slate-400"
            >
              <span :data-testid="`message-agent-label-${message.id}`" class="truncate text-[13px] font-semibold tracking-[0.04em] text-slate-700 dark:text-slate-200">{{ messageAgentTitle(message) }}</span>
            </div>

            <div
              v-if="hasBubbleContent(message, showThinking ?? false) || shouldShowStreamingPlaceholder(message, messages, sessionStatus, showThinking ?? false)"
              :data-testid="`message-bubble-${message.id}`"
              class="message-bubble text-sm dark:shadow-none"
              :class="assistantBubbleClass(message, showThinking ?? false)"
              @contextmenu="openMessageContextMenu(message, $event)"
            >
              <p v-if="shouldShowStreamingPlaceholder(message, messages, sessionStatus, showThinking ?? false)" class="text-sm italic text-slate-500 dark:text-slate-400">正在思考...</p>
              <div
                v-if="visibleReasoningParts(message, showThinking ?? false).length"
                class="mb-2.5"
              >
                <button
                  type="button"
                  :data-testid="`message-reasoning-toggle-${message.id}`"
                  class="inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-slate-400 transition hover:text-slate-500 dark:text-slate-500 dark:hover:text-slate-400"
                  :aria-expanded="isReasoningExpanded(message.id) ? 'true' : 'false'"
                  @click="toggleReasoning(message.id)"
                >
                  <span>思考过程</span>
                  <ChevronDownIcon
                    :data-testid="`message-reasoning-toggle-icon-${message.id}`"
                    class="h-3 w-3 transition-transform duration-150"
                    :class="isReasoningExpanded(message.id) ? 'rotate-0' : '-rotate-90'"
                  />
                </button>
                <div v-if="isReasoningExpanded(message.id)" class="mt-1.5 space-y-1.5">
                  <div
                    v-for="(part, index) in visibleReasoningParts(message, showThinking ?? false)"
                    :key="`${message.id}-reasoning-${index}`"
                    :data-testid="index === 0 ? `message-reasoning-text-${message.id}` : undefined"
                    class="message-markdown message-reasoning"
                    v-html="renderText(part.text)"
                  ></div>
                </div>
              </div>
              <template v-for="(part, index) in message.parts" :key="`${message.id}-${index}`">
                <div v-if="part.type === 'text'" class="message-markdown leading-6" v-html="renderText(part.text)"></div>
                <div
                  v-else-if="part.type === 'subtask'"
                  :data-testid="`subtask-notice-${message.id}`"
                  class="leading-6"
                >
                  <button
                    type="button"
                    :data-testid="`subtask-mention-${message.id}`"
                    class="inline border-0 bg-transparent p-0 align-baseline font-semibold text-bjut-blue transition hover:text-sky-700 focus:outline-none focus-visible:rounded-sm focus-visible:ring-2 focus-visible:ring-bjut-blue/30 dark:text-cyan-200 dark:hover:text-cyan-100 dark:focus-visible:ring-cyan-300/35"
                    @click="openAgentProfile(subtaskState(message, index).child_agent, $event)"
                  >
                    @{{ subtaskChildLabel(message, index) }}
                  </button>
                  <div
                    v-if="subtaskPromptText(message, index)"
                    class="message-markdown message-subtask-prompt ml-1 inline align-baseline"
                    v-html="renderText(subtaskPromptText(message, index))"
                  ></div>
                </div>
                <div v-else-if="part.type === 'todo'" class="space-y-1.5">
                  <p class="text-xs font-semibold uppercase tracking-[0.08em] text-bjut-blue dark:text-cyan-400">任务更新</p>
                  <ul class="space-y-1.5">
                    <li v-for="entry in todoEntries(message, index)" :key="entry.id" class="rounded-xl bg-slate-50 px-3 py-2 text-sm text-slate-700 ring-1 ring-slate-200/70 dark:bg-white/[0.04] dark:text-slate-200 dark:ring-white/8">
                      <div class="flex items-center justify-between gap-3">
                        <span>{{ entry.label }}</span>
                        <span class="shrink-0 text-[11px] font-medium text-slate-500 dark:text-slate-400">{{ statusLabel(entry.status) }}</span>
                      </div>
                    </li>
                  </ul>
                </div>
                <div v-else-if="part.type === 'verification'" class="space-y-1.5">
                  <p class="text-xs font-semibold uppercase tracking-[0.08em] text-bjut-blue dark:text-cyan-400">验证</p>
                  <ul class="space-y-1.5">
                    <li v-for="entry in verificationEntries(message, index)" :key="entry.id" class="rounded-xl bg-slate-50 px-3 py-2 text-sm text-slate-700 ring-1 ring-slate-200/70 dark:bg-white/[0.04] dark:text-slate-200 dark:ring-white/8">
                      <div class="flex items-center justify-between gap-3">
                        <span class="font-medium">{{ entry.title }}</span>
                        <span class="shrink-0 text-[11px] font-medium text-slate-500 dark:text-slate-400">{{ statusLabel(entry.status) }}</span>
                      </div>
                      <p class="mt-1 text-[12px] text-slate-500 dark:text-slate-400">{{ entry.detail }}</p>
                    </li>
                  </ul>
                </div>
                <ArtifactInlineBlock
                  v-else-if="part.type === 'artifact'"
                  :artifact="artifactState(message, index)"
                  :session-id="activeSessionId ?? null"
                  :actions-disabled="artifactActionsDisabled ?? false"
                  @open-artifact="emit('open-artifact', $event)"
                />
                <div
                  v-else-if="part.type === 'skill_use'"
                  :data-testid="`skill-use-${message.id}-${index}`"
                  class="inline-flex max-w-full items-center gap-2 rounded-lg border border-slate-200/70 bg-slate-50/80 px-2.5 py-1.5 text-xs text-slate-600 dark:border-white/8 dark:bg-white/[0.04] dark:text-slate-300"
                >
                  <span class="h-1.5 w-1.5 shrink-0 rounded-full bg-cyan-400"></span>
                  <span class="shrink-0 text-slate-400 dark:text-slate-500">技能</span>
                  <span class="truncate font-medium text-slate-700 dark:text-slate-200">{{ skillUseLabel(message, index) }}</span>
                </div>
                <div
                  v-else-if="part.type === 'issue'"
                  :data-testid="`inline-issue-${message.id}`"
                  class="flex min-w-0 w-full items-center justify-center gap-1.5 overflow-hidden whitespace-nowrap text-center text-[12px] leading-5"
                  :class="issueInlineClass(issueState(message, index).severity)"
                  :title="issueTooltip(issueState(message, index), part.text)"
                >
                <span class="shrink-0 font-semibold">{{ issueSeverityLabel(issueState(message, index).severity) }}</span>
                <span class="shrink-0 opacity-50">·</span>
                <span class="min-w-0 truncate opacity-85">{{ issueDisplayDetail(issueState(message, index), part.text) }}</span>
              </div>
                <div v-else-if="part.type === 'question'" class="w-full space-y-1.5">
                  <div
                    v-if="isActiveQuestionPart(message, index)"
                    class="w-full rounded-[1.15rem] border border-slate-200/70 bg-white/92 px-4 py-3 text-sm text-slate-800 ring-1 ring-slate-200/60 dark:border-white/10 dark:bg-zinc-900/82 dark:text-slate-100 dark:ring-white/8"
                  >
                    <div class="flex items-center justify-between gap-3">
                      <span class="text-[12px] font-semibold text-slate-500 dark:text-slate-400">{{ activeInlineQuestionProgress() }}</span>
                      <div class="flex flex-wrap justify-end gap-1.5">
                        <button
                          v-for="(question, questionIndex) in activeInlineQuestionItems()"
                          :key="`${message.id}-active-question-tab-${questionIndex}`"
                          :data-testid="`structured-question-tab-${questionIndex}`"
                          type="button"
                          class="inline-flex h-7 items-center rounded-full px-2.5 text-[11px] font-medium transition"
                          :class="questionIndex === inlineQuestionIndex
                            ? 'bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900'
                            : activeInlineQuestionAnswered(questionIndex)
                              ? 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200/80 dark:bg-emerald-500/10 dark:text-emerald-200 dark:ring-emerald-400/20'
                              : 'bg-white text-slate-500 ring-1 ring-slate-200/80 hover:text-slate-700 dark:bg-white/5 dark:text-slate-400 dark:ring-white/10 dark:hover:text-slate-200'"
                          @click="activateInlineQuestion(questionIndex)"
                        >
                          {{ question.header || `问题 ${questionIndex + 1}` }}
                        </button>
                      </div>
                    </div>

                    <div v-if="activeInlineQuestion()" class="mt-3 space-y-2.5">
                      <p class="text-[15px] font-semibold leading-6 text-slate-900 dark:text-slate-100">{{ activeInlineQuestion()?.question }}</p>

                      <div class="space-y-2">
                        <button
                          v-for="(option, optionIndex) in activeInlineQuestion()?.options ?? []"
                          :key="`${message.id}-active-question-option-${inlineQuestionIndex}-${optionIndex}`"
                          :data-testid="`structured-question-option-${inlineQuestionIndex}-${optionIndex}`"
                          type="button"
                          class="flex w-full items-start gap-3 rounded-[0.95rem] border px-3 py-2.5 text-left transition"
                          :class="activeInlineQuestionOptionSelected(option.label)
                            ? 'border-bjut-blue/35 bg-bjut-blue/8 text-bjut-blue dark:border-cyan-300/35 dark:bg-cyan-400/10 dark:text-cyan-100'
                            : 'border-slate-200/80 bg-white/90 text-slate-800 hover:border-slate-300 dark:border-white/10 dark:bg-transparent dark:text-slate-100 dark:hover:border-white/20'"
                          @click="selectInlineQuestionOption(option.label)"
                        >
                          <span
                            class="mt-0.5 inline-flex h-4 w-4 shrink-0 rounded-full border transition"
                            :class="activeInlineQuestionOptionSelected(option.label)
                              ? 'border-current bg-current/20'
                              : 'border-slate-300 dark:border-slate-600'"
                          ></span>
                          <span class="min-w-0">
                            <span class="block text-sm font-semibold">{{ option.label }}</span>
                            <span v-if="option.description" class="mt-0.5 block text-[12px] leading-5 text-slate-500 dark:text-slate-400">{{ option.description }}</span>
                          </span>
                        </button>

                        <label class="flex items-start gap-3 rounded-[0.95rem] border border-slate-200/80 bg-white/90 px-3 py-2.5 transition focus-within:border-bjut-blue/35 dark:border-white/10 dark:bg-transparent dark:focus-within:border-cyan-300/35">
                          <span
                            class="mt-0.5 inline-flex h-4 w-4 shrink-0 rounded-full border transition"
                            :class="activeInlineQuestionAnswer(inlineQuestionIndex).trim().length && !(activeInlineQuestion()?.options ?? []).some((option) => option.label === activeInlineQuestionAnswer(inlineQuestionIndex))
                              ? 'border-bjut-blue bg-bjut-blue/20 dark:border-cyan-300 dark:bg-cyan-400/20'
                              : 'border-slate-300 dark:border-slate-600'"
                          ></span>
                          <input
                            :data-testid="`structured-question-input-${inlineQuestionIndex}`"
                            ref="inlineQuestionInputRef"
                            :value="activeInlineQuestionAnswer(inlineQuestionIndex)"
                            type="text"
                            class="min-w-0 flex-1 border-0 bg-transparent p-0 text-sm text-slate-900 outline-none placeholder:text-slate-400 focus:ring-0 dark:text-slate-100 dark:placeholder:text-slate-500"
                            placeholder="输入你的回答..."
                            @input="updateInlineQuestionAnswer(($event.target as HTMLInputElement).value)"
                            @keydown="handleInlineQuestionInputKeydown"
                            @compositionstart="inlineQuestionComposing = true"
                            @compositionend="inlineQuestionComposing = false"
                          />
                        </label>
                      </div>
                    </div>
                  </div>

                  <template v-else>
                    <div class="inline-flex max-w-full flex-col overflow-hidden rounded-2xl bg-white/90 text-slate-900 ring-1 ring-slate-200/70 shadow-sm dark:bg-zinc-900/80 dark:text-slate-100 dark:ring-white/8 dark:shadow-none">
                      <div
                        :data-testid="`answered-question-header-${message.id}`"
                        class="flex items-center gap-2 border-b border-slate-200/70 bg-slate-50/85 px-3 py-2 dark:border-white/8 dark:bg-white/[0.04]"
                      >
                        <QuestionCircleIcon class="h-4 w-4 shrink-0 text-bjut-blue dark:text-cyan-300" />
                        <span class="truncate font-mono text-sm text-gray-700 dark:text-slate-300">提问</span>
                      </div>
                      <div class="px-3 py-3 text-sm text-slate-700 dark:text-slate-200">
                        <div v-if="questionItems(message, index).length" class="space-y-2.5">
                          <section
                            v-for="(question, questionIndex) in questionItems(message, index)"
                            :key="`${message.id}-question-${questionIndex}`"
                            class="rounded-[0.95rem] border border-slate-200/70 bg-slate-50/85 px-3 py-2.5 dark:border-white/8 dark:bg-white/[0.04]"
                          >
                            <p class="text-sm font-medium text-slate-800 dark:text-slate-100">{{ question.question }}</p>
                            <div
                              v-if="questionAnswerEntryAt(message, index, messages, questionIndex)"
                              class="mt-2"
                            >
                              <span class="text-[13px] font-medium text-emerald-700 dark:text-emerald-200">
                                {{ questionAnswerEntryAt(message, index, messages, questionIndex)?.value }}
                              </span>
                            </div>
                          </section>
                        </div>
                        <p
                          v-else-if="questionAnswerEntries(message, index, messages).length"
                          class="text-[13px] font-medium text-emerald-700 dark:text-emerald-200"
                        >
                          {{ questionAnswerEntries(message, index, messages)[0]?.value }}
                        </p>
                      </div>
                    </div>
                  </template>
                </div>
              </template>
            </div>

            <template v-for="(part, index) in visibleToolParts(message)" :key="`${message.id}-tool-${index}`">
              <ToolCallBlock v-if="part.type === 'tool'" :part="part" />
            </template>
          </div>
        </div>
      </div>
    </template>

    <FinalArtifactCarousel
      :artifacts="finalArtifacts ?? []"
      :actions-disabled="artifactActionsDisabled ?? false"
      @open-artifact="emit('open-artifact', $event)"
      @preview-artifact="emit('preview-artifact', $event)"
    />

    <div
      v-if="contextMenu && contextMenuMessage"
      data-testid="message-context-menu"
      class="fixed z-[80] min-w-40 overflow-hidden rounded-2xl border border-slate-200/80 bg-white/96 p-1.5 shadow-xl shadow-slate-900/10 backdrop-blur dark:border-white/10 dark:bg-zinc-950/96 dark:shadow-black/30"
      :style="{ left: `${contextMenu.left}px`, top: `${contextMenu.top}px` }"
      @click.stop
    >
      <button
        :data-testid="`message-context-menu-copy-${contextMenuMessage.id}`"
        type="button"
        class="flex w-full items-center rounded-xl px-3 py-2 text-left text-sm text-slate-700 transition hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-white/8"
        @click="triggerContextMenuCopy"
      >
        复制文本
      </button>
    </div>

    <div
      v-if="agentProfilePopover && activeAgentProfile"
      data-testid="agent-profile-popover"
      class="fixed z-[80] w-[19rem] overflow-hidden rounded-[1.6rem] border border-slate-200/80 bg-white/96 shadow-2xl shadow-slate-900/12 backdrop-blur dark:border-white/10 dark:bg-zinc-950/96 dark:shadow-black/30"
      :style="{ left: `${agentProfilePopover.left}px`, top: `${agentProfilePopover.top}px` }"
      @click.stop
    >
      <div class="h-20 bg-[radial-gradient(circle_at_top_left,_rgba(14,165,233,0.24),_transparent_55%),linear-gradient(135deg,rgba(186,230,253,0.72),rgba(255,255,255,0.92))] dark:bg-[radial-gradient(circle_at_top_left,_rgba(34,211,238,0.18),_transparent_55%),linear-gradient(135deg,rgba(14,116,144,0.45),rgba(9,9,11,0.96))]"></div>
      <div class="relative px-5 pb-5">
        <div class="-mt-8 flex items-start justify-between gap-4">
          <img
            data-testid="agent-profile-popover-avatar"
            :src="activeAgentProfile.avatar"
            :alt="`${activeAgentProfile.label} 头像`"
            class="h-[4.5rem] w-[4.5rem] rounded-[1.45rem] object-cover ring-4 ring-white dark:ring-zinc-950"
          />
          <button
            type="button"
            class="inline-flex h-8 w-8 items-center justify-center rounded-full text-slate-400 transition hover:bg-slate-100 hover:text-slate-600 dark:text-slate-500 dark:hover:bg-white/8 dark:hover:text-slate-300"
            @click="closeAgentProfilePopover"
          >
            ×
          </button>
        </div>

        <div class="mt-3">
          <h3 data-testid="agent-profile-popover-label" class="text-[18px] font-semibold tracking-[0.02em] text-slate-900 dark:text-slate-100">{{ activeAgentProfile.label }}</h3>
        </div>

        <p class="mt-3 text-[13px] leading-6 text-slate-600 dark:text-slate-300">{{ activeAgentProfile.summary }}</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.message-bubble--assistant {
  --markdown-body: rgb(15 23 42);
  --markdown-heading: rgb(2 8 23);
  --markdown-muted: rgb(71 85 105);
  --markdown-link: rgb(3 105 161);
  --markdown-link-underline: rgba(3, 105, 161, 0.22);
  --markdown-strong: rgb(15 23 42);
  --markdown-inline-code-bg: rgba(14, 165, 233, 0.1);
  --markdown-inline-code-border: rgba(14, 165, 233, 0.2);
  --markdown-pre-bg: rgba(15, 23, 42, 0.96);
  --markdown-pre-border: rgba(30, 41, 59, 0.95);
  --markdown-pre-text: rgb(226 232 240);
  --markdown-blockquote-bg: rgba(14, 165, 233, 0.08);
  --markdown-blockquote-border: rgba(14, 165, 233, 0.45);
  --markdown-rule: rgba(148, 163, 184, 0.38);
  --markdown-table-border: rgba(148, 163, 184, 0.3);
  --markdown-table-header-bg: rgba(241, 245, 249, 0.92);
  --markdown-table-row-bg: rgba(248, 250, 252, 0.7);
  --markdown-image-border: rgba(148, 163, 184, 0.26);
}

.message-bubble--user {
  --markdown-body: rgba(255, 255, 255, 0.96);
  --markdown-heading: rgb(255 255 255);
  --markdown-muted: rgba(255, 255, 255, 0.8);
  --markdown-link: rgb(255 255 255);
  --markdown-link-underline: rgba(255, 255, 255, 0.3);
  --markdown-strong: rgb(255 255 255);
  --markdown-inline-code-bg: rgba(255, 255, 255, 0.14);
  --markdown-inline-code-border: rgba(255, 255, 255, 0.18);
  --markdown-pre-bg: rgba(7, 28, 51, 0.42);
  --markdown-pre-border: rgba(255, 255, 255, 0.14);
  --markdown-pre-text: rgb(248 250 252);
  --markdown-blockquote-bg: rgba(255, 255, 255, 0.1);
  --markdown-blockquote-border: rgba(255, 255, 255, 0.28);
  --markdown-rule: rgba(255, 255, 255, 0.18);
  --markdown-table-border: rgba(255, 255, 255, 0.16);
  --markdown-table-header-bg: rgba(255, 255, 255, 0.12);
  --markdown-table-row-bg: rgba(255, 255, 255, 0.04);
  --markdown-image-border: rgba(255, 255, 255, 0.18);
}

.message-system-notice__content {
  --markdown-body: rgb(100 116 139);
  --markdown-heading: rgb(100 116 139);
  --markdown-muted: rgb(100 116 139);
  --markdown-link: rgb(71 85 105);
  --markdown-link-underline: rgba(100, 116, 139, 0.18);
  --markdown-strong: rgb(71 85 105);
  display: inline-flex;
  max-width: min(100%, 32rem);
  justify-content: center;
  border-radius: 9999px;
  background: rgba(241, 245, 249, 0.94);
  padding: 0.4rem 0.85rem;
  font-size: 0.74rem;
  line-height: 1.45;
  text-align: center;
}

@media (prefers-color-scheme: dark) {
  .message-bubble--assistant {
    --markdown-body: rgb(226 232 240);
    --markdown-heading: rgb(248 250 252);
    --markdown-muted: rgb(148 163 184);
    --markdown-link: rgb(125 211 252);
    --markdown-link-underline: rgba(125, 211, 252, 0.24);
    --markdown-strong: rgb(248 250 252);
    --markdown-inline-code-bg: rgba(56, 189, 248, 0.14);
    --markdown-inline-code-border: rgba(103, 232, 249, 0.16);
    --markdown-pre-bg: rgba(2, 6, 23, 0.92);
    --markdown-pre-border: rgba(51, 65, 85, 0.88);
    --markdown-pre-text: rgb(226 232 240);
    --markdown-blockquote-bg: rgba(34, 211, 238, 0.08);
    --markdown-blockquote-border: rgba(103, 232, 249, 0.34);
    --markdown-rule: rgba(100, 116, 139, 0.42);
    --markdown-table-border: rgba(71, 85, 105, 0.48);
    --markdown-table-header-bg: rgba(15, 23, 42, 0.84);
    --markdown-table-row-bg: rgba(15, 23, 42, 0.34);
    --markdown-image-border: rgba(71, 85, 105, 0.44);
  }

  .message-system-notice__content {
    --markdown-body: rgb(148 163 184);
    --markdown-heading: rgb(148 163 184);
    --markdown-muted: rgb(148 163 184);
    --markdown-link: rgb(203 213 225);
    --markdown-link-underline: rgba(148, 163, 184, 0.18);
    --markdown-strong: rgb(226 232 240);
    background: rgba(30, 41, 59, 0.68);
  }
}

.message-markdown {
  color: var(--markdown-body);
  font-size: 0.875rem;
  line-height: 1.6;
  overflow-wrap: anywhere;
}

.message-markdown :deep(.message-markdown__heading),
.message-markdown :deep(.message-markdown__paragraph),
.message-markdown :deep(.message-markdown__list),
.message-markdown :deep(.message-markdown__blockquote),
.message-markdown :deep(.message-markdown__pre),
.message-markdown :deep(.message-markdown__table),
.message-markdown :deep(.message-markdown__image),
.message-markdown :deep(.message-markdown__rule) {
  margin: 0.65rem 0 0;
}

.message-markdown :deep(.message-markdown__heading:first-child),
.message-markdown :deep(.message-markdown__paragraph:first-child),
.message-markdown :deep(.message-markdown__list:first-child),
.message-markdown :deep(.message-markdown__blockquote:first-child),
.message-markdown :deep(.message-markdown__pre:first-child),
.message-markdown :deep(.message-markdown__table:first-child),
.message-markdown :deep(.message-markdown__image:first-child),
.message-markdown :deep(.message-markdown__rule:first-child) {
  margin-top: 0;
}

.message-markdown :deep(.message-markdown__heading) {
  color: var(--markdown-heading);
  font-weight: 700;
  line-height: 1.28;
  letter-spacing: 0;
}

.message-markdown :deep(.message-markdown__heading--h1) {
  font-size: 1rem;
}

.message-markdown :deep(.message-markdown__heading--h2) {
  font-size: 0.96rem;
}

.message-markdown :deep(.message-markdown__heading--h3),
.message-markdown :deep(.message-markdown__heading--h4),
.message-markdown :deep(.message-markdown__heading--h5),
.message-markdown :deep(.message-markdown__heading--h6) {
  font-size: 0.9rem;
}

.message-markdown :deep(.message-markdown__paragraph) {
  color: var(--markdown-body);
}

.message-markdown :deep(.message-markdown__strong) {
  color: var(--markdown-strong);
  font-weight: 700;
}

.message-markdown :deep(.message-markdown__emphasis) {
  color: inherit;
}

.message-markdown :deep(.message-markdown__delete) {
  color: var(--markdown-muted);
  text-decoration-color: var(--markdown-rule);
}

.message-markdown :deep(.message-markdown__link) {
  color: var(--markdown-link);
  font-weight: 600;
  text-decoration: none;
  border-bottom: 1px solid var(--markdown-link-underline);
  transition: border-color 160ms ease, color 160ms ease;
}

.message-markdown :deep(.message-markdown__link:hover) {
  border-bottom-color: currentColor;
}

.message-markdown :deep(.message-markdown__list) {
  padding-left: 1.1rem;
  list-style-position: outside;
  color: var(--markdown-body);
}

.message-markdown :deep(.message-markdown__list--ordered) {
  padding-left: 1.25rem;
  list-style-type: decimal;
}

.message-markdown :deep(.message-markdown__list--bullet) {
  list-style-type: disc;
}

.message-markdown :deep(.message-markdown__list-item) {
  margin: 0.18rem 0;
  padding-left: 0.12rem;
}

.message-markdown :deep(.message-markdown__list-item::marker) {
  color: var(--markdown-muted);
}

.message-markdown :deep(.message-markdown__list-item > .message-markdown__paragraph) {
  margin: 0.16rem 0 0;
}

.message-markdown :deep(.message-markdown__list-item > .message-markdown__paragraph:first-child) {
  margin-top: 0;
}

.message-markdown :deep(.message-markdown__blockquote) {
  padding: 0.55rem 0.7rem;
  border-left: 3px solid var(--markdown-blockquote-border);
  border-radius: 0 0.75rem 0.75rem 0;
  background: var(--markdown-blockquote-bg);
  color: var(--markdown-muted);
}

.message-markdown :deep(.message-markdown__blockquote > .message-markdown__paragraph) {
  margin: 0.35rem 0 0;
}

.message-markdown :deep(.message-markdown__blockquote > .message-markdown__paragraph:first-child) {
  margin-top: 0;
}

.message-markdown :deep(.message-markdown__rule) {
  height: 1px;
  border: 0;
  background: linear-gradient(90deg, transparent, var(--markdown-rule), transparent);
}

.message-markdown :deep(.message-markdown__code) {
  font-family: ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
}

.message-markdown :deep(.message-markdown__code--inline) {
  border: 1px solid var(--markdown-inline-code-border);
  border-radius: 0.5rem;
  background: var(--markdown-inline-code-bg);
  padding: 0.15rem 0.42rem;
  font-size: 0.84em;
}

.message-markdown :deep(.message-markdown__pre) {
  overflow-x: auto;
  border: 1px solid var(--markdown-pre-border);
  border-radius: 0.75rem;
  background: var(--markdown-pre-bg);
  padding: 0.65rem 0.75rem;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
}

.message-markdown :deep(.message-markdown__pre .message-markdown__code--block) {
  display: block;
  min-width: max-content;
  background: transparent;
  color: var(--markdown-pre-text);
  font-size: 0.78rem;
  line-height: 1.55;
}

.message-markdown :deep(.message-markdown__table) {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  overflow: hidden;
  border: 1px solid var(--markdown-table-border);
  border-radius: 0.75rem;
  background: rgba(255, 255, 255, 0.02);
}

.message-markdown :deep(.message-markdown__table-head-cell),
.message-markdown :deep(.message-markdown__table-cell) {
  padding: 0.5rem 0.6rem;
  text-align: left;
  vertical-align: top;
}

.message-markdown :deep(.message-markdown__table-head-cell) {
  background: var(--markdown-table-header-bg);
  color: var(--markdown-heading);
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.message-markdown :deep(.message-markdown__table-cell) {
  border-top: 1px solid var(--markdown-table-border);
  color: var(--markdown-body);
}

.message-markdown :deep(.message-markdown__table-row:nth-child(even) .message-markdown__table-cell) {
  background: var(--markdown-table-row-bg);
}

.message-markdown :deep(.message-markdown__image) {
  display: block;
  max-width: 100%;
  border: 1px solid var(--markdown-image-border);
  border-radius: 0.75rem;
  background: rgba(255, 255, 255, 0.04);
  box-shadow: 0 14px 28px rgba(15, 23, 42, 0.08);
}

.message-subtask-prompt {
  display: inline;
}

.message-subtask-prompt :deep(.message-markdown__paragraph:first-child) {
  display: inline;
}

.message-markdown.message-reasoning {
  --markdown-body: rgb(148 163 184);
  --markdown-heading: rgb(100 116 139);
  --markdown-muted: rgb(148 163 184);
  --markdown-link: rgb(100 116 139);
  --markdown-link-underline: rgba(148, 163, 184, 0.22);
  --markdown-strong: rgb(100 116 139);
  --markdown-inline-code-bg: rgba(148, 163, 184, 0.08);
  --markdown-inline-code-border: rgba(148, 163, 184, 0.18);
  --markdown-pre-bg: rgba(241, 245, 249, 0.72);
  --markdown-pre-border: rgba(203, 213, 225, 0.68);
  --markdown-pre-text: rgb(100 116 139);
  --markdown-blockquote-bg: rgba(148, 163, 184, 0.08);
  --markdown-blockquote-border: rgba(148, 163, 184, 0.28);
  --markdown-rule: rgba(148, 163, 184, 0.24);
  --markdown-table-border: rgba(203, 213, 225, 0.48);
  --markdown-table-header-bg: rgba(248, 250, 252, 0.92);
  --markdown-table-row-bg: rgba(248, 250, 252, 0.58);
  --markdown-image-border: rgba(203, 213, 225, 0.4);
  color: var(--markdown-body);
  font-size: 11px;
  line-height: 1.5;
}

.message-markdown.message-reasoning :deep(.message-markdown__heading),
.message-markdown.message-reasoning :deep(.message-markdown__paragraph),
.message-markdown.message-reasoning :deep(.message-markdown__list),
.message-markdown.message-reasoning :deep(.message-markdown__blockquote),
.message-markdown.message-reasoning :deep(.message-markdown__pre),
.message-markdown.message-reasoning :deep(.message-markdown__table),
.message-markdown.message-reasoning :deep(.message-markdown__image),
.message-markdown.message-reasoning :deep(.message-markdown__rule) {
  margin: 0.45rem 0 0;
}

.message-markdown.message-reasoning :deep(.message-markdown__heading:first-child),
.message-markdown.message-reasoning :deep(.message-markdown__paragraph:first-child),
.message-markdown.message-reasoning :deep(.message-markdown__list:first-child),
.message-markdown.message-reasoning :deep(.message-markdown__blockquote:first-child),
.message-markdown.message-reasoning :deep(.message-markdown__pre:first-child),
.message-markdown.message-reasoning :deep(.message-markdown__table:first-child),
.message-markdown.message-reasoning :deep(.message-markdown__image:first-child),
.message-markdown.message-reasoning :deep(.message-markdown__rule:first-child) {
  margin-top: 0;
}

.message-markdown.message-reasoning :deep(.message-markdown__heading) {
  color: var(--markdown-heading);
  line-height: 1.35;
}

.message-markdown.message-reasoning :deep(.message-markdown__heading--h1) {
  font-size: 1em;
}

.message-markdown.message-reasoning :deep(.message-markdown__heading--h2) {
  font-size: 0.98em;
}

.message-markdown.message-reasoning :deep(.message-markdown__heading--h3),
.message-markdown.message-reasoning :deep(.message-markdown__heading--h4),
.message-markdown.message-reasoning :deep(.message-markdown__heading--h5),
.message-markdown.message-reasoning :deep(.message-markdown__heading--h6) {
  font-size: 0.95em;
}

.message-markdown.message-reasoning :deep(.message-markdown__paragraph) {
  color: var(--markdown-body);
  font-size: 1em;
}

.message-markdown.message-reasoning :deep(.message-markdown__strong) {
  color: var(--markdown-strong);
}

.message-markdown.message-reasoning :deep(.message-markdown__link) {
  color: var(--markdown-link);
}

.message-markdown.message-reasoning :deep(.message-markdown__list) {
  padding-left: 1.05rem;
}

.message-markdown.message-reasoning :deep(.message-markdown__list-item) {
  margin: 0.16rem 0;
}

.message-markdown.message-reasoning :deep(.message-markdown__blockquote) {
  padding: 0.45rem 0.7rem;
  border-left-width: 2px;
  border-radius: 0 0.75rem 0.75rem 0;
}

.message-markdown.message-reasoning :deep(.message-markdown__code--inline) {
  font-size: 0.95em;
}

.message-markdown.message-reasoning :deep(.message-markdown__pre) {
  border-radius: 0.75rem;
  padding: 0.6rem 0.7rem;
}

.message-markdown.message-reasoning :deep(.message-markdown__pre .message-markdown__code--block) {
  font-size: 0.92em;
  line-height: 1.5;
}

.message-markdown.message-reasoning :deep(.message-markdown__table-head-cell),
.message-markdown.message-reasoning :deep(.message-markdown__table-cell) {
  padding: 0.45rem 0.55rem;
}

@media (prefers-color-scheme: dark) {
  .message-markdown.message-reasoning {
    --markdown-body: rgb(148 163 184);
    --markdown-heading: rgb(203 213 225);
    --markdown-muted: rgb(100 116 139);
    --markdown-link: rgb(148 163 184);
    --markdown-link-underline: rgba(148, 163, 184, 0.2);
    --markdown-strong: rgb(203 213 225);
    --markdown-inline-code-bg: rgba(148, 163, 184, 0.12);
    --markdown-inline-code-border: rgba(148, 163, 184, 0.16);
    --markdown-pre-bg: rgba(15, 23, 42, 0.5);
    --markdown-pre-border: rgba(71, 85, 105, 0.44);
    --markdown-pre-text: rgb(148 163 184);
    --markdown-blockquote-bg: rgba(100, 116, 139, 0.12);
    --markdown-blockquote-border: rgba(148, 163, 184, 0.22);
    --markdown-rule: rgba(100, 116, 139, 0.28);
    --markdown-table-border: rgba(71, 85, 105, 0.42);
    --markdown-table-header-bg: rgba(15, 23, 42, 0.82);
    --markdown-table-row-bg: rgba(15, 23, 42, 0.28);
    --markdown-image-border: rgba(71, 85, 105, 0.4);
  }
}
</style>
