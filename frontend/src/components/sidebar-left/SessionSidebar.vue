<script setup lang="ts">
import { computed, ref } from 'vue'
import PlusLgIcon from 'bootstrap-icons/icons/plus-lg.svg'
import ClockHistoryIcon from 'bootstrap-icons/icons/clock-history.svg'
import ChatTextIcon from 'bootstrap-icons/icons/chat-text.svg'
import ArrowRepeatIcon from 'bootstrap-icons/icons/arrow-repeat.svg'
import ListCheckIcon from 'bootstrap-icons/icons/list-check.svg'
import Check2AllIcon from 'bootstrap-icons/icons/check2-all.svg'
import CheckLgIcon from 'bootstrap-icons/icons/check-lg.svg'
import XLgIcon from 'bootstrap-icons/icons/x-lg.svg'
import XSquareIcon from 'bootstrap-icons/icons/x-square.svg'
import Trash3Icon from 'bootstrap-icons/icons/trash3.svg'
import UploadIcon from 'bootstrap-icons/icons/upload.svg'
import SessionActionMenu from '../shared/SessionActionMenu.vue'

import type { SessionSummary } from '../../types'

const props = defineProps<{
  sessions: SessionSummary[]
  activeSessionId?: string | null
  batchMode?: boolean
  selectedSessionIds?: string[]
}>()

const emit = defineEmits<{
  (e: 'start-session'): void
  (e: 'resume-session', id: string): void
  (e: 'rename-session', id: string): void
  (e: 'export-session', id: string): void
  (e: 'request-delete-session', id: string): void
  (e: 'import-session-archive', file: File): void
  (e: 'enter-batch-mode'): void
  (e: 'cancel-batch-mode'): void
  (e: 'toggle-session-selection', id: string): void
  (e: 'toggle-all-session-selection'): void
  (e: 'request-delete-selected-sessions'): void
}>()

const archiveInput = ref<HTMLInputElement | null>(null)
const allSessionsSelected = computed<boolean>(() => (
  props.sessions.length > 0 && props.sessions.every((session) => isSessionSelected(session.id))
))
const toggleAllSessionTitle = computed<string>(() => (allSessionsSelected.value ? '取消全选' : '全选会话'))

function isSessionSelected(sessionId: string): boolean {
  return props.selectedSessionIds?.includes(sessionId) ?? false
}

function handleSessionClick(sessionId: string): void {
  if (props.batchMode) {
    emit('toggle-session-selection', sessionId)
    return
  }
  emit('resume-session', sessionId)
}

function requestArchiveImport(): void {
  archiveInput.value?.click()
}

function handleArchiveImport(event: Event): void {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) {
    emit('import-session-archive', file)
  }
  input.value = ''
}
</script>

