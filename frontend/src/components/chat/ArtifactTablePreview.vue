<script setup lang="ts">
import type { DelimitedTablePreview } from './tablePreview'

defineProps<{
  preview: DelimitedTablePreview
  compact?: boolean
  maxRows: number
}>()
</script>

<template>
  <div
    data-testid="artifact-table-preview"
    :class="[
      'overflow-auto rounded-lg border border-slate-200 bg-white text-left shadow-inner shadow-slate-950/[0.025] dark:border-white/10 dark:bg-black/18',
      compact ? 'max-h-56' : 'max-h-[36rem]',
    ]"
  >
    <table v-if="preview.headers.length" class="min-w-full border-separate border-spacing-0 text-[12px] leading-5 text-slate-700 dark:text-slate-200">
      <thead class="sticky top-0 z-10 bg-slate-50 dark:bg-zinc-900">
        <tr>
          <th
            v-for="(header, headerIndex) in preview.headers"
            :key="headerIndex"
            class="border-b border-slate-200 px-3 py-2 font-semibold text-slate-900 first:rounded-tl-lg last:rounded-tr-lg dark:border-white/10 dark:text-slate-100"
          >
            {{ header }}
          </th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(row, rowIndex) in preview.rows" :key="rowIndex" class="odd:bg-white even:bg-slate-50/70 dark:odd:bg-transparent dark:even:bg-white/[0.035]">
          <td
            v-for="(cell, cellIndex) in row"
            :key="cellIndex"
            class="max-w-72 whitespace-nowrap border-b border-slate-100 px-3 py-1.5 font-mono text-[11px] text-slate-600 dark:border-white/[0.06] dark:text-slate-300"
          >
            {{ cell }}
          </td>
        </tr>
      </tbody>
    </table>
    <div v-else class="px-3 py-2 text-xs text-slate-500 dark:text-slate-400">没有可预览的表格数据。</div>
    <div
      v-if="preview.truncated"
      class="sticky bottom-0 border-t border-slate-200 bg-white/95 px-3 py-1.5 text-[11px] text-slate-500 backdrop-blur dark:border-white/10 dark:bg-zinc-950/95 dark:text-slate-400"
    >
      仅显示前 {{ maxRows }} 行。
    </div>
  </div>
</template>
