<script setup lang="ts">
import ArrowUpRightCircleFillIcon from 'bootstrap-icons/icons/arrow-up-right-circle-fill.svg'
import PlusLgIcon from 'bootstrap-icons/icons/plus-lg.svg'
import ChevronLeftIcon from 'bootstrap-icons/icons/chevron-left.svg'
import Folder2OpenIcon from 'bootstrap-icons/icons/folder2-open.svg'
import ClockHistoryIcon from 'bootstrap-icons/icons/clock-history.svg'
import BoxArrowUpRightIcon from 'bootstrap-icons/icons/box-arrow-up-right.svg'
import HouseDoorIcon from 'bootstrap-icons/icons/house-door.svg'
import TerminalIcon from 'bootstrap-icons/icons/terminal.svg'
import XLgIcon from 'bootstrap-icons/icons/x-lg.svg'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { browseDataDirectories, listRecentDataDirectories } from '../../api'
import type { DataDirectoryAttachment, DataDirectoryBrowserPayload, Question } from '../../types'

const PROMPT_HISTORY_STORAGE_KEY = 'geo-agent:prompt-history'
const PROMPT_HISTORY_LIMIT = 50

const props = defineProps<{
  disabled: boolean
  isDraft: boolean
  sessionStatus?: 'idle' | 'running' | 'waiting_for_input' | 'completed' | 'failed' | null
  interrupting?: boolean
  readOnly?: boolean
  activeQuestion: Question | null
  attachedDataDirectories: DataDirectoryAttachment[]
  workspacePath: string | null
  recentMessages?: string[]
}>()

const emit = defineEmits<{
  (e: 'send-message', text: string): void
  (e: 'interrupt-task'): void
  (e: 'attach-directory', item: { path: string, label?: string | null }): void
  (e: 'open-directory', item: { path: string }): void
  (e: 'remove-directory', id: string): void
  (e: 'open-workspace'): void
}>()

const message = ref('')
const messageInputRef = ref<HTMLTextAreaElement | null>(null)
const attachmentMenuOpen = ref(false)
const attachmentBrowserOpen = ref(false)
const browserState = ref<DataDirectoryBrowserPayload | null>(null)
const recentDirectories = ref<DataDirectoryAttachment[]>([])
const browserLoading = ref(false)
const browserError = ref('')
const editingPath = ref(false)
const pathDraft = ref('')
const historyIndex = ref<number | null>(null)
const historyDraft = ref('')
const applyingHistoryMessage = ref(false)
const persistedRecentMessages = ref<string[]>(loadPersistedPromptHistory())
const messageComposing = ref(false)
const sessionRunning = computed<boolean>(() => props.sessionStatus === 'running')
const questionPending = computed<boolean>(() => Boolean(props.activeQuestion))
const composerSubmitDisabled = computed<boolean>(() => (
  props.disabled
  || props.readOnly
  || questionPending.value
  || !message.value.trim()
))

function loadPersistedPromptHistory(): string[] {
  if (typeof localStorage === 'undefined') {
    return []
  }
  try {
    const raw = localStorage.getItem(PROMPT_HISTORY_STORAGE_KEY)
    if (!raw) {
      return []
    }
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) {
      return []
    }
    return parsed
      .filter((entry): entry is string => typeof entry === 'string')
      .map((entry) => entry.trim())
      .filter((entry) => entry.length > 0)
      .slice(0, PROMPT_HISTORY_LIMIT)
  } catch {
    return []
  }
}

function savePersistedPromptHistory(entries: string[]): void {
  persistedRecentMessages.value = entries
  if (typeof localStorage === 'undefined') {
    return
  }
  try {
    localStorage.setItem(PROMPT_HISTORY_STORAGE_KEY, JSON.stringify(entries))
  } catch {
    return
  }
}

function rememberPromptHistoryEntry(value: string): void {
  const normalized = value.trim()
  if (!normalized) {
    return
  }
  savePersistedPromptHistory([
    normalized,
    ...persistedRecentMessages.value.filter((entry) => entry !== normalized),
  ].slice(0, PROMPT_HISTORY_LIMIT))
}

