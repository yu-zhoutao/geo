<script setup lang="ts">
import { Menu, MenuButton, MenuItem, MenuItems, TransitionRoot } from '@headlessui/vue'
import ThreeDotsIcon from 'bootstrap-icons/icons/three-dots.svg'
import PencilIcon from 'bootstrap-icons/icons/pencil.svg'
import Trash3Icon from 'bootstrap-icons/icons/trash3.svg'
import DownloadIcon from 'bootstrap-icons/icons/download.svg'

const props = defineProps<{
  sessionId: string
  align?: 'left' | 'right'
  buttonLabel?: string
  testIdPrefix?: string
  readOnly?: boolean
}>()

const emit = defineEmits<{
  (e: 'rename', sessionId: string): void
  (e: 'delete', sessionId: string): void
  (e: 'export', sessionId: string): void
}>()

function handleRename(): void {
  emit('rename', props.sessionId)
}

function handleDelete(): void {
  emit('delete', props.sessionId)
}

function handleExport(): void {
  emit('export', props.sessionId)
}
</script>

<template>
  <Menu v-slot="{ open }" as="div" class="relative">
    <MenuButton
      :data-testid="`${testIdPrefix ?? 'session-actions'}-${sessionId}`"
      class="inline-flex h-8 w-8 items-center justify-center rounded-full text-slate-400 transition hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-white/6 dark:hover:text-white"
      :title="buttonLabel ?? '会话操作'"
      :aria-label="buttonLabel ?? '会话操作'"
      @click.stop
    >
      <ThreeDotsIcon class="h-4 w-4" />
    </MenuButton>

    <TransitionRoot
      :show="open"
      as="template"
      enter="transition duration-150 ease-out"
      enter-from="scale-95 opacity-0"
      enter-to="scale-100 opacity-100"
      leave="transition duration-100 ease-in"
      leave-from="scale-100 opacity-100"
      leave-to="scale-95 opacity-0"
    >
      <MenuItems
        :class="align === 'left' ? 'left-0' : 'right-0'"
        class="absolute top-10 z-[80] min-w-36 overflow-hidden rounded-2xl border border-slate-200/80 bg-white/96 p-1 shadow-xl shadow-slate-900/10 backdrop-blur focus:outline-none dark:border-white/10 dark:bg-zinc-950/96 dark:shadow-black/30"
      >
        <MenuItem v-slot="{ active }">
          <button
            :data-testid="`menu-export-${sessionId}`"
            :class="active ? 'bg-slate-100 dark:bg-white/6' : ''"
            class="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-sm text-slate-700 transition dark:text-slate-200"
            type="button"
            @click.stop="handleExport"
          >
            <DownloadIcon class="h-3.5 w-3.5" />
            <span>导出记录</span>
          </button>
        </MenuItem>

        <MenuItem v-if="!readOnly" v-slot="{ active }">
          <button
            :data-testid="`menu-rename-${sessionId}`"
            :class="active ? 'bg-slate-100 dark:bg-white/6' : ''"
            class="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-sm text-slate-700 transition dark:text-slate-200"
            type="button"
            @click.stop="handleRename"
          >
            <PencilIcon class="h-3.5 w-3.5" />
            <span>重命名</span>
          </button>
        </MenuItem>

        <MenuItem v-slot="{ active }">
          <button
            :data-testid="`menu-delete-${sessionId}`"
            :class="active ? 'bg-rose-50 dark:bg-rose-500/10' : ''"
            class="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-sm text-rose-600 transition dark:text-rose-300"
            type="button"
            @click.stop="handleDelete"
          >
            <Trash3Icon class="h-3.5 w-3.5" />
            <span>删除</span>
          </button>
        </MenuItem>
      </MenuItems>
    </TransitionRoot>
  </Menu>
</template>
