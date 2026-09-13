<script setup lang="ts">
// Main layout container
</script>

<template>
  <div class="flex h-screen h-dvh w-screen flex-col overflow-hidden bg-gray-50 text-gray-900 dark:bg-zinc-950 dark:text-zinc-100">
    <slot name="header" />
    <div class="flex flex-1 overflow-hidden">
      <slot />
    </div>
  </div>
</template>
