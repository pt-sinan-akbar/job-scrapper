<script setup lang="ts">
interface Slab {
  id: string
  slabClass: string
  pillClass: string
  rows: readonly (readonly string[])[]
}

const PRODUCT_NAME_ROWS: readonly string[] = ['Job Agent', 'Scraper']

const SLABS: readonly Slab[] = [
  {
    id: 'accent',
    slabClass: 'h-full grow-54 justify-end bg-accent',
    pillClass: 'bg-accent-soft',
    rows: [['w-10'], ['w-24', 'w-12']],
  },
  {
    id: 'tint',
    slabClass: 'h-4/5 grow-27 justify-start bg-accent-soft pt-10 motion-safe:delay-75',
    pillClass: 'bg-accent',
    rows: [
      ['w-16', 'w-8'],
      ['w-10', 'w-24'],
      ['w-30', 'w-10'],
    ],
  },
  {
    id: 'ink',
    slabClass: 'h-full grow-35 justify-end bg-ink motion-safe:delay-150',
    pillClass: 'bg-accent',
    rows: [['w-28', 'w-10']],
  },
]
</script>

<template>
  <aside class="hidden min-w-0 p-4 lg:sticky lg:top-0 lg:block lg:h-dvh">
    <div
      class="relative flex h-full flex-col justify-between overflow-hidden rounded-lg bg-surface-subtle"
    >
      <div
        data-testid="brand-slabs"
        aria-hidden="true"
        class="-mt-4 ml-6 flex h-1/3 max-h-80 min-h-32 w-full items-start gap-4"
      >
        <div
          v-for="slab in SLABS"
          :key="slab.id"
          data-testid="brand-slab"
          :class="[
            'flex min-w-0 basis-0 animate-in flex-col gap-2 overflow-hidden rounded-lg p-6 duration-500 ease-out fill-mode-both fade-in slide-in-from-top-8',
            slab.slabClass,
          ]"
        >
          <div v-for="(row, rowIndex) in slab.rows" :key="rowIndex" class="flex gap-2">
            <span
              v-for="(pillWidth, pillIndex) in row"
              :key="pillIndex"
              :class="['h-4 shrink-0 rounded-full', pillWidth, slab.pillClass]"
            />
          </div>
        </div>
      </div>
      <p data-testid="brand-name" class="p-8 text-display text-ink">
        <span v-for="row in PRODUCT_NAME_ROWS" :key="row" class="block">{{ row }}</span>
      </p>
    </div>
  </aside>
</template>