<template>
  <aside class="relative z-40 flex w-72 shrink-0 flex-col border-r border-slate-200/60 bg-white/75 backdrop-blur-xl dark:border-white/8 dark:bg-zinc-950/70">
    <div class="flex h-14 items-center justify-between border-b border-slate-200/60 px-4 dark:border-white/8">
      <div class="flex items-center gap-2 text-slate-900 dark:text-white">
        <div class="flex h-9 w-9 items-center justify-center rounded-2xl bg-slate-100/80 text-slate-500 dark:bg-white/5 dark:text-slate-300">
          <ClockHistoryIcon class="h-4 w-4" />
        </div>
        <div>
          <h2 class="text-sm font-semibold">会话</h2>
        </div>
      </div>
      <div class="flex items-center gap-1.5">
        <button
          v-if="!batchMode"
          data-testid="import-session-archive"
          class="inline-flex h-9 w-9 items-center justify-center rounded-full text-slate-500 transition hover:bg-slate-100 hover:text-slate-900 dark:text-slate-300 dark:hover:bg-white/6 dark:hover:text-white"
          title="导入会话记录"
          aria-label="导入会话记录"
          type="button"
          @click="requestArchiveImport"
        >
          <UploadIcon class="h-4 w-4" />
        </button>
        <input
          ref="archiveInput"
          data-testid="import-session-archive-input"
          class="hidden"
          type="file"
          accept="application/json,.json"
          @change="handleArchiveImport"
        />
        <button
          v-if="!batchMode"
          data-testid="enter-session-batch-mode"
          class="inline-flex h-9 w-9 items-center justify-center rounded-full text-slate-500 transition hover:bg-slate-100 hover:text-slate-900 dark:text-slate-300 dark:hover:bg-white/6 dark:hover:text-white"
          title="批量选择会话"
          aria-label="批量选择会话"
          type="button"
          @click="$emit('enter-batch-mode')"
        >
          <ListCheckIcon class="h-4 w-4" />
        </button>
        <button
          v-else
          data-testid="cancel-session-batch-mode"
          class="inline-flex h-9 w-9 items-center justify-center rounded-full text-slate-500 transition hover:bg-slate-100 hover:text-slate-900 dark:text-slate-300 dark:hover:bg-white/6 dark:hover:text-white"
          title="取消批量选择"
          aria-label="取消批量选择"
          type="button"
          @click="$emit('cancel-batch-mode')"
        >
          <XLgIcon class="h-3.5 w-3.5" />
        </button>
        <button
          v-if="batchMode"
          data-testid="toggle-all-session-selection"
          class="inline-flex h-9 w-9 items-center justify-center rounded-full transition"
          :class="allSessionsSelected ? 'text-slate-500 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-300 dark:hover:bg-white/6 dark:hover:text-white' : 'text-bjut-blue hover:bg-bjut-blue/10 dark:text-cyan-300 dark:hover:bg-cyan-300/10'"
          :title="toggleAllSessionTitle"
          :aria-label="toggleAllSessionTitle"
          :disabled="sessions.length === 0"
          type="button"
          @click="$emit('toggle-all-session-selection')"
        >
          <XSquareIcon v-if="allSessionsSelected" class="h-4 w-4" />
          <Check2AllIcon v-else class="h-4 w-4" />
        </button>
        <button
          v-if="!batchMode"
          data-testid="start-session"
          class="inline-flex h-9 w-9 items-center justify-center rounded-full bg-slate-900 text-white shadow-sm transition hover:bg-slate-700 dark:bg-white dark:text-slate-900 dark:hover:bg-slate-200"
          title="开始新会话"
          aria-label="开始新会话"
          type="button"
          @click="$emit('start-session')"
        >
          <PlusLgIcon class="h-4 w-4" />
        </button>
        <button
          v-else
          data-testid="delete-selected-sessions"
          class="inline-flex h-9 w-9 items-center justify-center rounded-full transition"
          :class="selectedSessionIds?.length ? 'bg-rose-500 text-white shadow-sm hover:bg-rose-600' : 'cursor-not-allowed bg-rose-50 text-rose-300 dark:bg-rose-500/10 dark:text-rose-400/60'"
          :disabled="!selectedSessionIds?.length"
          title="删除所选会话"
          aria-label="删除所选会话"
          type="button"
          @click="$emit('request-delete-selected-sessions')"
        >
          <Trash3Icon class="h-4 w-4" />
        </button>
      </div>
    </div>

    <div class="flex-1 overflow-y-auto px-2.5 py-3">
      <button
        v-for="session in sessions"
        :key="session.id"
        :data-testid="`session-row-${session.id}`"
        class="group mb-1 flex w-full rounded-xl px-2.5 py-1.5 text-left transition last:mb-0"
        :class="[
          batchMode && isSessionSelected(session.id)
            ? 'bg-bjut-blue/[0.09] ring-1 ring-bjut-blue/15 dark:bg-bjut-blue/[0.15] dark:ring-bjut-blue/20'
            : session.id === activeSessionId
            ? 'bg-bjut-blue/[0.07] shadow-sm ring-1 ring-bjut-blue/10 dark:bg-bjut-blue/[0.12] dark:ring-bjut-blue/15'
            : 'hover:bg-slate-100/80 dark:hover:bg-white/4'
        ]"
        type="button"
        @click="handleSessionClick(session.id)"
      >
        <div class="flex w-full items-center justify-between gap-1.5">
          <div class="min-w-0 flex flex-1 items-center gap-1.5">
            <span
              v-if="session.status === 'running'"
              :data-testid="`running-indicator-${session.id}`"
              class="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-bjut-blue/10 text-bjut-blue dark:bg-bjut-blue/15 dark:text-cyan-200"
              aria-label="会话运行中"
              title="会话运行中"
            >
              <ArrowRepeatIcon class="h-3 w-3 animate-spin" />
            </span>
            <ChatTextIcon v-else class="h-3.5 w-3.5 shrink-0 text-slate-400 transition group-hover:text-bjut-blue dark:text-slate-500" />
            <span class="block min-w-0 flex-1 truncate text-sm font-medium" :class="session.id === activeSessionId ? 'text-bjut-blue dark:text-cyan-50' : 'text-slate-900 dark:text-white'">{{ session.title }}</span>
            <span
              v-if="session.read_only"
              :data-testid="`readonly-session-badge-${session.id}`"
              class="shrink-0 rounded-full bg-slate-100 px-1.5 py-0.5 text-[9px] font-semibold text-slate-500 dark:bg-white/8 dark:text-slate-300"
            >
              只读
            </span>
          </div>

          <span
            :data-testid="`session-action-slot-${session.id}`"
            class="inline-flex h-8 w-8 shrink-0 items-center justify-center"
            v-if="!batchMode"
          >
            <SessionActionMenu
              :session-id="session.id"
              :read-only="session.read_only"
              @rename="$emit('rename-session', $event)"
              @export="$emit('export-session', $event)"
              @delete="$emit('request-delete-session', $event)"
            />
          </span>
          <span
            v-else
            :data-testid="`session-action-slot-${session.id}`"
            class="inline-flex h-8 w-8 shrink-0 items-center justify-center"
          >
            <span
              :data-testid="`session-checkbox-${session.id}`"
              class="inline-flex h-5 w-5 items-center justify-center rounded-md border transition"
              :class="isSessionSelected(session.id) ? 'border-bjut-blue bg-bjut-blue text-white shadow-sm shadow-bjut-blue/20 dark:border-cyan-300 dark:bg-cyan-400 dark:text-zinc-950' : 'border-slate-300 bg-white text-transparent group-hover:border-bjut-blue dark:border-white/15 dark:bg-white/5 dark:group-hover:border-cyan-300'"
              role="checkbox"
              :aria-checked="isSessionSelected(session.id) ? 'true' : 'false'"
              :aria-label="isSessionSelected(session.id) ? '取消选择会话' : '选择会话'"
            >
              <CheckLgIcon class="h-3 w-3" />
            </span>
          </span>
        </div>
      </button>

      <div v-if="sessions.length === 0" class="flex h-full min-h-40 items-center justify-center px-4 text-center">
        <div class="space-y-2 text-sm text-slate-500 dark:text-slate-400">
          <div class="mx-auto flex h-11 w-11 items-center justify-center rounded-2xl bg-slate-100 text-slate-400 dark:bg-white/5 dark:text-slate-500">
            <ClockHistoryIcon class="h-4 w-4" />
          </div>
          <p class="italic">暂无会话。</p>
        </div>
      </div>
    </div>
  </aside>
</template>