function handleSubmit() {
  if (props.disabled || props.readOnly || messageComposing.value) {
    return
  }
  if (sessionRunning.value || questionPending.value) {
    return
  }
  const submittedMessage = message.value.trim()
  if (!submittedMessage) return
  
  emit('send-message', submittedMessage)
  rememberPromptHistoryEntry(submittedMessage)

  historyIndex.value = null
  historyDraft.value = ''
  message.value = ''
  nextTick(() => resizeMessageInput())
}

function handleInterrupt(): void {
  if (props.disabled || props.readOnly || props.interrupting || !sessionRunning.value) {
    return
  }
  emit('interrupt-task')
}

function isComposingEnter(event: KeyboardEvent): boolean {
  const composingEvent = event as KeyboardEvent & { keyCode?: number, which?: number }
  return event.isComposing || messageComposing.value || composingEvent.keyCode === 229 || composingEvent.which === 229
}

function handleMessageKeydown(event: KeyboardEvent): void {
  if (event.key === 'Enter' && isComposingEnter(event)) {
    return
  }
  if ((sessionRunning.value || questionPending.value) && event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    return
  }
  if (event.key === 'ArrowUp') {
    if (handleHistoryNavigation('previous')) {
      event.preventDefault()
    }
    return
  }
  if (event.key === 'ArrowDown') {
    if (handleHistoryNavigation('next')) {
      event.preventDefault()
    }
    return
  }
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    handleSubmit()
  }
}

function handleHistoryNavigation(direction: 'previous' | 'next'): boolean {
  const input = messageInputRef.value
  if (!input || props.activeQuestion) {
    return false
  }
  if (input.selectionStart !== input.selectionEnd) {
    return false
  }

  const atStart = input.selectionStart === 0
  const atEnd = input.selectionEnd === message.value.length
  if (direction === 'previous' && !atStart) {
    return false
  }
  if (direction === 'next' && !atEnd) {
    return false
  }

  const entries = recentMessageHistory()
  if (!entries.length) {
    return false
  }

  if (direction === 'previous') {
    if (historyIndex.value === null) {
      historyDraft.value = message.value
      historyIndex.value = 0
    } else if (historyIndex.value < entries.length - 1) {
      historyIndex.value += 1
    }
  } else {
    if (historyIndex.value === null) {
      return false
    }
    if (historyIndex.value === 0) {
      historyIndex.value = null
      applyHistoryMessage(historyDraft.value)
      return true
    }
    historyIndex.value -= 1
  }

  applyHistoryMessage(entries[historyIndex.value])
  return true
}

function recentMessageHistory(): string[] {
  const history: string[] = []
  const seen = new Set<string>()
  for (const entry of [...(props.recentMessages ?? [])].reverse()) {
    const normalized = entry.trim()
    if (!normalized || seen.has(normalized)) {
      continue
    }
    seen.add(normalized)
    history.push(normalized)
  }
  for (const entry of persistedRecentMessages.value) {
    const normalized = entry.trim()
    if (!normalized || seen.has(normalized)) {
      continue
    }
    seen.add(normalized)
    history.push(normalized)
  }
  return history
}

function applyHistoryMessage(value: string): void {
  applyingHistoryMessage.value = true
  message.value = value
  void nextTick(() => {
    const input = messageInputRef.value
    resizeMessageInput()
    if (input) {
      const cursor = input.value.length
      input.selectionStart = cursor
      input.selectionEnd = cursor
    }
    applyingHistoryMessage.value = false
  })
}

function handleGlobalKeydown(event: KeyboardEvent): void {
  if (event.key !== 'Escape') {
    return
  }
  if (attachmentBrowserOpen.value && editingPath.value) {
    event.preventDefault()
    cancelPathEditing()
    return
  }
  if (attachmentBrowserOpen.value) {
    event.preventDefault()
    closeDirectoryBrowser()
    return
  }
  if (attachmentMenuOpen.value) {
    event.preventDefault()
    attachmentMenuOpen.value = false
  }
}

function resizeMessageInput(): void {
  const element = messageInputRef.value
  if (!element) {
    return
  }
  element.style.height = '0px'
  const nextHeight = Math.min(Math.max(element.scrollHeight, 36), 84)
  element.style.height = `${nextHeight}px`
  element.style.overflowY = element.scrollHeight > 84 ? 'auto' : 'hidden'
}

async function toggleAttachmentMenu(): Promise<void> {
  if (props.readOnly) {
    return
  }
  attachmentMenuOpen.value = !attachmentMenuOpen.value
  if (!attachmentMenuOpen.value) {
    return
  }
  const recent = await listRecentDataDirectories()
  recentDirectories.value = recent.items
}

