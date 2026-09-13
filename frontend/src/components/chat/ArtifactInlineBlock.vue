<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import BoxArrowUpRightIcon from 'bootstrap-icons/icons/box-arrow-up-right.svg'
import EyeIcon from 'bootstrap-icons/icons/eye.svg'
import FileTextIcon from 'bootstrap-icons/icons/file-earmark-text.svg'
import ImageIcon from 'bootstrap-icons/icons/image.svg'
import MapIcon from 'bootstrap-icons/icons/map.svg'
import TableIcon from 'bootstrap-icons/icons/table.svg'
import BracesIcon from 'bootstrap-icons/icons/braces.svg'
import type { Artifact } from '../../types'
import { artifactPreviewKind, canPreviewArtifact, loadTextArtifactPreview, previewContentUrl } from './artifactPreview'
import ArtifactTablePreview from './ArtifactTablePreview.vue'
import { renderMarkdown } from './markdown'
import { INLINE_TABLE_PREVIEW_MAX_ROWS, parseDelimitedTablePreview, tableDelimiterForArtifact } from './tablePreview'

const props = defineProps<{
  artifact: Artifact
  sessionId: string | null
  actionsDisabled?: boolean
}>()

const emit = defineEmits<{
  (e: 'open-artifact', artifact: Artifact): void
}>()

const previewText = ref('')
const previewError = ref('')
const previewOpen = ref(false)
const previewLoading = ref(false)

const displayHint = computed(() => props.artifact.display_hint ?? 'download')
const previewKind = computed(() => artifactPreviewKind(props.artifact))
const previewable = computed(() => Boolean(props.sessionId) && !props.actionsDisabled && canPreviewArtifact(props.artifact))
const contentUrl = computed(() => previewContentUrl(props.sessionId, props.artifact))
const isImagePreview = computed(() => previewOpen.value && previewKind.value === 'image')
const isHtmlPreview = computed(() => previewOpen.value && previewKind.value === 'html')
const isMarkdownPreview = computed(() => previewOpen.value && previewKind.value === 'markdown' && previewText.value)
const isTablePreview = computed(() => previewOpen.value && previewKind.value === 'table' && previewText.value)
const isTextPreview = computed(() => previewOpen.value && previewKind.value === 'text' && previewText.value)
const tablePreview = computed(() => (
  previewKind.value === 'table'
    ? parseDelimitedTablePreview(previewText.value, tableDelimiterForArtifact(props.artifact), INLINE_TABLE_PREVIEW_MAX_ROWS)
    : null
))

const iconComponent = computed(() => {
  if (displayHint.value === 'map') return MapIcon
  if (displayHint.value === 'image') return ImageIcon
  if (displayHint.value === 'table') return TableIcon
  if (displayHint.value === 'json') return BracesIcon
  return FileTextIcon
})

watch(
  () => [props.sessionId, props.artifact.id],
  () => {
    previewText.value = ''
    previewError.value = ''
    previewOpen.value = false
    previewLoading.value = false
  },
)

function openArtifact(): void {
  if (!props.sessionId || props.actionsDisabled) {
    return
  }
  emit('open-artifact', props.artifact)
}

function renderedPreviewText(): string {
  return renderMarkdown(previewText.value)
}

async function togglePreview(): Promise<void> {
  if (!props.sessionId || !previewable.value) {
    return
  }
  previewOpen.value = !previewOpen.value
  previewError.value = ''
  if (!previewOpen.value || previewText.value || !['markdown', 'text', 'table'].includes(previewKind.value)) {
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
}
</script>

<template>
  <div
    data-testid="inline-artifact-block"
    class="my-2 border-l-2 border-cyan-400/65 bg-cyan-50/50 px-3 py-2.5 text-sm text-slate-700 dark:border-cyan-300/55 dark:bg-cyan-400/[0.055] dark:text-slate-200"
  >
    <div class="flex min-w-0 items-start justify-between gap-3">
      <div class="flex min-w-0 items-start gap-2">
        <component :is="iconComponent" class="mt-0.5 h-4 w-4 shrink-0 text-bjut-blue dark:text-cyan-300" />
        <div class="min-w-0">
          <p class="truncate font-semibold text-slate-900 dark:text-slate-100">{{ artifact.title }}</p>
          <p v-if="artifact.description" class="mt-0.5 max-h-10 overflow-hidden text-[12px] leading-5 text-slate-500 dark:text-slate-400">{{ artifact.description }}</p>
          <p class="mt-0.5 truncate font-mono text-[11px] text-slate-500 dark:text-slate-500">{{ artifact.path }}</p>
        </div>
      </div>
      <div class="flex shrink-0 items-center gap-1">
        <button
          v-if="previewable"
          type="button"
          data-testid="inline-artifact-preview"
          :aria-label="`预览${artifact.title}`"
          :title="`预览${artifact.title}`"
          class="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-slate-500 transition hover:bg-white/80 hover:text-bjut-blue dark:text-slate-400 dark:hover:bg-white/8 dark:hover:text-cyan-200"
          @click="togglePreview"
        >
          <EyeIcon class="h-3.5 w-3.5" />
        </button>
        <button
          v-if="!actionsDisabled"
          type="button"
          data-testid="inline-artifact-open"
          :aria-label="`打开${artifact.title}`"
          :title="`打开${artifact.title}`"
          class="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-slate-500 transition hover:bg-white/80 hover:text-bjut-blue dark:text-slate-400 dark:hover:bg-white/8 dark:hover:text-cyan-200"
          :disabled="!sessionId"
          @click="openArtifact"
        >
          <BoxArrowUpRightIcon class="h-3.5 w-3.5" />
        </button>
      </div>
    </div>

    <div v-if="isImagePreview" class="mt-2 max-h-64 overflow-auto">
      <img :src="contentUrl" :alt="artifact.title" class="max-h-64 max-w-full rounded-md object-contain" />
    </div>
    <iframe
      v-else-if="isHtmlPreview"
      :src="contentUrl"
      title="artifact preview"
      sandbox="allow-scripts allow-same-origin"
      class="mt-2 h-64 w-full rounded-md border border-slate-200/70 bg-white dark:border-white/10"
    ></iframe>
    <div
      v-else-if="isMarkdownPreview"
      class="message-markdown message-markdown--assistant-theme mt-2 max-h-56 overflow-auto rounded-md bg-white/72 px-2.5 py-2 dark:bg-black/20"
      v-html="renderedPreviewText()"
    ></div>
    <ArtifactTablePreview
      v-else-if="isTablePreview && tablePreview"
      class="mt-2"
      :preview="tablePreview"
      :compact="true"
      :max-rows="INLINE_TABLE_PREVIEW_MAX_ROWS"
    />
    <pre v-else-if="isTextPreview" class="mt-2 max-h-56 overflow-auto rounded-md bg-white/72 px-2.5 py-2 font-mono text-[11px] leading-5 text-slate-600 dark:bg-black/20 dark:text-slate-300">{{ previewText }}</pre>
    <p v-else-if="previewLoading" class="mt-2 text-[11px] text-slate-400">加载预览...</p>
    <p v-else-if="previewError" class="mt-2 text-[11px] text-slate-400">{{ previewError }}</p>
  </div>
</template>
