<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { answerQuestion, createSession, deleteSession, exportSessionArchive, getHealth, getSession, importSessionArchive, interruptSession, listSessions, openArtifact, openDataDirectory, renameSession, submitMessage, updateAttachedDataDirectories } from './api'
import { loadAppSettings, saveAppSettings } from './app-settings'
import type { Artifact, ChatMessage, DataDirectoryAttachment, EventEnvelope, GeospatialTask, HealthPayload, PlanEntry, PlanGroup, Question, QuestionReplyPayload, Session, SessionIssue, SessionSummary, TimelineEntry, VerificationEntry } from './types'
import AppLayout from './components/layout/AppLayout.vue'
import SessionSidebar from './components/sidebar-left/SessionSidebar.vue'
import ChatWorkspace from './components/chat/ChatWorkspace.vue'
import ArtifactPreviewDialog from './components/chat/ArtifactPreviewDialog.vue'
import StatusPanel from './components/sidebar-right/StatusPanel.vue'
import ConfirmDialog from './components/shared/ConfirmDialog.vue'
import TextInputDialog from './components/shared/TextInputDialog.vue'
import SessionActionMenu from './components/shared/SessionActionMenu.vue'
import Trash3Icon from 'bootstrap-icons/icons/trash3.svg'

const health = ref<HealthPayload | null>(null)
const sessions = ref<SessionSummary[]>([])
const activeSession = ref<Session | null>(null)
const error = ref('')
const draftActive = ref(false)
const defaultDraftDataDirectories = ref<DataDirectoryAttachment[]>([])
const draftAttachedDataDirectories = ref<DataDirectoryAttachment[]>([])
const appSettings = ref(loadAppSettings())
const mobileSessionsOpen = ref(false)
const mobileInspectorOpen = ref(false)
const provisioningLogRef = ref<HTMLElement | null>(null)
const pendingDeleteSessionId = ref<string | null>(null)
const pendingRenameSessionId = ref<string | null>(null)
const sessionBatchMode = ref(false)
const selectedSessionIds = ref<string[]>([])
const pendingBatchDeleteSessions = ref(false)
const interruptPending = ref(false)
const previewArtifact = ref<Artifact | null>(null)
let healthRefreshTimer: number | null = null

let eventSource: EventSource | null = null
let pendingUserMessageCount = 0

const planEntries = computed<PlanEntry[]>(() => activeSession.value?.plan ?? [])
const planGroups = computed<PlanGroup[]>(() => activeSession.value?.plan_groups ?? [])
const messages = computed<ChatMessage[]>(() => activeSession.value?.messages ?? [])
const activeQuestion = computed<Question | null>(() => activeSession.value?.question ?? null)
const activeSessionReadOnly = computed<boolean>(() => activeSession.value?.read_only ?? false)
const artifactEntries = computed<Artifact[]>(() => activeSession.value?.artifacts ?? [])
const finalArtifactEntries = computed<Artifact[]>(() => artifactEntries.value.filter((artifact) => artifact.artifact_stage !== 'intermediate'))
const geospatialEnvironment = computed(() => health.value?.geospatial_environment ?? null)
const geospatialProvisioningBlocked = computed<boolean>(() => {
  const status = geospatialEnvironment.value?.status
  return status === 'provisioning' || status === 'not_ready' || status === 'failed'
})
const geospatialProvisioningLogs = computed<string[]>(() => geospatialEnvironment.value?.logs ?? [])
const geospatialProvisioningLogSignature = computed<string>(() => geospatialProvisioningLogs.value.join('\n'))
const geospatialProvisioningProgress = computed<number>(() => {
  const progress = geospatialEnvironment.value?.progress
  if (typeof progress !== 'number' || !Number.isFinite(progress)) {
    return geospatialEnvironment.value?.status === 'ready' ? 100 : 0
  }
  return Math.max(0, Math.min(100, Math.round(progress * 100)))
})
const geospatialProvisioningProgressLabel = computed<string>(() => {
  const status = geospatialEnvironment.value?.status
  if (status === 'ready') {
    return '完成'
  }
  if (status === 'failed') {
    return '失败'
  }
  return `约 ${geospatialProvisioningProgress.value}%`
})
const attachedDataDirectories = computed<DataDirectoryAttachment[]>(() => activeSession.value?.attached_data_directories ?? draftAttachedDataDirectories.value)
const timelineEntries = computed<TimelineEntry[]>(() => activeSession.value?.timeline ?? [])
const selectedSessions = computed<SessionSummary[]>(() => sessions.value.filter((session) => selectedSessionIds.value.includes(session.id)))
const allSessionsSelected = computed<boolean>(() => (
  sessions.value.length > 0 && sessions.value.every((session) => selectedSessionIds.value.includes(session.id))
))
const recentUserMessages = computed<string[]>(() => {
  const history: string[] = []
  const seen = new Set<string>()
  for (const message of activeSession.value?.messages ?? []) {
    if (message.role !== 'user' || messageExcludedFromPromptHistory(message)) {
      continue
    }
    const text = message.parts
      .filter((part) => part.type === 'text')
      .map((part) => part.text ?? '')
      .join('\n\n')
      .trim()
    if (!text || seen.has(text)) {
      continue
    }
    seen.add(text)
    history.push(text)
  }
  return history
})

watch(geospatialProvisioningLogSignature, () => {
  if (geospatialProvisioningBlocked.value) {
    scrollProvisioningLogsToBottom()
  }
}, { flush: 'post' })

onMounted(async () => {
  await refreshHealth()
  await refreshSessions()
  if (!activeSession.value) {
    draftActive.value = true
    draftAttachedDataDirectories.value = [...defaultDraftDataDirectories.value]
  }
  document.addEventListener('keydown', handleGlobalKeydown)
})