async function openDirectoryBrowser(path?: string | null): Promise<void> {
  attachmentMenuOpen.value = false
  attachmentBrowserOpen.value = true
  await browsePath(path)
}

async function browsePath(path?: string | null): Promise<boolean> {
  browserLoading.value = true
  browserError.value = ''
  try {
    browserState.value = await browseDataDirectories(path ?? undefined)
    pathDraft.value = browserState.value.current_path
    return true
  } catch (error) {
    const message = error instanceof Error ? error.message : ''
    browserError.value = message === 'Directory not found' ? '目录不存在或无法访问。' : '无法打开该目录。'
    return false
  } finally {
    browserLoading.value = false
  }
}

function attachDirectory(path: string, label?: string | null): void {
  if (props.readOnly) {
    return
  }
  emit('attach-directory', { path, label })
  attachmentMenuOpen.value = false
  attachmentBrowserOpen.value = false
}

function attachCurrentDirectory(): void {
  const currentPath = browserState.value?.current_path
  if (!currentPath) {
    return
  }
  attachDirectory(currentPath, directoryLabel(currentPath))
}

function openAttachedDirectory(path: string): void {
  emit('open-directory', { path })
}

function removeAttachedDirectory(id: string): void {
  emit('remove-directory', id)
}

function closeDirectoryBrowser(): void {
  attachmentBrowserOpen.value = false
  editingPath.value = false
  browserError.value = ''
}

function startPathEditing(): void {
  editingPath.value = true
  pathDraft.value = browserState.value?.current_path ?? ''
  browserError.value = ''
}

function cancelPathEditing(): void {
  editingPath.value = false
  pathDraft.value = browserState.value?.current_path ?? ''
  browserError.value = ''
}

async function confirmPathEditing(): Promise<void> {
  if (!pathDraft.value.trim()) {
    return
  }
  const succeeded = await browsePath(pathDraft.value.trim())
  if (succeeded) {
    editingPath.value = false
  }
}

function directoryLabel(path: string): string {
  const normalized = path.replace(/\/+$/g, '')
  const segments = normalized.split('/').filter(Boolean)
  return segments.at(-1) ?? normalized
}

onMounted(() => {
  resizeMessageInput()
  document.addEventListener('keydown', handleGlobalKeydown)
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', handleGlobalKeydown)
})

watch(message, async () => {
  if (historyIndex.value !== null && !applyingHistoryMessage.value) {
    historyIndex.value = null
  }
  await nextTick()
  resizeMessageInput()
})

watch(
  () => props.activeQuestion,
  (question) => {
    if (!question) {
      return
    }
    message.value = ''
    historyIndex.value = null
    historyDraft.value = ''
    void nextTick(() => resizeMessageInput())
  },
  { immediate: true },
)
</script>

