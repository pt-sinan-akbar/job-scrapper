<script setup lang="ts">
defineProps<{ legend: string }>()
</script>

<template>
  <fieldset
    data-slot="site-group"
    class="flex min-w-0 flex-col gap-4 border-0 border-t border-line p-0 pt-6 first-of-type:border-t-0 first-of-type:pt-0"
  >
    <legend class="float-left w-full text-body-sm font-semibold text-ink">{{ legend }}</legend>
    <div class="flex min-w-0 flex-col gap-8">
      <slot />
    </div>
  </fieldset>
</template>