onBeforeUnmount(() => {
  eventSource?.close()
  if (healthRefreshTimer !== null) {
    window.clearInterval(healthRefreshTimer)
  }
  document.removeEventListener('keydown', handleGlobalKeydown)
})

function handleGlobalKeydown(event: KeyboardEvent): void {
  if (event.key !== 'Escape') {
    return
  }
  if (pendingRenameSessionId.value) {
    event.preventDefault()
    cancelRenameSession()
    return
  }
  if (pendingDeleteSessionId.value) {
    event.preventDefault()
    cancelDeleteSession()
    return
  }
  if (pendingBatchDeleteSessions.value) {
    event.preventDefault()
    cancelBatchDeleteSessions()
    return
  }
  if (sessionBatchMode.value) {
    event.preventDefault()
    cancelSessionBatchMode()
  }
}

function updateShowThinking(value: boolean): void {
  appSettings.value = {
    ...appSettings.value,
    showThinking: value,
  }
  saveAppSettings(appSettings.value)
}

async function refreshHealth(): Promise<void> {
  health.value = await getHealth()
  defaultDraftDataDirectories.value = health.value.default_data_directories ?? []
  updateHealthPolling()
}

function updateHealthPolling(): void {
  if (geospatialEnvironment.value?.status === 'provisioning' && healthRefreshTimer === null) {
    healthRefreshTimer = window.setInterval(() => {
      void refreshHealth()
    }, 1000)
    return
  }
  if (geospatialEnvironment.value?.status !== 'provisioning' && healthRefreshTimer !== null) {
    window.clearInterval(healthRefreshTimer)
    healthRefreshTimer = null
  }
}

function scrollProvisioningLogsToBottom(): void {
  void nextTick(() => {
    const element = provisioningLogRef.value
    if (element) {
      element.scrollTop = Math.max(element.scrollHeight - element.clientHeight, 0)
    }
  })
}

function isProvisioningErrorLog(line: string): boolean {
  return line.startsWith('ERROR:')
}

async function refreshSessions(): Promise<void> {
  sessions.value = (await listSessions()).map((session) => ({
    ...session,
    read_only: session.read_only ?? false,
    archive_metadata: session.archive_metadata ?? {},
  }))
}

async function startSession(): Promise<void> {
  error.value = ''
  interruptPending.value = false
  cancelSessionBatchMode()
  draftActive.value = true
  draftAttachedDataDirectories.value = [...defaultDraftDataDirectories.value]
  activeSession.value = null
  mobileSessionsOpen.value = false
  mobileInspectorOpen.value = false
  eventSource?.close()
  eventSource = null
}

async function resumeSession(sessionId: string): Promise<void> {
  error.value = ''
  interruptPending.value = false
  cancelSessionBatchMode()
  draftActive.value = false
  mobileSessionsOpen.value = false
  mobileInspectorOpen.value = false
  eventSource?.close()
  eventSource = null
  activeSession.value = normalizeSessionForDisplay(await getSession(sessionId))
  if (!activeSession.value.read_only) {
    subscribeToSession(sessionId)
  }
}

async function handleSendMessage(text: string): Promise<void> {
  let createdFromDraft = false

  if (!activeSession.value && draftActive.value) {
    activeSession.value = await createSession()
    if (!sameAttachedDirectories(activeSession.value.attached_data_directories, draftAttachedDataDirectories.value)) {
      activeSession.value = await updateAttachedDataDirectories(activeSession.value.id, draftAttachedDataDirectories.value)
    }
    draftAttachedDataDirectories.value = []
    draftActive.value = false
    createdFromDraft = true
    await refreshSessions()
    subscribeToSession(activeSession.value.id)
  }

  if (!activeSession.value || geospatialProvisioningBlocked.value || activeSessionReadOnly.value) return

  insertOptimisticUserMessage(text)
  await submitMessage(activeSession.value.id, text)

  if (createdFromDraft) {
    activeSession.value = mergeSessionMessages(normalizeSessionForDisplay(await getSession(activeSession.value.id)))
    sessions.value = sessions.value.map((session) => (
      session.id === activeSession.value?.id
        ? {
            ...session,
            title: activeSession.value.title,
            status: activeSession.value.status,
          }
        : session
    ))
  }
}

async function handleInterruptTask(): Promise<void> {
  if (!activeSession.value || activeSessionReadOnly.value || activeSession.value.status !== 'running' || interruptPending.value) {
    return
  }

  interruptPending.value = true
  try {
    await interruptSession(activeSession.value.id)
  } catch (cause) {
    interruptPending.value = false
    error.value = cause instanceof Error ? cause.message : '中断任务失败。'
  } finally {
    if (activeSession.value?.status !== 'running') {
      interruptPending.value = false
    }
  }
}

function normalizeSessionForDisplay(session: Session): Session {
  const messages = [...session.messages]
  const hasPart = (type: string): boolean => messages.some((message) => message.parts.some((part) => part.type === type))

  if (session.question && !hasPart('question')) {
    messages.push({
      id: `restored-question-${session.question.id}`,
      role: 'system',
      agent: 'geo',
      created_at: new Date().toISOString(),
      parts: [{ type: 'question', text: session.question.prompt, state: { ...session.question } }],
    })
  }

  if (session.verification.length && !hasPart('verification')) {
    messages.push({
      id: `restored-verification-${session.id}`,
      role: 'system',
      agent: 'skeptical-review',
      created_at: new Date().toISOString(),
      parts: [{ type: 'verification', state: { entries: session.verification } }],
    })
  }

  for (const issue of session.issues ?? []) {
    if (!hasIssueMessage(messages, issue.id)) {
      messages.push(createIssueMessage(issue))
    }
  }

  return {
    ...session,
    read_only: session.read_only ?? false,
    archive_metadata: session.archive_metadata ?? {},
    artifacts: deduplicateArtifactsByPath(session.artifacts),
    plan_groups: session.plan_groups ?? [],
    issues: session.issues ?? [],
    messages,
  }
}

