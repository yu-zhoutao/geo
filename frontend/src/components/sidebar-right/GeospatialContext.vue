<script setup lang="ts">
import { computed, ref } from 'vue'
import BoxArrowUpRightIcon from 'bootstrap-icons/icons/box-arrow-up-right.svg'
import ChevronDownIcon from 'bootstrap-icons/icons/chevron-down.svg'
import EyeIcon from 'bootstrap-icons/icons/eye.svg'
import FileEarmarkIcon from 'bootstrap-icons/icons/file-earmark.svg'
import MapIcon from 'bootstrap-icons/icons/map.svg'
import ImageIcon from 'bootstrap-icons/icons/image.svg'
import TableIcon from 'bootstrap-icons/icons/table.svg'
import BracesIcon from 'bootstrap-icons/icons/braces.svg'
import type { Artifact, TimelineEntry } from '../../types'
import { artifactAnalysisTypeLabel, evidenceAnalysisTypeLabel } from '../../shared/analysisTypes'
import { canPreviewArtifact } from '../chat/artifactPreview'

const props = withDefaults(defineProps<{
  artifacts: Artifact[]
  timelineEntries: TimelineEntry[]
  artifactActionsDisabled?: boolean
}>(), {
  timelineEntries: () => [],
})

const emit = defineEmits<{
  (e: 'open-artifact', artifact: Artifact): void
  (e: 'preview-artifact', artifact: Artifact): void
}>()

const expandedEvidenceIds = ref<Set<string>>(new Set())
const evidenceEntries = computed(() => (
  props.timelineEntries
    .filter((entry) => entry.kind === 'evidence')
    .slice()
    .sort((left, right) => Date.parse(right.created_at) - Date.parse(left.created_at))
))

const artifactKindLabels: Record<NonNullable<Artifact['kind']>, string> = {
  manifest: '清单',
  map: '地图',
  raster: '栅格',
  report: '报告',
  metadata: '参数',
  prepared: '预处理',
  verification: '验证',
  table: '表格',
  dataset: '数据',
  image: '图像',
  html: 'HTML',
  json: 'JSON',
  text: '文本',
  archive: '归档',
  other: '文件',
}

const evidenceTypeLabels: Record<string, string> = {
  dataset_profile: '数据画像',
  verification_fact: '验证事实',
  parameter_snapshot: '参数快照',
  claim_trace: '声明追踪',
}

function artifactIcon(artifact: Artifact) {
  if (artifact.display_hint === 'map' || artifact.kind === 'map') return MapIcon
  if (artifact.display_hint === 'image' || artifact.kind === 'image') return ImageIcon
  if (artifact.display_hint === 'table' || artifact.kind === 'table') return TableIcon
  if (artifact.display_hint === 'json' || artifact.kind === 'json') return BracesIcon
  return FileEarmarkIcon
}

function evidenceLabel(entry: TimelineEntry): string {
  return evidenceTypeLabels[entry.record_type ?? ''] ?? '证据'
}

function artifactTaskFamilyLabel(artifact: Artifact): string | null {
  return artifactAnalysisTypeLabel(artifact)
}

function evidenceTaskFamilyLabel(entry: TimelineEntry): string | null {
  return evidenceAnalysisTypeLabel(entry)
}

function toggleEvidence(entryId: string): void {
  const next = new Set(expandedEvidenceIds.value)
  if (next.has(entryId)) {
    next.delete(entryId)
  } else {
    next.add(entryId)
  }
  expandedEvidenceIds.value = next
}

function isEvidenceExpanded(entryId: string): boolean {
  return expandedEvidenceIds.value.has(entryId)
}

function hasPayload(value: Record<string, unknown> | undefined): boolean {
  return Boolean(value && Object.keys(value).length)
}

function hasEvidenceDetails(entry: TimelineEntry): boolean {
  return hasPayload(entry.data)
}

function formatEvidencePayload(value: Record<string, unknown> | undefined): string {
  if (!value) {
    return ''
  }
  return JSON.stringify(value, null, 2)
}
</script>

