<script setup lang="ts">
defineProps<{
  fields: string[]
  targetId: string
}>()

defineEmits<{
  insert: [token: string]
}>()

function toToken(field: string): string {
  return '{' + field + '}'
}

function toInsertLabel(field: string): string {
  return `Insert ${field}`
}
</script>

<template>
  <div class="flex flex-wrap items-center gap-2" aria-label="Template variables" role="group">
    <button
      v-for="field in fields"
      :key="field"
      type="button"
      data-slot="template-variable"
      :aria-label="toInsertLabel(field)"
      :aria-controls="targetId"
      class="cursor-pointer rounded-md border border-line px-2 py-1 font-mono text-body-sm text-ink-muted outline-none hover:bg-surface-subtle hover:text-ink focus-visible:focus-ring"
      @click="$emit('insert', toToken(field))"
    >
      {{ toToken(field) }}
    </button>
  </div>
</template>
