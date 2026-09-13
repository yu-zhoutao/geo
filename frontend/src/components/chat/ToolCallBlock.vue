<script setup lang="ts">
import { ref } from 'vue'
import SearchIcon from 'bootstrap-icons/icons/search.svg'
import FunnelIcon from 'bootstrap-icons/icons/funnel.svg'
import GridIcon from 'bootstrap-icons/icons/grid-3x3-gap.svg'
import FileTextIcon from 'bootstrap-icons/icons/file-earmark-text.svg'
import WrenchIcon from 'bootstrap-icons/icons/wrench.svg'
import ListTaskIcon from 'bootstrap-icons/icons/list-task.svg'
import DiagramIcon from 'bootstrap-icons/icons/diagram-3.svg'
import QuestionIcon from 'bootstrap-icons/icons/question-circle.svg'
import JournalCodeIcon from 'bootstrap-icons/icons/journal-code.svg'
import TerminalIcon from 'bootstrap-icons/icons/terminal.svg'
import GearIcon from 'bootstrap-icons/icons/gear.svg'
import type { ChatMessagePart } from '../../types'
import { resolveToolIdentityForState } from '../../shared/toolIdentity'

const props = defineProps<{
  part: ChatMessagePart
}>()

const isExpanded = ref(false)

function toggle() {
  isExpanded.value = !isExpanded.value
}

function toolTitle(): string {
  return toolMeta().label
}

function toolPreview(): string | null {
  if (typeof props.part.state?.input === 'object' && props.part.state?.input && 'command' in props.part.state.input) {
    return String(props.part.state.input.command)
  }
  if (typeof props.part.state?.input === 'object' && props.part.state?.input) {
    return JSON.stringify(props.part.state.input)
  }
  return null
}

function toolOutput(): string {
  if (typeof props.part.state?.output === 'string') {
    return props.part.state.output
  }
  return ''
}

function toolMeta() {
  return resolveToolIdentityForState(props.part.tool, props.part.state)
}

function familyIcon() {
  const icon = toolMeta().icon
  if (icon === 'search') return SearchIcon
  if (icon === 'funnel') return FunnelIcon
  if (icon === 'grid') return GridIcon
  if (icon === 'file-text') return FileTextIcon
  if (icon === 'list-task') return ListTaskIcon
  if (icon === 'diagram') return DiagramIcon
  if (icon === 'question') return QuestionIcon
  if (icon === 'journal-code') return JournalCodeIcon
  if (icon === 'terminal') return TerminalIcon
  if (icon === 'gear') return GearIcon
  return WrenchIcon
}

</script>

<template>
  <div class="my-1.5 overflow-hidden rounded-lg border border-gray-200 bg-gray-50 shadow-sm dark:border-white/10 dark:bg-slate-900/50 dark:shadow-none">
    <button 
      data-testid="toggle-tool-details"
      class="flex w-full items-center justify-between px-2.5 py-1.5 text-left transition hover:bg-gray-100 dark:hover:bg-white/5"
      @click="toggle"
    >
      <div class="flex items-center gap-2 overflow-hidden">
        <component :is="familyIcon()" data-testid="tool-family-icon" class="h-3.5 w-3.5 shrink-0 text-bjut-blue dark:text-cyan-400" />
        <span class="truncate font-mono text-xs text-gray-700 dark:text-slate-300">{{ toolTitle() }}</span>
      </div>
      <svg 
        class="h-3.5 w-3.5 text-gray-400 transition-transform duration-200 dark:text-slate-500"
        :class="{ 'rotate-180': isExpanded }"
        fill="none" viewBox="0 0 24 24" stroke="currentColor"
      >
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
      </svg>
    </button>
    
    <div v-if="isExpanded" class="border-t border-gray-200 bg-white p-2.5 dark:border-white/5 dark:bg-slate-950">
      <div class="mb-2 min-w-0 space-y-1">
        <p v-if="toolPreview()" class="text-[11px] text-gray-500 dark:text-slate-400 font-mono truncate">{{ toolPreview() }}</p>
      </div>
      <div v-if="toolPreview() && toolOutput()" data-testid="tool-input-output-divider" class="mb-2 border-t border-gray-200 dark:border-white/10"></div>
      <pre class="text-[11px] text-gray-600 dark:text-slate-400 whitespace-pre-wrap font-mono overflow-x-auto">{{ toolOutput() }}</pre>
    </div>
  </div>
</template>