function hasQuestionMessage(questionId: string): boolean {
  return activeSession.value?.messages.some((message) => message.parts.some((part) => (
    part.type === 'question'
    && part.state
    && typeof part.state === 'object'
    && part.state.id === questionId
  ))) ?? false
}

function injectQuestionMessage(question: Question): void {
  if (!activeSession.value || hasQuestionMessage(question.id)) {
    return
  }
  upsertMessage({
    id: `restored-question-${question.id}`,
    role: 'system',
    agent: 'geo',
    created_at: new Date().toISOString(),
    parts: [{ type: 'question', text: question.prompt, state: { ...question } }],
  })
}

function hasIssueMessage(messages: ChatMessage[], issueId: string): boolean {
  return messages.some((message) => message.id === `inline-issue-${issueId}` || message.parts.some((part) => (
    part.type === 'issue'
    && part.state
    && typeof part.state === 'object'
    && part.state.id === issueId
  )))
}

function createIssueMessage(issue: SessionIssue): ChatMessage {
  return {
    id: `inline-issue-${issue.id}`,
    role: 'system',
    agent: null,
    created_at: issue.created_at,
    parts: [{ type: 'issue', text: issue.title, state: { ...issue } }],
  }
}

function createFrontendConnectionIssue(sessionId: string): SessionIssue {
  return {
    id: `frontend-connection-lost-${sessionId}`,
    type: 'frontend_connection_lost',
    severity: 'warning',
    source: 'frontend',
    title: '实时更新已断开',
    detail: '浏览器与当前会话的实时更新连接已断开，后台任务可能仍在继续。重新打开会话或刷新页面后可同步最新记录。',
    created_at: new Date().toISOString(),
    recoverable: true,
  }
}

function questionIdFromMessage(message: ChatMessage): string | null {
  for (const part of message.parts) {
    if (part.type !== 'question' || !part.state || typeof part.state !== 'object' || typeof part.state.id !== 'string') {
      continue
    }
    return part.state.id
  }
  return null
}

function displayQuestionReply(question: Question, answers: string[]): string {
  if (answers.length <= 1 || !(question.questions?.length)) {
    return answers[0] ?? ''
  }
  return answers
    .map((value, index) => `${question.questions?.[index]?.header ?? `问题 ${index + 1}`}：${value}`)
    .join('\n')
}

async function handleReplyQuestion(payload: QuestionReplyPayload): Promise<void> {
  if (!activeSession.value || activeSessionReadOnly.value || !activeQuestion.value) return
  const answers = typeof payload === 'string' ? [payload] : payload.answers
  const displayText = displayQuestionReply(activeQuestion.value, answers)
  insertOptimisticUserMessage(displayText, {
    history_excluded: true,
    question_id: activeQuestion.value.id,
    question_answers: answers,
  })
  await answerQuestion(activeSession.value.id, activeQuestion.value.id, payload)
}

async function handleAttachDirectory(item: { path: string, label?: string | null }): Promise<void> {
  if (activeSessionReadOnly.value) {
    return
  }
  const next = mergeAttachedDirectories(attachedDataDirectories.value, [{
    id: `dir-${Date.now()}`,
    path: item.path,
    enabled: true,
    label: item.label ?? null,
  }])

  if (!activeSession.value) {
    draftAttachedDataDirectories.value = next
    return
  }

  activeSession.value = await updateAttachedDataDirectories(activeSession.value.id, next)
  sessions.value = sessions.value.map((session) => (
    session.id === activeSession.value?.id ? { ...session, attached_data_directories: activeSession.value.attached_data_directories } : session
  ))
}

async function handleRemoveDirectory(directoryId: string): Promise<void> {
  if (activeSessionReadOnly.value) {
    return
  }
  const next = attachedDataDirectories.value.filter((item) => item.id !== directoryId)

  if (!activeSession.value) {
    draftAttachedDataDirectories.value = next
    return
  }

  activeSession.value = await updateAttachedDataDirectories(activeSession.value.id, next)
  sessions.value = sessions.value.map((session) => (
    session.id === activeSession.value?.id ? { ...session, attached_data_directories: activeSession.value.attached_data_directories } : session
  ))
}

async function handleOpenDirectory(item: { path: string }): Promise<void> {
  await openDataDirectory(item.path)
}

async function handleOpenWorkspace(): Promise<void> {
  if (!activeSession.value || activeSessionReadOnly.value) return
  await fetch(`/api/sessions/${activeSession.value.id}/workspace/open`, { method: 'POST' })
}

async function handleOpenArtifact(artifact: Artifact): Promise<void> {
  if (!activeSession.value || activeSessionReadOnly.value) return
  try {
    await openArtifact(activeSession.value.id, artifact.id)
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '打开产物失败。'
  }
}

function handlePreviewArtifact(artifact: Artifact): void {
  if (activeSessionReadOnly.value) {
    return
  }
  previewArtifact.value = artifact
}

function closeArtifactPreview(): void {
  previewArtifact.value = null
}