<template>
  <div data-testid="composer-shell" class="pointer-events-none bg-transparent p-4">
    <form data-testid="send-message" @submit.prevent="handleSubmit" class="pointer-events-auto relative overflow-visible rounded-[1.8rem] border border-slate-200/70 bg-white/88 p-2.5 shadow-[0_18px_40px_rgba(15,23,42,0.08)] backdrop-blur-xl dark:border-white/10 dark:bg-zinc-900/88 dark:shadow-[0_18px_40px_rgba(0,0,0,0.28)]">
      <div v-if="attachedDataDirectories.length" class="mb-3 flex flex-wrap items-center gap-2">
        <span
          v-for="directory in attachedDataDirectories"
          :key="directory.id"
          class="inline-flex max-w-full items-center gap-1 rounded-full bg-sky-50 pr-1 py-1 pl-1 text-xs font-medium text-sky-800 ring-1 ring-sky-200/80 dark:bg-sky-500/10 dark:text-sky-200 dark:ring-sky-400/20"
        >
          <button
            :data-testid="`attached-directory-open-${directory.id}`"
            type="button"
            class="inline-flex min-w-0 items-center gap-2 rounded-full px-2 py-1 text-left transition hover:bg-sky-100/80 dark:hover:bg-sky-400/10"
            @click="openAttachedDirectory(directory.path)"
          >
            <Folder2OpenIcon class="h-3.5 w-3.5 shrink-0" />
            <span class="truncate">{{ directory.label ?? directory.path }}</span>
          </button>
          <button
            :data-testid="`attached-directory-remove-${directory.id}`"
            v-if="!readOnly"
            type="button"
            class="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-sky-700/80 transition hover:bg-sky-100 hover:text-sky-900 dark:text-sky-200/80 dark:hover:bg-sky-400/10 dark:hover:text-white"
            @click="removeAttachedDirectory(directory.id)"
          >
            <XLgIcon class="h-3 w-3" />
          </button>
        </span>
      </div>

      <textarea
        ref="messageInputRef"
        data-testid="message-input"
        v-model="message"
        rows="1"
        class="max-h-[84px] min-h-[36px] w-full resize-none overflow-y-auto border-0 bg-transparent px-1.5 py-1.5 text-[15px] leading-6 text-slate-900 outline-none placeholder:text-slate-400 focus:ring-0 dark:text-white dark:placeholder:text-slate-500"
        :disabled="disabled || questionPending"
        :placeholder="isDraft ? '输入你的第一条提示词...' : '请输入您的指令...'"
        @input="resizeMessageInput"
        @compositionstart="messageComposing = true"
        @compositionend="messageComposing = false"
        @keydown="handleMessageKeydown"
      />

      <div class="relative mt-2 flex items-center justify-between gap-3">
        <div class="flex min-w-0 flex-wrap items-center gap-2">
        <button
          v-if="!readOnly"
          data-testid="composer-attach-trigger"
          type="button"
          class="inline-flex h-9 items-center gap-2 rounded-full border px-3 text-sm font-medium transition"
          :class="attachmentMenuOpen || attachmentBrowserOpen
            ? 'border-bjut-blue/30 bg-bjut-blue/10 text-bjut-blue hover:border-bjut-blue/40 hover:bg-bjut-blue/12 hover:text-bjut-blue dark:border-cyan-400/40 dark:bg-cyan-400/16 dark:text-cyan-100 dark:hover:border-cyan-300/55 dark:hover:bg-cyan-400/22 dark:hover:text-white'
            : 'border-slate-200 bg-white text-slate-700 hover:border-slate-300 hover:bg-slate-50 hover:text-slate-900 dark:border-white/10 dark:bg-white/5 dark:text-slate-200 dark:hover:border-white/20 dark:hover:bg-white/10 dark:hover:text-white'"
          @click="toggleAttachmentMenu"
        >
          <PlusLgIcon class="h-3.5 w-3.5" />
          <span>添加数据</span>
        </button>

          <div v-if="attachmentMenuOpen" data-testid="composer-attach-menu" class="absolute bottom-[calc(100%+0.75rem)] left-0 z-10 w-72 rounded-2xl border border-slate-200/80 bg-white/96 p-2 shadow-[0_20px_50px_rgba(15,23,42,0.18)] backdrop-blur-xl dark:border-white/10 dark:bg-zinc-900/96 dark:shadow-[0_20px_50px_rgba(0,0,0,0.38)]">
            <div class="px-3 pb-2 pt-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-500 dark:text-slate-400">最近目录</div>
            <div class="space-y-1">
              <button
                v-for="item in recentDirectories"
                :key="item.id"
                :data-testid="`recent-directory-${item.id}`"
                type="button"
                class="flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left text-sm text-slate-700 transition hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-white/5"
                @click="attachDirectory(item.path, item.label)"
              >
                <ClockHistoryIcon class="h-3.5 w-3.5 shrink-0 text-slate-400" />
                <span class="truncate">{{ item.label ?? item.path }}</span>
              </button>
              <div v-if="!recentDirectories.length" class="px-3 py-2 text-sm text-slate-500 dark:text-slate-400">暂无最近目录</div>
            </div>
            <div class="mt-2 border-t border-slate-200/70 pt-2 dark:border-white/10">
              <button
                data-testid="composer-open-browser"
                type="button"
                class="flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left text-sm font-medium text-slate-700 transition hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-white/5"
                @click="openDirectoryBrowser()"
              >
                <Folder2OpenIcon class="h-3.5 w-3.5 shrink-0 text-slate-400" />
                <span>选择其他目录</span>
              </button>
            </div>
          </div>

          <button
            v-if="workspacePath"
            data-testid="composer-open-workspace"
            type="button"
            class="inline-flex h-9 items-center gap-2 rounded-full border border-slate-200 bg-white px-3 text-sm font-medium text-slate-700 transition hover:border-slate-300 hover:bg-slate-50 hover:text-slate-900 dark:border-white/10 dark:bg-white/5 dark:text-slate-200 dark:hover:border-white/20 dark:hover:bg-white/10 dark:hover:text-white"
            @click="$emit('open-workspace')"
          >
            <BoxArrowUpRightIcon class="h-3.5 w-3.5" />
            <span>打开工作区</span>
          </button>
        </div>

        <button
          v-if="sessionRunning"
          data-testid="interrupt-task-button"
          type="button"
          :disabled="disabled || (interrupting ?? false)"
          class="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-slate-200 text-slate-700 shadow-sm transition hover:bg-slate-300 hover:text-slate-900 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-white/10 dark:text-slate-200 dark:hover:bg-white/15 dark:hover:text-white"
          aria-label="中断当前任务"
          title="中断当前任务"
          @click="handleInterrupt"
        >
          <XLgIcon class="h-4 w-4" />
        </button>
        <button
          v-else
          type="submit"
          :disabled="composerSubmitDisabled"
          class="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-slate-900 text-white shadow-sm transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bjut-blue dark:hover:bg-bjut-blue-hover"
        >
          <ArrowUpRightCircleFillIcon data-testid="send-button-icon" class="h-5 w-5" />
        </button>
      </div>
    </form>

    <Teleport to="body">
      <div v-if="attachmentBrowserOpen" data-testid="composer-directory-modal" class="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/52 p-4 backdrop-blur-sm" @click.self="closeDirectoryBrowser">
        <div class="flex h-[min(44rem,calc(100vh-2rem))] w-full max-w-3xl flex-col overflow-hidden rounded-[1.75rem] border border-slate-200/80 bg-white/96 shadow-[0_32px_80px_rgba(15,23,42,0.22)] dark:border-white/10 dark:bg-zinc-900/96 dark:shadow-[0_32px_80px_rgba(0,0,0,0.45)]">
          <div class="flex items-start justify-between gap-3 border-b border-slate-200/70 px-5 py-4 dark:border-white/10">
            <div>
              <h3 class="text-base font-semibold text-slate-900 dark:text-white">选择数据目录</h3>
              <p class="mt-1 text-sm text-slate-500 dark:text-slate-400">从本地工作目录中选择要附加到当前会话的数据路径。</p>
            </div>
            <button type="button" class="inline-flex h-9 w-9 items-center justify-center rounded-full border border-slate-200 text-slate-600 transition hover:border-slate-300 hover:text-slate-900 dark:border-white/10 dark:text-slate-300 dark:hover:border-white/20 dark:hover:text-white" @click="closeDirectoryBrowser">
              <XLgIcon class="h-4 w-4" />
            </button>
          </div>

          <div class="flex min-h-0 flex-1 flex-col gap-4 px-5 py-4">
            <div class="flex items-center gap-2">
              <button
                v-if="browserState?.parent_path"
                type="button"
                class="inline-flex h-10 shrink-0 items-center gap-1 rounded-full border border-slate-200 px-3 text-sm font-medium text-slate-700 transition hover:border-slate-300 hover:bg-slate-50 dark:border-white/10 dark:text-slate-200 dark:hover:bg-white/10 dark:hover:text-white"
                @click="browsePath(browserState.parent_path)"
              >
                <ChevronLeftIcon class="h-3.5 w-3.5" />
                <span>上一级</span>
              </button>

              <div class="min-w-0 flex-1">
                <button
                  v-if="!editingPath"
                  data-testid="directory-path-display"
                  type="button"
                  class="h-10 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 text-left text-[13px] font-mono text-slate-600 transition hover:border-slate-300 hover:bg-white dark:border-white/10 dark:bg-white/5 dark:text-slate-300 dark:hover:bg-white/8"
                  @click="startPathEditing"
                >
                  {{ browserState?.current_path }}
                </button>
                <input
                  v-else
                  id="directory-path-input"
                  data-testid="directory-path-input"
                  v-model="pathDraft"
                  type="text"
                  class="h-10 w-full rounded-xl border border-bjut-blue/35 bg-white px-3 text-[13px] font-mono text-slate-700 outline-none ring-2 ring-bjut-blue/12 dark:border-cyan-400/35 dark:bg-white/8 dark:text-slate-100 dark:ring-cyan-400/12"
                  @keydown.enter.prevent="confirmPathEditing"
                  @keydown.esc.prevent="cancelPathEditing"
                />
              </div>

              <div v-if="editingPath" class="flex shrink-0 items-center gap-2">
                <button type="button" class="inline-flex h-10 items-center rounded-full border border-slate-200 px-3 text-sm font-medium text-slate-600 transition hover:border-slate-300 hover:text-slate-900 dark:border-white/10 dark:text-slate-300 dark:hover:text-white" @click="cancelPathEditing">取消</button>
                <button data-testid="directory-path-submit" type="button" class="inline-flex h-10 items-center rounded-full bg-bjut-blue px-3 text-sm font-medium text-white transition hover:bg-bjut-blue-hover" @click="confirmPathEditing">确认</button>
              </div>

              <div v-else class="flex shrink-0 items-center gap-2">
                <button data-testid="directory-shortcut-home" type="button" class="inline-flex h-10 w-10 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-600 transition hover:border-slate-300 hover:bg-slate-50 hover:text-slate-900 dark:border-white/10 dark:bg-white/5 dark:text-slate-300 dark:hover:bg-white/10 dark:hover:text-white" title="转到用户主目录" @click="browsePath(browserState?.home_path)">
                  <HouseDoorIcon class="h-4 w-4" />
                </button>
                <button data-testid="directory-shortcut-cwd" type="button" class="inline-flex h-10 w-10 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-600 transition hover:border-slate-300 hover:bg-slate-50 hover:text-slate-900 dark:border-white/10 dark:bg-white/5 dark:text-slate-300 dark:hover:bg-white/10 dark:hover:text-white" title="转到当前工作目录" @click="browsePath(browserState?.cwd_path)">
                  <TerminalIcon class="h-4 w-4" />
                </button>
              </div>
            </div>

            <p v-if="browserError" class="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700 dark:border-rose-400/20 dark:bg-rose-500/10 dark:text-rose-200">{{ browserError }}</p>

            <div class="min-h-0 flex-1 overflow-y-auto rounded-2xl border border-slate-200/70 bg-slate-50/70 p-2 dark:border-white/10 dark:bg-slate-950/40">
              <div class="space-y-2">
                <button
                  v-for="entry in browserState?.entries ?? []"
                  :key="entry.path"
                  :data-testid="`browser-directory-${entry.name}`"
                  type="button"
                  class="flex w-full items-center justify-between gap-3 rounded-xl bg-white px-3 py-3 text-left text-sm text-slate-700 ring-1 ring-slate-200/70 transition hover:ring-slate-300 dark:bg-white/5 dark:text-slate-200 dark:ring-white/10"
                  @click="browsePath(entry.path)"
                >
                  <div class="flex min-w-0 items-center gap-3">
                    <Folder2OpenIcon class="h-4 w-4 shrink-0 text-slate-400" />
                    <span class="truncate">{{ entry.name }}</span>
                  </div>
                  <span class="text-xs text-slate-400">进入</span>
                </button>
                <p v-if="browserLoading" class="px-3 py-2 text-sm text-slate-500 dark:text-slate-400">正在加载目录...</p>
                <p v-else-if="!(browserState?.entries.length ?? 0)" class="px-3 py-2 text-sm text-slate-500 dark:text-slate-400">当前目录下没有可选子目录。</p>
              </div>
            </div>

            <div class="flex items-center justify-end gap-2 border-t border-slate-200/70 pt-3 dark:border-white/10">
              <button
                data-testid="directory-cancel"
                type="button"
                class="inline-flex h-9 items-center rounded-full border border-slate-200 px-3 text-sm font-medium text-slate-600 transition hover:border-slate-300 hover:bg-slate-50 hover:text-slate-900 dark:border-white/10 dark:text-slate-300 dark:hover:bg-white/5 dark:hover:text-white"
                @click="closeDirectoryBrowser"
              >
                取消
              </button>
              <button
                data-testid="directory-select-current"
                type="button"
                class="inline-flex h-9 items-center rounded-full bg-bjut-blue px-3 text-sm font-medium text-white transition hover:bg-bjut-blue-hover disabled:cursor-not-allowed disabled:opacity-50"
                :disabled="!browserState?.current_path"
                @click="attachCurrentDirectory"
              >
                选择当前目录
              </button>
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
