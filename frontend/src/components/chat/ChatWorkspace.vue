<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { Artifact, ChatMessage, DataDirectoryAttachment, Question, QuestionReplyPayload } from '../../types'
import MessageList from './MessageList.vue'
import ChatInput from './ChatInput.vue'

const defaultComposerOverlayOffsetPx = 192

const props = withDefaults(defineProps<{
  activeSessionId: string | null
  isDraft: boolean
  sessionStatus: 'idle' | 'running' | 'waiting_for_input' | 'completed' | 'failed' | null
  inputDisabled?: boolean
  interrupting?: boolean
  readOnly?: boolean
  showThinking?: boolean
  messages: ChatMessage[]
  recentMessages: string[]
  activeQuestion: Question | null
  artifacts?: Artifact[]
  finalArtifacts?: Artifact[]
  attachedDataDirectories: DataDirectoryAttachment[]
  workspacePath: string | null
}>(), {
  artifacts: () => [],
  finalArtifacts: () => [],
})

defineEmits<{
  (e: 'send-message', text: string): void
  (e: 'interrupt-task'): void
  (e: 'reply-question', payload: QuestionReplyPayload): void
  (e: 'open-artifact', artifact: Artifact): void
  (e: 'preview-artifact', artifact: Artifact): void
  (e: 'attach-directory', item: { path: string, label?: string | null }): void
  (e: 'open-directory', item: { path: string }): void
  (e: 'remove-directory', id: string): void
  (e: 'open-workspace'): void
}>()

const composerOverlayRef = ref<HTMLElement | null>(null)
const composerOverlayOffsetPx = ref(defaultComposerOverlayOffsetPx)
let composerResizeObserver: ResizeObserver | null = null

const workspaceStyle = computed<Record<string, string>>(() => ({
  '--composer-overlay-offset': `${props.readOnly ? 0 : composerOverlayOffsetPx.value}px`,
}))

function updateComposerOverlayOffset(height: number): void {
  const nextHeight = Math.ceil(height)
  if (nextHeight <= 0) {
    return
  }

  composerOverlayOffsetPx.value = nextHeight
}

function measureComposerOverlay(): void {
  if (props.readOnly) {
    return
  }
  const overlay = composerOverlayRef.value
  if (!overlay) {
    return
  }

  updateComposerOverlayOffset(overlay.getBoundingClientRect().height)
}

function disconnectComposerResizeObserver(): void {
  composerResizeObserver?.disconnect()
  composerResizeObserver = null
}

function observeComposerOverlay(): void {
  if (props.readOnly) {
    disconnectComposerResizeObserver()
    return
  }

  measureComposerOverlay()

  const overlay = composerOverlayRef.value
  if (!overlay || typeof ResizeObserver === 'undefined') {
    return
  }

  disconnectComposerResizeObserver()
  composerResizeObserver = new ResizeObserver((entries) => {
    const entry = entries[0]
    if (!entry) {
      measureComposerOverlay()
      return
    }

    updateComposerOverlayOffset(entry.contentRect.height)
  })
  composerResizeObserver.observe(overlay)
}

onMounted(() => {
  observeComposerOverlay()
})

onBeforeUnmount(() => {
  disconnectComposerResizeObserver()
})

watch(
  () => props.readOnly,
  async () => {
    await nextTick()
    observeComposerOverlay()
  },
  { flush: 'post' },
)

watch(composerOverlayRef, async () => {
  await nextTick()
  observeComposerOverlay()
})
</script>

<template>
  <main data-testid="chat-workspace" class="relative z-0 isolate flex min-w-0 flex-1 flex-col bg-white dark:bg-zinc-950/80" :style="workspaceStyle">
    <MessageList
      :messages="messages"
      :isDraft="isDraft"
      :sessionStatus="sessionStatus"
      :showThinking="showThinking ?? false"
      :activeQuestion="activeQuestion"
      :activeSessionId="activeSessionId"
      :artifacts="artifacts"
      :finalArtifacts="finalArtifacts"
      :artifact-actions-disabled="readOnly ?? false"
      @open-artifact="$emit('open-artifact', $event)"
      @preview-artifact="$emit('preview-artifact', $event)"
      @reply-question="readOnly ? undefined : $emit('reply-question', $event)"
    />

    <div v-if="!readOnly" ref="composerOverlayRef" data-testid="composer-overlay" class="pointer-events-none absolute inset-x-0 bottom-0 z-10 bg-gradient-to-b from-transparent via-white/80 to-white pt-12 dark:via-zinc-950/80 dark:to-zinc-950">
      <ChatInput
        :disabled="inputDisabled || (!activeSessionId && !isDraft)"
        :isDraft="isDraft"
        :sessionStatus="sessionStatus"
        :interrupting="interrupting ?? false"
        :readOnly="readOnly ?? false"
        :activeQuestion="readOnly ? null : activeQuestion"
        :recentMessages="recentMessages"
        :attachedDataDirectories="attachedDataDirectories"
        :workspacePath="readOnly ? null : workspacePath"
        @send-message="$emit('send-message', $event)"
        @interrupt-task="$emit('interrupt-task')"
        @attach-directory="$emit('attach-directory', $event)"
        @open-directory="$emit('open-directory', $event)"
        @remove-directory="$emit('remove-directory', $event)"
        @open-workspace="$emit('open-workspace')"
      />
    </div>
  </main>
</template>
