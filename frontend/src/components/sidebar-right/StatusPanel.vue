<script setup lang="ts">
import { computed } from 'vue'
import { Switch, SwitchGroup, SwitchLabel } from '@headlessui/vue'

import type { Artifact, PlanEntry, PlanGroup, TimelineEntry } from '../../types'
import TaskList from './TaskList.vue'
import GeospatialContext from './GeospatialContext.vue'

const props = defineProps<{
  planGroups: PlanGroup[]
  planEntries: PlanEntry[]
  timelineEntries: TimelineEntry[]
  artifacts: Artifact[]
  showThinking?: boolean
  artifactActionsDisabled?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:showThinking', value: boolean): void
  (e: 'open-artifact', artifact: Artifact): void
  (e: 'preview-artifact', artifact: Artifact): void
}>()

const showThinkingModel = computed({
  get: (): boolean => props.showThinking ?? false,
  set: (value: boolean): void => emit('update:showThinking', value),
})
</script>

<template>
  <aside class="relative z-30 flex min-h-0 w-80 shrink-0 flex-col border-l border-slate-200/60 bg-white/75 dark:border-white/8 dark:bg-zinc-950/70">
    <div class="flex-1 overflow-y-auto px-4 py-4 space-y-5">
      <TaskList :planGroups="planGroups" :planEntries="planEntries" />

      <GeospatialContext
        :artifacts="artifacts"
        :timelineEntries="timelineEntries"
        :artifactActionsDisabled="artifactActionsDisabled ?? false"
        @open-artifact="emit('open-artifact', $event)"
        @preview-artifact="emit('preview-artifact', $event)"
      />

      <section class="space-y-3 border-t border-slate-200/70 pt-4 dark:border-white/8">
        <h3 class="text-xs font-medium text-gray-500 dark:text-gray-400">设置</h3>

        <SwitchGroup as="div" class="flex items-center justify-between gap-3 py-1 text-sm text-slate-700 dark:text-slate-200">
          <SwitchLabel as="span">显示思考内容</SwitchLabel>
          <Switch
            v-model="showThinkingModel"
            data-testid="sidebar-setting-show-thinking"
            class="relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-bjut-blue/35 focus-visible:ring-offset-2 focus-visible:ring-offset-white dark:focus-visible:ring-cyan-400/40 dark:focus-visible:ring-offset-zinc-950"
            :class="showThinkingModel ? 'bg-bjut-blue/70 dark:bg-cyan-500/70' : 'bg-slate-300 dark:bg-white/15'"
          >
            <span
              aria-hidden="true"
              class="inline-block h-4 w-4 rounded-full bg-white shadow-[0_1px_2px_rgba(15,23,42,0.18)] ring-1 ring-black/5 transition-transform duration-150"
              :class="showThinkingModel ? 'translate-x-4' : 'translate-x-0.5'"
            />
          </Switch>
        </SwitchGroup>
      </section>
    </div>
  </aside>
</template>
