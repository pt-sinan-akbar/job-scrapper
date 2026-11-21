<script setup lang="ts">
import { Skeleton } from '@/shared/components/ui/skeleton'

const CARD_COUNT = 3
const JSON_LINE_WIDTHS = ['w-1/3', 'w-3/4', 'w-2/3', 'w-5/6', 'w-1/2', 'w-3/5'] as const
</script>

<template>
  <div
    data-slot="results-skeleton"
    role="status"
    aria-busy="true"
    class="grid min-w-0 items-start gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]"
  >
    <span class="sr-only">Loading results</span>
    <div class="flex min-w-0 flex-col gap-3">
      <div
        v-for="card in CARD_COUNT"
        :key="card"
        class="flex flex-col gap-3 rounded-md border border-line p-4"
      >
        <div class="flex items-start justify-between gap-3">
          <Skeleton class="h-5 w-2/3" />
          <Skeleton class="h-6 w-16 rounded-full" />
        </div>
        <Skeleton class="h-4 w-1/2" />
        <Skeleton class="h-4 w-full" />
        <Skeleton class="h-4 w-4/5" />
      </div>
    </div>
    <div class="hidden flex-col gap-3 rounded-md border border-line p-4 lg:flex">
      <Skeleton v-for="width in JSON_LINE_WIDTHS" :key="width" :class="['h-4', width]" />
    </div>
  </div>
</template>