async function handleImportSessionArchive(file: File): Promise<void> {
  error.value = ''
  try {
    const archive = JSON.parse(await file.text()) as unknown
    const imported = normalizeSessionForDisplay(await importSessionArchive(archive))
    eventSource?.close()
    eventSource = null
    activeSession.value = imported
    draftActive.value = false
    interruptPending.value = false
    mobileSessionsOpen.value = false
    mobileInspectorOpen.value = false
    previewArtifact.value = null
    await refreshSessions()
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '导入会话记录失败。'
  }
}

async function handleExportSessionArchive(sessionId: string): Promise<void> {
  error.value = ''
  try {
    const { blob, filename } = await exportSessionArchive(sessionId)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '导出会话记录失败。'
  }
}

async function saveRenameSession(title: string): Promise<void> {
  const sessionId = pendingRenameSessionId.value
  if (!sessionId || !title.trim()) {
    pendingRenameSessionId.value = null
    return
  }

  const renamed = await renameSession(sessionId, title)
  sessions.value = sessions.value.map((session) => (session.id === sessionId ? renamed : session))
  if (activeSession.value?.id === sessionId) {
    activeSession.value.title = renamed.title
  }
  pendingRenameSessionId.value = null
}

function requestRenameSession(sessionId: string): void {
  if (sessions.value.some((session) => session.id === sessionId && session.read_only)) {
    return
  }
  pendingRenameSessionId.value = sessionId
}

function cancelRenameSession(): void {
  pendingRenameSessionId.value = null
}

function resetActiveSessionToDraft(): void {
  activeSession.value = null
  draftActive.value = true
  draftAttachedDataDirectories.value = [...defaultDraftDataDirectories.value]
  mobileInspectorOpen.value = false
  eventSource?.close()
  eventSource = null
}

async function handleDeleteSession(sessionId: string): Promise<void> {
  await deleteSession(sessionId)
  sessions.value = sessions.value.filter((session) => session.id !== sessionId)
  selectedSessionIds.value = selectedSessionIds.value.filter((id) => id !== sessionId)
  if (activeSession.value?.id === sessionId) {
    resetActiveSessionToDraft()
  }
  pendingDeleteSessionId.value = null
}

function requestDeleteSession(sessionId: string): void {
  pendingDeleteSessionId.value = sessionId
}

function cancelDeleteSession(): void {
  pendingDeleteSessionId.value = null
}

function confirmDeleteSession(): Promise<void> {
  if (!pendingDeleteSession.value) {
    return Promise.resolve()
  }

  return handleDeleteSession(pendingDeleteSession.value.id)
}

function enterSessionBatchMode(): void {
  error.value = ''
  sessionBatchMode.value = true
  selectedSessionIds.value = []
}

function cancelSessionBatchMode(): void {
  sessionBatchMode.value = false
  selectedSessionIds.value = []
  pendingBatchDeleteSessions.value = false
}

function toggleSessionSelection(sessionId: string): void {
  selectedSessionIds.value = selectedSessionIds.value.includes(sessionId)
    ? selectedSessionIds.value.filter((id) => id !== sessionId)
    : [...selectedSessionIds.value, sessionId]
}

function toggleAllSessionSelection(): void {
  selectedSessionIds.value = allSessionsSelected.value ? [] : sessions.value.map((session) => session.id)
}

function requestBatchDeleteSessions(): void {
  if (selectedSessionIds.value.length === 0) {
    return
  }
  pendingBatchDeleteSessions.value = true
}

function cancelBatchDeleteSessions(): void {
  pendingBatchDeleteSessions.value = false
}

async function confirmBatchDeleteSessions(): Promise<void> {
  const sessionIds = [...selectedSessionIds.value]
  if (sessionIds.length === 0) {
    pendingBatchDeleteSessions.value = false
    return
  }

  try {
    for (const sessionId of sessionIds) {
      await deleteSession(sessionId)
    }
  } catch (cause) {
    pendingBatchDeleteSessions.value = false
    error.value = cause instanceof Error ? cause.message : '删除所选会话失败。'
    return
  }

  sessions.value = sessions.value.filter((session) => !sessionIds.includes(session.id))
  if (activeSession.value && sessionIds.includes(activeSession.value.id)) {
    resetActiveSessionToDraft()
  }
  cancelSessionBatchMode()
}

const pendingDeleteSession = computed(() => sessions.value.find((session) => session.id === pendingDeleteSessionId.value) ?? null)
const pendingRenameSession = computed(() => sessions.value.find((session) => session.id === pendingRenameSessionId.value) ?? null)

