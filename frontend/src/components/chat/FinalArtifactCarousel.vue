<script setup lang="ts">
import BoxArrowUpRightIcon from 'bootstrap-icons/icons/box-arrow-up-right.svg'
import EyeIcon from 'bootstrap-icons/icons/eye.svg'
import FileEarmarkIcon from 'bootstrap-icons/icons/file-earmark.svg'
import MapIcon from 'bootstrap-icons/icons/map.svg'
import ImageIcon from 'bootstrap-icons/icons/image.svg'
import TableIcon from 'bootstrap-icons/icons/table.svg'
import BracesIcon from 'bootstrap-icons/icons/braces.svg'
import type { Artifact } from '../../types'
import { canPreviewArtifact } from './artifactPreview'

defineProps<{
  artifacts: Artifact[]
  actionsDisabled?: boolean
}>()

const emit = defineEmits<{
  (e: 'open-artifact', artifact: Artifact): void
  (e: 'preview-artifact', artifact: Artifact): void
}>()

function artifactIcon(artifact: Artifact) {
  if (artifact.display_hint === 'map' || artifact.kind === 'map') return MapIcon
  if (artifact.display_hint === 'image' || artifact.kind === 'image') return ImageIcon
  if (artifact.display_hint === 'table' || artifact.kind === 'table') return TableIcon
  if (artifact.display_hint === 'json' || artifact.kind === 'json') return BracesIcon
  return FileEarmarkIcon
}
</script>

<template>
  <section
    v-if="artifacts.length"
    data-testid="final-artifact-carousel"
    class="mx-auto w-full max-w-5xl px-4 pb-3 pt-5"
  >
    <div class="overflow-x-auto pb-1">
      <div class="flex w-max min-w-full justify-center gap-2 px-1">
        <article
          v-for="artifact in artifacts"
          :key="artifact.id"
          class="group flex min-w-56 max-w-64 shrink-0 items-center gap-2 rounded-lg border border-slate-200/75 bg-white/86 px-2.5 py-2 shadow-sm shadow-slate-900/5 dark:border-white/8 dark:bg-white/[0.045] dark:shadow-none"
        >
          <component :is="artifactIcon(artifact)" class="h-4 w-4 shrink-0 text-bjut-blue dark:text-cyan-300" />
          <div class="min-w-0 flex-1">
            <p class="truncate text-[12px] font-semibold text-slate-800 dark:text-slate-100">{{ artifact.title }}</p>
            <p class="truncate font-mono text-[10px] text-slate-500 dark:text-slate-500">{{ artifact.path }}</p>
          </div>
          <button
            v-if="!actionsDisabled && canPreviewArtifact(artifact)"
            type="button"
            :data-testid="`final-artifact-preview-${artifact.id}`"
            :aria-label="`预览${artifact.title}`"
            :title="`预览${artifact.title}`"
            class="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-slate-500 transition hover:bg-slate-100 hover:text-bjut-blue dark:text-slate-400 dark:hover:bg-white/8 dark:hover:text-cyan-200"
            @click="emit('preview-artifact', artifact)"
          >
            <EyeIcon class="h-3.5 w-3.5" />
          </button>
          <button
            v-if="!actionsDisabled"
            type="button"
            :data-testid="`final-artifact-open-${artifact.id}`"
            :aria-label="`打开${artifact.title}`"
            :title="`打开${artifact.title}`"
            class="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-slate-500 transition hover:bg-slate-100 hover:text-bjut-blue dark:text-slate-400 dark:hover:bg-white/8 dark:hover:text-cyan-200"
            @click="emit('open-artifact', artifact)"
          >
            <BoxArrowUpRightIcon class="h-3.5 w-3.5" />
          </button>
        </article>
      </div>
    </div>
  </section>
</template>
