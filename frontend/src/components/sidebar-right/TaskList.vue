<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import type { PlanEntry, PlanGroup } from '../../types'

const props = defineProps<{
  planGroups: PlanGroup[]
  planEntries: PlanEntry[]
}>()

const statusLabels: Record<PlanEntry['status'], string> = {
  completed: '已完成',
  in_progress: '进行中',
  pending: '待开始',
  blocked: '已阻塞',
}

const visibleGroups = computed<PlanGroup[]>(() => {
  if (props.planGroups.length) {
    return props.planGroups
  }
  if (!props.planEntries.length) {
    return []
  }
  return [
    {
      id: 'runtime-plan',
      agent: 'runtime-plan',
      label: '执行计划',
      updated_at: '',
      entries: props.planEntries,
    },
  ]
})

const activeGroupId = ref('')

watch(
  visibleGroups,
  (groups) => {
    if (!groups.length) {
      activeGroupId.value = ''
      return
    }
    if (!groups.some((group) => group.id === activeGroupId.value)) {
      activeGroupId.value = groups[0].id
    }
  },
  { immediate: true },
)

const activeGroup = computed<PlanGroup | null>(() => {
  return visibleGroups.value.find((group) => group.id === activeGroupId.value) ?? visibleGroups.value[0] ?? null
})
</script>

<template>
  <section class="space-y-3">
    <div>
      <h3 class="text-xs font-medium text-gray-500 dark:text-gray-400">执行计划</h3>
    </div>

    <div v-if="visibleGroups.length > 1" data-testid="plan-group-tabs" class="flex gap-1 overflow-x-auto rounded-lg bg-slate-100 p-1 dark:bg-white/5">
      <button
        v-for="group in visibleGroups"
        :key="group.id"
        type="button"
        :data-testid="`plan-group-tab-${group.agent}`"
        class="shrink-0 rounded-md px-2 py-1 text-xs font-medium transition-colors"
        :class="group.id === activeGroup?.id ? 'bg-white text-slate-900 shadow-sm dark:bg-zinc-800 dark:text-slate-100' : 'text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-100'"
        @click="activeGroupId = group.id"
      >
        {{ group.label }}
      </button>
    </div>

    <ul v-if="activeGroup?.entries.length" class="space-y-1.5">
      <li
        v-for="entry in activeGroup.entries"
        :key="entry.id"
        :data-testid="`plan-card-${entry.id}`"
        class="flex min-w-0 items-start gap-2 rounded-lg border border-slate-200/70 bg-white px-2.5 py-2 text-xs shadow-sm dark:border-white/8 dark:bg-zinc-900/50"
      >
        <div class="mt-0.5 shrink-0">
          <div v-if="entry.status === 'completed'" class="h-4 w-4 rounded-full bg-emerald-100 border border-emerald-500/50 flex items-center justify-center dark:bg-emerald-500/20">
            <div class="h-2 w-2 rounded-full bg-emerald-500 dark:bg-emerald-400"></div>
          </div>
          <div v-else-if="entry.status === 'in_progress'" class="h-4 w-4 rounded-full border-2 border-bjut-blue border-t-transparent animate-spin dark:border-cyan-400"></div>
          <div v-else-if="entry.status === 'blocked'" class="h-4 w-4 rounded-full bg-rose-100 border border-rose-500/60 flex items-center justify-center dark:bg-rose-500/15">
            <div class="h-1.5 w-1.5 rounded-full bg-rose-500 dark:bg-rose-400"></div>
          </div>
          <div v-else class="h-4 w-4 rounded-full border border-gray-300 dark:border-slate-600"></div>
        </div>

        <div class="min-w-0 flex-1">
          <div class="flex min-w-0 items-start gap-2">
            <p class="min-w-0 flex-1 text-[12px] font-semibold leading-5 text-slate-800 dark:text-slate-100">{{ entry.label }}</p>
            <span
              :data-testid="`plan-status-${entry.id}`"
              class="shrink-0 rounded-full px-1.5 py-0.5 text-[9px] font-semibold"
              :class="{
                'bg-emerald-50 text-emerald-600 dark:bg-emerald-500/10 dark:text-emerald-300': entry.status === 'completed',
                'bg-cyan-50 text-bjut-blue dark:bg-cyan-400/10 dark:text-cyan-300': entry.status === 'in_progress',
                'bg-rose-50 text-rose-600 dark:bg-rose-500/10 dark:text-rose-300': entry.status === 'blocked',
                'bg-slate-100 text-slate-500 dark:bg-white/8 dark:text-slate-400': entry.status === 'pending'
              }">
              {{ statusLabels[entry.status] }}
            </span>
          </div>
        </div>
      </li>
    </ul>
    <div v-else class="rounded-2xl border border-dashed border-slate-200 bg-white/60 p-4 text-sm italic text-slate-500 dark:border-white/10 dark:bg-white/[0.02] dark:text-slate-400">
      暂无执行计划。
    </div>
  </section>
</template>