function subscribeToSession(sessionId: string): void {
  eventSource?.close()
  eventSource = new EventSource(`/api/sessions/${sessionId}/events`)
  const handleEnvelope = (event: MessageEvent<string>) => {
    const envelope = JSON.parse(event.data) as EventEnvelope<unknown>
    if (!activeSession.value) {
      return
    }
    if (envelope.type === 'session.plan') {
      activeSession.value.plan = envelope.payload as PlanEntry[]
    }
    if (envelope.type === 'session.plan_group') {
      upsertPlanGroup(envelope.payload as PlanGroup)
    }
    if (envelope.type === 'session.plan_groups') {
      activeSession.value.plan_groups = envelope.payload as PlanGroup[]
    }
    if (envelope.type === 'session.messages') {
      activeSession.value.messages = reconcileMessages(normalizeSessionForDisplay({
        ...activeSession.value,
        messages: envelope.payload as ChatMessage[],
      }).messages)
    }
    if (envelope.type === 'session.message_delta') {
      upsertMessage(envelope.payload as ChatMessage)
    }
    if (envelope.type === 'session.timeline') {
      activeSession.value.timeline = envelope.payload as TimelineEntry[]
    }
    if (envelope.type === 'session.timeline_entry') {
      upsertTimelineEntry(envelope.payload as TimelineEntry)
    }
    if (envelope.type === 'session.question') {
      const question = envelope.payload as Question | null
      activeSession.value.question = question
      if (question) {
        injectQuestionMessage(question)
      }
    }
    if (envelope.type === 'session.geospatial_task') {
      activeSession.value.geospatial_task = envelope.payload as GeospatialTask
    }
    if (envelope.type === 'session.verification') {
      activeSession.value.verification = envelope.payload as VerificationEntry[]
    }
    if (envelope.type === 'session.artifact') {
      upsertArtifact(envelope.payload as Artifact)
    }
    if (envelope.type === 'session.issue') {
      const issue = envelope.payload as SessionIssue
      upsertIssue(issue)
      upsertMessage(createIssueMessage(issue))
    }
    if (envelope.type === 'session.issues') {
      activeSession.value.issues = envelope.payload as SessionIssue[]
      for (const issue of activeSession.value.issues) {
        upsertMessage(createIssueMessage(issue))
      }
    }
    if (envelope.type === 'session.title') {
      const payload = envelope.payload as { id: string, title: string }
      activeSession.value.title = payload.title
      sessions.value = sessions.value.map((session) => (session.id === payload.id ? { ...session, title: payload.title } : session))
    }
    if (envelope.type === 'session.attached_data_directories') {
      activeSession.value.attached_data_directories = envelope.payload as DataDirectoryAttachment[]
    }
    if (envelope.type === 'session.status') {
      const status = (envelope.payload as { status: Session['status'] }).status
      activeSession.value.status = status
      if (status !== 'running') {
        interruptPending.value = false
      }
      sessions.value = sessions.value.map((session) => (
        session.id === activeSession.value?.id
          ? { ...session, status }
          : session
      ))
    }
  }
  eventSource.onmessage = handleEnvelope
  eventSource.addEventListener('session.status', handleEnvelope)
  eventSource.addEventListener('session.messages', handleEnvelope)
  eventSource.addEventListener('session.message_delta', handleEnvelope)
  eventSource.addEventListener('session.timeline', handleEnvelope)
  eventSource.addEventListener('session.timeline_entry', handleEnvelope)
  eventSource.addEventListener('session.plan', handleEnvelope)
  eventSource.addEventListener('session.plan_group', handleEnvelope)
  eventSource.addEventListener('session.plan_groups', handleEnvelope)
  eventSource.addEventListener('session.question', handleEnvelope)
  eventSource.addEventListener('session.geospatial_task', handleEnvelope)
  eventSource.addEventListener('session.verification', handleEnvelope)
  eventSource.addEventListener('session.artifact', handleEnvelope)
  eventSource.addEventListener('session.issue', handleEnvelope)
  eventSource.addEventListener('session.issues', handleEnvelope)
  eventSource.addEventListener('session.title', handleEnvelope)
  eventSource.addEventListener('session.attached_data_directories', handleEnvelope)
  eventSource.onerror = () => {
    if (!activeSession.value) {
      error.value = '实时更新连接已断开，请刷新后重试。'
      return
    }
    const issue = createFrontendConnectionIssue(activeSession.value.id)
    upsertIssue(issue)
    upsertMessage(createIssueMessage(issue))
  }
}

function upsertMessage(message: ChatMessage): void {
  if (!activeSession.value) return
  const incomingQuestionId = questionIdFromMessage(message)
  if (incomingQuestionId && !message.id.startsWith(`restored-question-${incomingQuestionId}`)) {
    activeSession.value.messages = activeSession.value.messages.filter((entry) => entry.id !== `restored-question-${incomingQuestionId}`)
  }
  const index = activeSession.value.messages.findIndex((entry) => entry.id === message.id)
  if (index >= 0) {
    activeSession.value.messages[index] = message
    removeMatchingPendingUserMessages(message)
    return
  }
  activeSession.value.messages = [...activeSession.value.messages, message]
  removeMatchingPendingUserMessages(message)
}

function upsertPlanGroup(group: PlanGroup): void {
  if (!activeSession.value) return
  const groups = activeSession.value.plan_groups ?? []
  const index = groups.findIndex((entry) => entry.agent === group.agent)
  if (index >= 0) {
    activeSession.value.plan_groups = groups.map((entry, currentIndex) => (currentIndex === index ? group : entry))
    return
  }
  activeSession.value.plan_groups = [...groups, group]
}

function upsertTimelineEntry(entry: TimelineEntry): void {
  if (!activeSession.value) return
  const index = activeSession.value.timeline.findIndex((item) => item.id === entry.id)
  if (index >= 0) {
    activeSession.value.timeline[index] = entry
    return
  }
  activeSession.value.timeline = [...activeSession.value.timeline, entry]
}

function upsertIssue(issue: SessionIssue): void {
  if (!activeSession.value) return
  const issues = activeSession.value.issues ?? []
  const index = issues.findIndex((entry) => entry.id === issue.id)
  if (index >= 0) {
    activeSession.value.issues = issues.map((entry, currentIndex) => (currentIndex === index ? issue : entry))
    return
  }
  activeSession.value.issues = [...issues, issue]
}

function artifactPathKey(path: string): string {
  return path.trim()
}

function deduplicateArtifactsByPath(artifacts: Artifact[]): Artifact[] {
  return artifacts.reduce<Artifact[]>((items, artifact) => (
    items.filter((item) => item.id !== artifact.id && artifactPathKey(item.path) !== artifactPathKey(artifact.path)).concat(artifact)
  ), [])
}

function upsertArtifact(artifact: Artifact): void {
  if (!activeSession.value) return
  activeSession.value.artifacts = deduplicateArtifactsByPath([...activeSession.value.artifacts, artifact])
}

