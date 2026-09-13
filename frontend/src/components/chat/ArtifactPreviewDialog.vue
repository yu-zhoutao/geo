<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import BoxArrowUpRightIcon from 'bootstrap-icons/icons/box-arrow-up-right.svg'
import XIcon from 'bootstrap-icons/icons/x.svg'
import type { Artifact } from '../../types'
import { artifactPreviewKind, loadTextArtifactPreview, previewContentUrl } from './artifactPreview'
import ArtifactTablePreview from './ArtifactTablePreview.vue'
import { renderMarkdown } from './markdown'
import { MODAL_TABLE_PREVIEW_MAX_ROWS, parseDelimitedTablePreview, tableDelimiterForArtifact } from './tablePreview'

const props = defineProps<{
  open: boolean
  artifact: Artifact | null
  sessionId: string | null
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'open-artifact', artifact: Artifact): void
}>()

const previewText = ref('')
const previewError = ref('')
const previewLoading = ref(false)

const previewKind = computed(() => (props.artifact ? artifactPreviewKind(props.artifact) : 'other'))
const contentUrl = computed(() => (props.artifact ? previewContentUrl(props.sessionId, props.artifact) : ''))
const canLoadText = computed(() => ['markdown', 'text', 'table'].includes(previewKind.value))
const renderedMarkdown = computed(() => renderMarkdown(previewText.value))
const tablePreview = computed(() => (
  props.artifact && previewKind.value === 'table'
    ? parseDelimitedTablePreview(previewText.value, tableDelimiterForArtifact(props.artifact), MODAL_TABLE_PREVIEW_MAX_ROWS)
    : null
))

watch(
  () => [props.open, props.sessionId, props.artifact?.id],
  async () => {
    previewText.value = ''
    previewError.value = ''
    previewLoading.value = false
    if (!props.open || !props.artifact || !props.sessionId || !canLoadText.value) {
      return
    }

    previewLoading.value = true
    try {
      previewText.value = await loadTextArtifactPreview(props.sessionId, props.artifact)
    } catch {
      previewError.value = '预览不可用'
    } finally {
      previewLoading.value = false
    }
  },
  { immediate: true },
)

function openArtifact(): void {
  if (props.artifact) {
    emit('open-artifact', props.artifact)
  }
}
</script>

<template>
  <Teleport to="body">
    <div
      v-if="open && artifact"
      data-testid="artifact-preview-dialog"
      class="fixed inset-0 z-[90] flex items-center justify-center bg-slate-950/35 px-4 py-6 backdrop-blur-sm"
      @click.self="emit('close')"
    >
      <section class="flex max-h-[min(44rem,calc(100vh-3rem))] w-[min(56rem,calc(100vw-2rem))] flex-col overflow-hidden rounded-xl border border-slate-200/80 bg-white shadow-2xl shadow-slate-950/18 dark:border-white/10 dark:bg-zinc-950 dark:shadow-black/40">
        <header class="flex items-center justify-between gap-3 border-b border-slate-200/70 px-4 py-3 dark:border-white/8">
          <div class="min-w-0">
            <h2 class="truncate text-sm font-semibold text-slate-900 dark:text-slate-100">{{ artifact.title }}</h2>
            <p class="truncate font-mono text-[11px] text-slate-500 dark:text-slate-500">{{ artifact.path }}</p>
          </div>
          <div class="flex shrink-0 items-center gap-1">
            <button
              type="button"
              data-testid="artifact-preview-open"
              :aria-label="`打开${artifact.title}`"
              :title="`打开${artifact.title}`"
              class="inline-flex h-8 w-8 items-center justify-center rounded-full text-slate-500 transition hover:bg-slate-100 hover:text-bjut-blue dark:text-slate-400 dark:hover:bg-white/8 dark:hover:text-cyan-200"
              @click="openArtifact"
            >
              <BoxArrowUpRightIcon class="h-4 w-4" />
            </button>
            <button
              type="button"
              data-testid="artifact-preview-close"
              aria-label="关闭预览"
              title="关闭"
              class="inline-flex h-8 w-8 items-center justify-center rounded-full text-slate-500 transition hover:bg-slate-100 hover:text-slate-700 dark:text-slate-400 dark:hover:bg-white/8 dark:hover:text-slate-200"
              @click="emit('close')"
            >
              <XIcon class="h-4 w-4" />
            </button>
          </div>
        </header>

        <div class="min-h-0 flex-1 overflow-auto p-4">
          <img
            v-if="previewKind === 'image'"
            :src="contentUrl"
            :alt="artifact.title"
            class="mx-auto max-h-[36rem] max-w-full rounded-lg object-contain"
          />
          <iframe
            v-else-if="previewKind === 'html'"
            :src="contentUrl"
            title="artifact preview"
            sandbox="allow-scripts allow-same-origin"
            class="h-[36rem] min-h-96 w-full rounded-lg border border-slate-200 bg-white dark:border-white/10"
          ></iframe>
          <div
            v-else-if="previewKind === 'markdown' && previewText"
            class="message-markdown message-markdown--assistant-theme max-w-none"
            v-html="renderedMarkdown"
          ></div>
          <ArtifactTablePreview
            v-else-if="previewKind === 'table' && previewText && tablePreview"
            :preview="tablePreview"
            :max-rows="MODAL_TABLE_PREVIEW_MAX_ROWS"
          />
          <pre
            v-else-if="previewKind === 'text' && previewText"
            class="max-h-[36rem] overflow-auto rounded-lg bg-slate-50 px-3 py-2 font-mono text-xs leading-5 text-slate-700 dark:bg-black/24 dark:text-slate-200"
          >{{ previewText }}</pre>
          <p v-else-if="previewLoading" class="text-sm text-slate-500 dark:text-slate-400">加载预览...</p>
          <p v-else-if="previewError" class="text-sm text-slate-500 dark:text-slate-400">{{ previewError }}</p>
          <p v-else class="text-sm text-slate-500 dark:text-slate-400">无法预览此产物。</p>
        </div>
      </section>
    </div>
  </Teleport>
</template>