<template>
  <section class="space-y-4">
    <div class="space-y-2">
      <h3 class="text-xs font-medium text-gray-500 dark:text-gray-400">工作区产物</h3>
      <ul v-if="artifacts.length" class="space-y-1.5">
        <li
          v-for="artifact in artifacts"
          :key="artifact.id"
          :data-testid="`artifact-card-${artifact.id}`"
          class="group flex min-w-0 items-start gap-2 rounded-lg border border-slate-200/70 bg-white px-2.5 py-2 text-xs shadow-sm dark:border-white/8 dark:bg-zinc-900/50"
        >
          <component :is="artifactIcon(artifact)" class="mt-0.5 h-4 w-4 shrink-0 text-bjut-blue dark:text-cyan-300" />
          <div class="min-w-0 flex-1">
            <div class="flex min-w-0 items-start gap-2">
              <p class="min-w-0 flex-1 truncate text-[12px] font-semibold leading-5 text-slate-800 dark:text-slate-100">{{ artifact.title }}</p>
              <span
                v-if="artifactTaskFamilyLabel(artifact)"
                :data-testid="`artifact-analysis-type-${artifact.id}`"
                class="shrink-0 rounded-full bg-cyan-50 px-1.5 py-0.5 text-[9px] font-semibold text-cyan-700 dark:bg-cyan-400/10 dark:text-cyan-200"
              >
                {{ artifactTaskFamilyLabel(artifact) }}
              </span>
              <span
                v-if="artifact.kind"
                :data-testid="`artifact-kind-${artifact.id}`"
                class="shrink-0 rounded-full bg-slate-100 px-1.5 py-0.5 text-[9px] font-semibold text-slate-600 dark:bg-white/8 dark:text-slate-300"
              >
                {{ artifactKindLabels[artifact.kind] }}
              </span>
            </div>
            <p v-if="artifact.description" class="mt-0.5 max-h-8 overflow-hidden text-[11px] leading-4 text-slate-500 dark:text-slate-400">{{ artifact.description }}</p>
            <p class="mt-0.5 truncate font-mono text-[10px] text-slate-500 dark:text-slate-500">{{ artifact.path }}</p>
          </div>
          <div class="flex shrink-0 items-center gap-1">
            <button
              v-if="!artifactActionsDisabled && canPreviewArtifact(artifact)"
              type="button"
              :data-testid="`sidebar-artifact-preview-${artifact.id}`"
              :aria-label="`预览${artifact.title}`"
              :title="`预览${artifact.title}`"
              class="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-slate-500 transition hover:bg-slate-100 hover:text-bjut-blue dark:text-slate-400 dark:hover:bg-white/8 dark:hover:text-cyan-200"
              @click="emit('preview-artifact', artifact)"
            >
              <EyeIcon class="h-3.5 w-3.5" />
            </button>
            <button
              v-if="!artifactActionsDisabled"
              type="button"
              :data-testid="`sidebar-artifact-open-${artifact.id}`"
              :aria-label="`打开${artifact.title}`"
              :title="`打开${artifact.title}`"
              class="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-slate-500 transition hover:bg-slate-100 hover:text-bjut-blue dark:text-slate-400 dark:hover:bg-white/8 dark:hover:text-cyan-200"
              @click="emit('open-artifact', artifact)"
            >
              <BoxArrowUpRightIcon class="h-3.5 w-3.5" />
            </button>
          </div>
        </li>
      </ul>
      <div v-else class="rounded-2xl border border-dashed border-slate-200 bg-white/60 p-4 text-sm italic text-slate-500 dark:border-white/10 dark:bg-white/[0.02] dark:text-slate-400">
        暂无生成产物。
      </div>
    </div>

    <div class="space-y-2">
      <h3 class="text-xs font-medium text-gray-500 dark:text-gray-400">地理任务摘要</h3>
      <div v-if="!evidenceEntries.length" class="rounded-2xl border border-dashed border-slate-200 bg-white/60 p-4 text-sm italic text-slate-500 dark:border-white/10 dark:bg-white/[0.02] dark:text-slate-400">
        暂无地理任务摘要。
      </div>

      <ol v-if="evidenceEntries.length" data-testid="evidence-timeline" class="mt-2 space-y-1.5">
        <li
          v-for="entry in evidenceEntries"
          :key="entry.id"
          :data-testid="`evidence-card-${entry.id}`"
          class="rounded-lg border border-slate-200/70 bg-white px-2.5 py-2 text-xs shadow-sm dark:border-white/8 dark:bg-zinc-900/50"
        >
          <button
            type="button"
            :data-testid="`evidence-toggle-${entry.id}`"
            class="flex w-full min-w-0 items-start gap-2 text-left disabled:cursor-default"
            :aria-expanded="hasEvidenceDetails(entry) ? isEvidenceExpanded(entry.id) : undefined"
            :disabled="!hasEvidenceDetails(entry)"
            @click="toggleEvidence(entry.id)"
          >
            <span class="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-cyan-400"></span>
            <div class="min-w-0 flex-1">
              <div class="flex min-w-0 items-start gap-2">
                <p class="min-w-0 flex-1 truncate text-[12px] font-semibold leading-5 text-slate-800 dark:text-slate-100">{{ entry.title ?? entry.text }}</p>
                <span
                  v-if="evidenceTaskFamilyLabel(entry)"
                  :data-testid="`evidence-analysis-type-${entry.id}`"
                  class="shrink-0 rounded-full bg-cyan-50 px-1.5 py-0.5 text-[9px] font-semibold text-cyan-700 dark:bg-cyan-400/10 dark:text-cyan-200"
                >
                  {{ evidenceTaskFamilyLabel(entry) }}
                </span>
                <span
                  :data-testid="`evidence-kind-${entry.id}`"
                  class="shrink-0 rounded-full bg-slate-100 px-1.5 py-0.5 text-[9px] font-semibold text-slate-600 dark:bg-white/8 dark:text-slate-300"
                >
                  {{ evidenceLabel(entry) }}
                </span>
              </div>
              <p v-if="entry.detail" class="mt-0.5 max-h-8 overflow-hidden text-[11px] leading-4 text-slate-500 dark:text-slate-400">{{ entry.detail }}</p>
            </div>
            <ChevronDownIcon
              v-if="hasEvidenceDetails(entry)"
              class="mt-1 h-3.5 w-3.5 shrink-0 text-slate-400 transition-transform dark:text-slate-500"
              :class="isEvidenceExpanded(entry.id) ? 'rotate-180' : ''"
            />
          </button>

          <div
            v-if="isEvidenceExpanded(entry.id) && hasEvidenceDetails(entry)"
            :data-testid="`evidence-details-${entry.id}`"
            class="mt-2 border-t border-slate-200/70 pt-2 dark:border-white/8"
          >
            <pre class="max-h-32 overflow-auto rounded-md bg-slate-50 px-2 py-1.5 font-mono text-[10px] leading-4 text-slate-600 dark:bg-black/20 dark:text-slate-300">{{ formatEvidencePayload(entry.data) }}</pre>
          </div>
        </li>
      </ol>
    </div>
  </section>
</template>