function mergeAttachedDirectories(existing: DataDirectoryAttachment[] | undefined, incoming: DataDirectoryAttachment[] | undefined): DataDirectoryAttachment[] {
  const merged = [...(existing ?? []), ...(incoming ?? [])]
  return merged.reduce<DataDirectoryAttachment[]>((items, entry) => {
    const candidate = { ...entry, path: normalizeDirectoryPath(entry.path) }
    const nextItems: DataDirectoryAttachment[] = []
    let skipCandidate = false
    for (const existingItem of items) {
      const existingPath = normalizeDirectoryPath(existingItem.path)
      if (existingPath === candidate.path || pathContains(existingPath, candidate.path)) {
        nextItems.push(existingItem)
        skipCandidate = true
        continue
      }
      if (pathContains(candidate.path, existingPath)) {
        continue
      }
      nextItems.push(existingItem)
    }
    if (!skipCandidate) {
      nextItems.push(candidate)
    }
    return nextItems
  }, [])
}

function sameAttachedDirectories(left: DataDirectoryAttachment[] | undefined, right: DataDirectoryAttachment[] | undefined): boolean {
  const normalize = (items: DataDirectoryAttachment[] | undefined): string[] => (items ?? [])
    .map((item) => `${normalizeDirectoryPath(item.path)}::${item.label ?? ''}::${item.enabled ? '1' : '0'}`)
    .sort()
  const normalizedLeft = normalize(left)
  const normalizedRight = normalize(right)
  return normalizedLeft.length === normalizedRight.length && normalizedLeft.every((value, index) => value === normalizedRight[index])
}

function normalizeDirectoryPath(path: string): string {
  const normalized = path.replace(/\\/g, '/').replace(/\/+$/g, '')
  return normalized || '/'
}

function pathContains(parent: string, child: string): boolean {
  return child === parent || child.startsWith(`${parent}/`)
}

function createOptimisticUserMessage(text: string, state: Record<string, unknown> | null = null): ChatMessage {
  pendingUserMessageCount += 1
  return {
    id: `pending-user-${pendingUserMessageCount}`,
    role: 'user',
    agent: 'geo',
    created_at: new Date().toISOString(),
    parts: [{ type: 'text', text, state }],
  }
}

function insertOptimisticUserMessage(text: string, state: Record<string, unknown> | null = null): void {
  if (!activeSession.value) {
    return
  }
  activeSession.value.messages = [...activeSession.value.messages, createOptimisticUserMessage(text, state)]
}

function isPendingUserMessage(message: ChatMessage): boolean {
  return message.role === 'user' && message.id.startsWith('pending-user-')
}

function messageText(message: ChatMessage): string {
  return message.parts
    .filter((part) => part.type === 'text')
    .map((part) => part.text ?? '')
    .join('\n\n')
    .trim()
}

function isMatchingUserMessage(authoritative: ChatMessage, pending: ChatMessage): boolean {
  return authoritative.role === 'user' && messageText(authoritative) === messageText(pending)
}

function messageExcludedFromPromptHistory(message: ChatMessage): boolean {
  return message.parts.some((part) => {
    if (part.type !== 'text' || !part.state || typeof part.state !== 'object') {
      return false
    }
    return part.state.history_excluded === true
  })
}

function reconcileMessages(authoritative: ChatMessage[]): ChatMessage[] {
  const pendingMessages = activeSession.value?.messages.filter((message) => isPendingUserMessage(message)) ?? []
  const merged = [...authoritative]
  for (const pendingMessage of pendingMessages) {
    if (!authoritative.some((message) => isMatchingUserMessage(message, pendingMessage))) {
      merged.push(pendingMessage)
    }
  }
  return merged
}

function removeMatchingPendingUserMessages(message: ChatMessage): void {
  if (!activeSession.value || message.role !== 'user' || isPendingUserMessage(message)) {
    return
  }
  activeSession.value.messages = activeSession.value.messages.filter((entry) => !isPendingUserMessage(entry) || !isMatchingUserMessage(message, entry))
}

function mergeSessionMessages(session: Session): Session {
  return {
    ...session,
    messages: reconcileMessages(session.messages),
  }
}

function closeMobilePanels(): void {
  mobileSessionsOpen.value = false
  mobileInspectorOpen.value = false
}
</script>

