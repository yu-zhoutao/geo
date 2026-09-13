<script setup lang="ts">
import { Dialog, DialogPanel, DialogTitle, TransitionChild, TransitionRoot } from '@headlessui/vue'
import { nextTick, ref, watch } from 'vue'

const props = defineProps<{
  open: boolean
  title: string
  message: string
  initialValue: string
  confirmLabel?: string
  cancelLabel?: string
}>()

const emit = defineEmits<{
  (e: 'confirm', value: string): void
  (e: 'cancel'): void
}>()

const value = ref(props.initialValue)
const previousFocusedElement = ref<HTMLElement | null>(
  props.open && document.activeElement instanceof HTMLElement ? document.activeElement : null,
)

function handleKeydown(event: KeyboardEvent): void {
  if (event.key === 'Enter') {
    event.preventDefault()
    handleConfirm()
    return
  }
  if (event.key === 'Escape') {
    event.preventDefault()
    emit('cancel')
  }
}

watch(
  () => [props.open, props.initialValue],
  () => {
    value.value = props.initialValue
  },
  { immediate: true },
)

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

function handleConfirm(): void {
  emit('confirm', value.value.trim())
}
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
          <DialogPanel class="relative w-full max-w-sm overflow-hidden rounded-3xl border border-white/70 bg-white/96 p-6 shadow-2xl shadow-slate-900/15 dark:border-white/10 dark:bg-zinc-950/94 dark:shadow-black/40" @keydown="handleKeydown">
            <div class="mb-5 space-y-2">
              <DialogTitle class="text-base font-semibold text-slate-900 dark:text-white">{{ title }}</DialogTitle>
              <p class="text-sm leading-6 text-slate-500 dark:text-slate-400">{{ message }}</p>
            </div>

            <input
              data-testid="rename-session-dialog-input"
              v-model="value"
              class="mb-5 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-bjut-blue dark:border-white/10 dark:bg-zinc-900 dark:text-white"
              type="text"
               @keydown="handleKeydown"
            >

            <div class="flex justify-end gap-2">
              <button
                data-testid="cancel-rename-session"
                class="rounded-full border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 transition hover:border-slate-300 hover:bg-slate-50 dark:border-white/10 dark:text-slate-300 dark:hover:bg-white/5"
                type="button"
                 @click="emit('cancel')"
              >
                {{ cancelLabel ?? '取消' }}
              </button>
              <button
                data-testid="confirm-rename-session"
                class="rounded-full bg-bjut-blue px-4 py-2 text-sm font-medium text-white transition hover:bg-bjut-blue-hover"
                type="button"
                @click="handleConfirm"
              >
                {{ confirmLabel ?? '保存名称' }}
              </button>
            </div>
          </DialogPanel>
        </TransitionChild>
      </div>
    </Dialog>
  </TransitionRoot>
</template>
