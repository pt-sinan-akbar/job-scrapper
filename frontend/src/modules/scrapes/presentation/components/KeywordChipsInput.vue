<script setup lang="ts">
import { X } from '@lucide/vue'
import { computed, ref } from 'vue'
import {
  addKeywordChips,
  commitKeywordText,
} from '@/modules/scrapes/presentation/components/keywordChips'

const EMPTY_PLACEHOLDER = 'data analyst, python'
const NEXT_PLACEHOLDER = 'Add keyword'

const props = defineProps<{
  id: string
  maxChips: number
  describedBy?: string
}>()

const chips = defineModel<string[]>('chips', { required: true })
const text = defineModel<string>('text', { required: true })

const keywordInput = ref<HTMLInputElement | null>(null)
const placeholder = computed(() =>
  chips.value.length === 0 ? EMPTY_PLACEHOLDER : NEXT_PLACEHOLDER,
)

function readKeywordKey(event: KeyboardEvent): void {
  if (event.key === 'Enter' || event.key === ',') {
    event.preventDefault()
    addTypedKeyword(event)
    return
  }
  if (event.key === 'Backspace' && text.value === '') {
    removeLastChip()
  }
}

function addPastedKeywords(event: ClipboardEvent): void {
  const pastedText = event.clipboardData?.getData('text') ?? ''
  if (!pastedText.includes(',')) {
    return
  }
  event.preventDefault()
  chips.value = addKeywordChips(chips.value, pastedText, props.maxChips)
}

function addTypedKeyword(event: KeyboardEvent): void {
  if (event.isComposing) {
    return
  }
  const committedDraft = commitKeywordText({ chips: chips.value, text: text.value }, props.maxChips)
  chips.value = committedDraft.chips
  text.value = committedDraft.text
}

function removeLastChip(): void {
  if (chips.value.length === 0) {
    return
  }
  chips.value = chips.value.slice(0, -1)
}

function removeChip(chipIndex: number): void {
  chips.value = chips.value.filter((_, index) => index !== chipIndex)
  focusKeywordInput()
}

function focusKeywordInput(): void {
  keywordInput.value?.focus()
}
</script>

<template>
  <div
    data-slot="keyword-chips-input"
    class="flex min-h-10 w-full min-w-0 flex-wrap items-center gap-2 rounded-md border border-line-strong bg-surface px-2 py-1.5 text-body text-ink transition-colors duration-150 focus-within:border-accent focus-within:focus-ring"
    @click.self="focusKeywordInput"
  >
    <ul v-if="chips.length > 0" aria-label="Keywords" class="flex min-w-0 flex-wrap gap-2">
      <li
        v-for="(chip, index) in chips"
        :key="chip"
        data-slot="keyword-chip"
        class="inline-flex h-7 min-w-0 items-center gap-1 rounded-full border border-transparent bg-accent-soft pr-1 pl-3 text-body-sm font-medium text-accent"
      >
        <span class="truncate">{{ chip }}</span>
        <button
          type="button"
          :aria-label="`Remove ${chip}`"
          class="flex size-5 shrink-0 cursor-pointer items-center justify-center rounded-full text-current outline-none transition-colors duration-150 hover:bg-line focus-visible:focus-ring"
          @click="removeChip(index)"
        >
          <X class="size-3.5" aria-hidden="true" />
        </button>
      </li>
    </ul>
    <input
      :id="id"
      ref="keywordInput"
      v-model="text"
      type="text"
      enterkeyhint="enter"
      autocomplete="off"
      :placeholder="placeholder"
      :aria-describedby="describedBy"
      class="h-7 min-w-24 flex-1 bg-transparent px-1 text-body text-ink outline-none placeholder:text-ink-muted"
      @keydown="readKeywordKey"
      @paste="addPastedKeywords"
    />
  </div>
</template>