<template>
  <AppLayout>
    <template #header>
      <header class="flex h-12 items-center justify-between border-b border-slate-200/70 bg-white/80 px-5 backdrop-blur-xl dark:border-white/10 dark:bg-zinc-950/80">
        <div class="flex items-center gap-3">
          <img
            data-testid="app-brand-icon"
            src="/app-icon-rounded.png"
            alt="多智能体协作智能地理空间数据强化分析系统图标"
            class="h-7 w-7 shrink-0 rounded-full object-cover ring-1 ring-slate-200/80 shadow-sm dark:ring-white/10"
          />
          <span class="max-w-[44rem] truncate text-sm font-semibold text-slate-900 dark:text-slate-100">多智能体协作智能地理空间数据强化分析系统</span>
        </div>
        <div class="flex items-center gap-2 text-xs font-medium text-slate-600 dark:text-slate-400">
          <span>{{ health?.runtime.status === 'ready' ? '系统就绪' : '连接中...' }}</span>
          <div 
            class="h-2 w-2 rounded-full"
            :class="health?.runtime.status === 'ready' ? 'bg-emerald-500' : 'bg-amber-400 animate-pulse'"
          ></div>
        </div>
      </header>
    </template>

    <Transition
      enter-active-class="transition duration-200 ease-out"
      enter-from-class="opacity-0"
      enter-to-class="opacity-100"
      leave-active-class="transition duration-150 ease-in"
      leave-from-class="opacity-100"
      leave-to-class="opacity-0"
    >
      <div v-if="mobileSessionsOpen" data-testid="mobile-session-panel" class="fixed inset-0 z-20 bg-slate-950/20 backdrop-blur-sm lg:hidden" @click.self="closeMobilePanels">
        <Transition
          appear
          enter-active-class="transition duration-200 ease-out"
          enter-from-class="-translate-x-full"
          enter-to-class="translate-x-0"
          leave-active-class="transition duration-150 ease-in"
          leave-from-class="translate-x-0"
          leave-to-class="-translate-x-full"
        >
          <SessionSidebar
            class="h-full"
            :sessions="sessions"
            :activeSessionId="activeSession?.id"
            :batchMode="sessionBatchMode"
            :selectedSessionIds="selectedSessionIds"
            @start-session="startSession"
            @resume-session="resumeSession"
            @rename-session="requestRenameSession"
            @export-session="handleExportSessionArchive"
            @request-delete-session="requestDeleteSession"
            @import-session-archive="handleImportSessionArchive"
            @enter-batch-mode="enterSessionBatchMode"
            @cancel-batch-mode="cancelSessionBatchMode"
            @toggle-session-selection="toggleSessionSelection"
            @toggle-all-session-selection="toggleAllSessionSelection"
            @request-delete-selected-sessions="requestBatchDeleteSessions"
          />
        </Transition>
      </div>
    </Transition>

    <SessionSidebar 
      class="hidden lg:flex"
      :sessions="sessions" 
      :activeSessionId="activeSession?.id" 
      :batchMode="sessionBatchMode"
      :selectedSessionIds="selectedSessionIds"
      @start-session="startSession" 
      @resume-session="resumeSession" 
      @rename-session="requestRenameSession"
      @export-session="handleExportSessionArchive"
      @request-delete-session="requestDeleteSession"
      @import-session-archive="handleImportSessionArchive"
      @enter-batch-mode="enterSessionBatchMode"
      @cancel-batch-mode="cancelSessionBatchMode"
      @toggle-session-selection="toggleSessionSelection"
      @toggle-all-session-selection="toggleAllSessionSelection"
      @request-delete-selected-sessions="requestBatchDeleteSessions"
    />

    <section class="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
      <header data-testid="session-header" class="flex h-14 items-center justify-between border-b border-slate-200/60 bg-linear-to-r from-slate-50 via-white to-white px-4 dark:border-white/8 dark:from-zinc-950 dark:via-zinc-950 dark:to-zinc-900/80">
        <div class="flex min-w-0 items-center gap-3">
          <div class="flex items-center gap-2 lg:hidden">
            <button data-testid="mobile-session-toggle" type="button" class="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 dark:border-white/10 dark:bg-white/5 dark:text-slate-200" @click="mobileSessionsOpen = true">会话</button>
            <button data-testid="mobile-inspector-toggle" type="button" class="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 dark:border-white/10 dark:bg-white/5 dark:text-slate-200" @click="mobileInspectorOpen = true">上下文</button>
          </div>
          <div class="flex min-w-0 items-center gap-2">
            <h1 data-testid="active-session-title" class="truncate text-lg font-semibold text-gray-900 dark:text-white">
              {{ activeSession?.title ?? (draftActive ? '新会话' : '请选择一个会话') }}
            </h1>
            <span
              v-if="activeSessionReadOnly"
              data-testid="readonly-session-indicator"
              class="shrink-0 rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-600 dark:bg-white/8 dark:text-slate-300"
            >
              只读归档
            </span>
          </div>
        </div>

        <SessionActionMenu
          v-if="activeSession"
          :session-id="activeSession.id"
          align="right"
          button-label="当前会话操作"
          test-id-prefix="active-session-actions"
          :read-only="activeSessionReadOnly"
          @rename="requestRenameSession"
          @export="handleExportSessionArchive"
          @delete="requestDeleteSession"
        />
      </header>

      <div
        v-if="error"
        data-testid="app-error"
        role="alert"
        class="border-b border-rose-200/70 bg-rose-50 px-4 py-2 text-sm font-medium text-rose-700 dark:border-rose-500/20 dark:bg-rose-500/10 dark:text-rose-200"
      >
        {{ error }}
      </div>

      <div class="flex min-h-0 flex-1 overflow-hidden">
        <div
          v-if="geospatialProvisioningBlocked"
          data-testid="geospatial-provisioning-overlay"
          role="dialog"
          aria-modal="true"
          aria-labelledby="geospatial-provisioning-title"
          class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/35 px-4 py-6 backdrop-blur-md"
        >
          <div
            data-testid="geospatial-provisioning-dialog"
            class="w-[min(40rem,calc(100vw-2rem))] overflow-hidden rounded-lg border border-white/70 bg-white shadow-2xl shadow-slate-950/25 dark:border-white/10 dark:bg-zinc-950 dark:shadow-black/40"
          >
            <div class="border-b border-slate-200/70 px-5 py-4 dark:border-white/10">
              <div class="flex items-center justify-between gap-4">
                <div class="min-w-0">
                  <p id="geospatial-provisioning-title" class="text-sm font-semibold text-slate-950 dark:text-slate-100">地理运行环境准备中</p>
                  <p class="mt-1 text-xs text-slate-500 dark:text-slate-400">首次启动正在安装和校验地理 Python 依赖。</p>
                </div>
                <span class="shrink-0 font-mono text-xs font-semibold text-bjut-blue dark:text-cyan-300">{{ geospatialProvisioningProgressLabel }}</span>
              </div>
            </div>
            <div class="space-y-4 px-5 py-4">
              <div class="h-2 overflow-hidden rounded-full bg-slate-100 dark:bg-white/10">
                <div class="h-full bg-bjut-blue transition-all duration-300 dark:bg-cyan-400" :style="{ width: `${geospatialProvisioningProgress}%` }"></div>
              </div>
              <div
                ref="provisioningLogRef"
                data-testid="geospatial-provisioning-logs"
                class="max-h-64 overflow-y-auto rounded-md bg-slate-950 px-3 py-2 font-mono text-[11px] leading-5 text-slate-100 shadow-inner dark:bg-black"
                aria-live="polite"
              >
                <p v-if="!geospatialProvisioningLogs.length">等待安装日志...</p>
                <p
                  v-for="(line, index) in geospatialProvisioningLogs"
                  :key="index"
                  data-testid="geospatial-provisioning-log-line"
                  :class="isProvisioningErrorLog(line) ? 'text-rose-300' : ''"
                >
                  {{ line }}
                </p>
              </div>
            </div>
          </div>
        </div>

        <ChatWorkspace 
          :activeSessionId="activeSession?.id ?? null"
          :isDraft="draftActive"
          :sessionStatus="activeSession?.status ?? null"
          :inputDisabled="geospatialProvisioningBlocked || activeSessionReadOnly"
          :interrupting="interruptPending"
          :readOnly="activeSessionReadOnly"
          :showThinking="appSettings.showThinking"
          :messages="messages"
          :recentMessages="recentUserMessages"
          :activeQuestion="activeSessionReadOnly ? null : activeQuestion"
          :artifacts="artifactEntries"
          :finalArtifacts="finalArtifactEntries"
          :attachedDataDirectories="attachedDataDirectories"
          :workspacePath="activeSessionReadOnly ? null : activeSession?.workspace_path ?? null"
          @send-message="handleSendMessage"
          @interrupt-task="handleInterruptTask"
          @reply-question="handleReplyQuestion"
          @open-artifact="handleOpenArtifact"
          @preview-artifact="handlePreviewArtifact"
          @attach-directory="handleAttachDirectory"
          @open-directory="handleOpenDirectory"
          @remove-directory="handleRemoveDirectory"
          @open-workspace="handleOpenWorkspace"
        />

        <Transition
          enter-active-class="transition duration-200 ease-out"
          enter-from-class="opacity-0"
          enter-to-class="opacity-100"
          leave-active-class="transition duration-150 ease-in"
          leave-from-class="opacity-100"
          leave-to-class="opacity-0"
        >
          <div v-if="mobileInspectorOpen" data-testid="mobile-inspector-panel" class="fixed inset-0 z-20 bg-slate-950/20 backdrop-blur-sm lg:hidden" @click.self="closeMobilePanels">
            <Transition
              appear
              enter-active-class="transition duration-200 ease-out"
              enter-from-class="translate-x-full"
              enter-to-class="translate-x-0"
              leave-active-class="transition duration-150 ease-in"
              leave-from-class="translate-x-0"
              leave-to-class="translate-x-full"
            >
              <div class="ml-auto h-full w-80 max-w-[90vw]">
                <StatusPanel
                  class="h-full"
                  :planGroups="planGroups"
                  :planEntries="planEntries"
                  :timelineEntries="timelineEntries"
                  :artifacts="finalArtifactEntries"
                  :showThinking="appSettings.showThinking"
                  :artifactActionsDisabled="activeSessionReadOnly"
                  @update:showThinking="updateShowThinking"
                  @open-artifact="handleOpenArtifact"
                  @preview-artifact="handlePreviewArtifact"
                />
              </div>
            </Transition>
          </div>
        </Transition>

        <StatusPanel 
          class="hidden lg:flex"
          :planGroups="planGroups"
          :planEntries="planEntries"
          :timelineEntries="timelineEntries"
          :artifacts="finalArtifactEntries"
          :showThinking="appSettings.showThinking"
          :artifactActionsDisabled="activeSessionReadOnly"
          @update:showThinking="updateShowThinking"
          @open-artifact="handleOpenArtifact"
          @preview-artifact="handlePreviewArtifact"
        />
      </div>
    </section>

    <ArtifactPreviewDialog
      :open="!activeSessionReadOnly && previewArtifact !== null"
      :artifact="previewArtifact"
      :sessionId="activeSession?.id ?? null"
      @close="closeArtifactPreview"
      @open-artifact="handleOpenArtifact"
    />

    <ConfirmDialog
      :open="pendingDeleteSession !== null"
      title="确认删除会话"
      :message="pendingDeleteSession ? `删除后该会话会从列表中移除：${pendingDeleteSession.title}` : ''"
      @cancel="cancelDeleteSession"
      @confirm="confirmDeleteSession"
    >
      <template #icon>
        <Trash3Icon class="h-4 w-4" />
      </template>
    </ConfirmDialog>

    <ConfirmDialog
      :open="pendingBatchDeleteSessions"
      title="确认删除所选会话"
      :message="`即将删除 ${selectedSessions.length} 个会话。删除后会从列表中移除，无法恢复。`"
      confirm-label="删除所选"
      @cancel="cancelBatchDeleteSessions"
      @confirm="confirmBatchDeleteSessions"
    >
      <template #icon>
        <Trash3Icon class="h-4 w-4" />
      </template>
    </ConfirmDialog>

    <TextInputDialog
      :open="pendingRenameSession !== null"
      title="重命名会话"
      :message="pendingRenameSession ? `为会话设置新的名称：${pendingRenameSession.title}` : ''"
      :initial-value="pendingRenameSession?.title ?? ''"
      @cancel="cancelRenameSession"
      @confirm="saveRenameSession"
    />
  </AppLayout>
</template>
