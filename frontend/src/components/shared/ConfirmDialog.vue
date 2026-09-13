<script setup lang="ts">
import { Dialog, DialogPanel, DialogTitle, TransitionChild, TransitionRoot } from '@headlessui/vue'
import { nextTick, ref, watch } from 'vue'

const props = defineProps<{
  open: boolean
  title: string
  message: string
  confirmLabel?: string
  cancelLabel?: string
}>()

const emit = defineEmits<{
  (e: 'confirm'): void
  (e: 'cancel'): void
}>()

const previousFocusedElement = ref<HTMLElement | null>(
  props.open && document.activeElement instanceof HTMLElement ? document.activeElement : null,
)

function handleEscape(event: KeyboardEvent): void {
  if (event.key !== 'Escape') {
    return
  }
  event.preventDefault()
  emit('cancel')
}

watch(
  () => props.open,
  (open, wasOpen) => {
    if (open && !wasOpen) {
      previousFocusedElement.value = document.activeElement instanceof HTMLElement ? document.activeElement : null
      return
    }
    if (!open && wasOpen) {
      const target = previousFocusedElement.value
      if (target?.isConnected) {
        void nextTick(() => target.focus())
      }
    }
  },
)
</script>

<template>
  <TransitionRoot :show="open" as="template" appear>
    <Dialog as="div" class="relative z-50" @close="emit('cancel')">
      <TransitionChild
        as="template"
        enter="transition duration-200 ease-out"
        enter-from="opacity-0"
        enter-to="opacity-100"
        leave="transition duration-150 ease-in"
        leave-from="opacity-100"
        leave-to="opacity-0"
      >
        <div class="fixed inset-0 bg-slate-950/45 backdrop-blur-[2px]" />
      </TransitionChild>

      <div class="fixed inset-0 flex items-center justify-center px-4">
        <TransitionChild
          as="template"
          enter="transition duration-200 ease-out"
          enter-from="translate-y-2 scale-95 opacity-0"
          enter-to="translate-y-0 scale-100 opacity-100"
          leave="transition duration-150 ease-in"
          leave-from="translate-y-0 scale-100 opacity-100"
          leave-to="translate-y-2 scale-95 opacity-0"
        >
          <DialogPanel class="relative w-full max-w-sm overflow-hidden rounded-3xl border border-white/70 bg-white/96 p-6 shadow-2xl shadow-slate-900/15 dark:border-white/10 dark:bg-zinc-950/94 dark:shadow-black/40" @keydown="handleEscape">
            <div class="mb-5 flex items-start gap-3">
              <div class="flex h-11 w-11 items-center justify-center rounded-2xl bg-rose-50 text-rose-500 dark:bg-rose-500/10 dark:text-rose-300">
                <slot name="icon" />
              </div>
              <div class="space-y-1">
                <DialogTitle class="text-base font-semibold text-slate-900 dark:text-white">{{ title }}</DialogTitle>
                <p class="text-sm leading-6 text-slate-500 dark:text-slate-400">{{ message }}</p>
              </div>
            </div>

            <div class="flex justify-end gap-2">
              <button
                data-testid="cancel-delete-session"
                class="rounded-full border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 transition hover:border-slate-300 hover:bg-slate-50 dark:border-white/10 dark:text-slate-300 dark:hover:bg-white/5"
                type="button"
                @click="emit('cancel')"
              >
                {{ cancelLabel ?? '取消' }}
              </button>
              <button
                data-testid="confirm-delete-session"
                class="rounded-full bg-rose-500 px-4 py-2 text-sm font-medium text-white transition hover:bg-rose-600"
                type="button"
                @click="emit('confirm')"
              >
                {{ confirmLabel ?? '确认删除' }}
              </button>
            </div>
          </DialogPanel>
        </TransitionChild>
      </div>
    </Dialog>
  </TransitionRoot>
</template>
