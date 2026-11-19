<script setup lang="ts">
import { computed, onMounted, ref, useId, watch } from 'vue'
import { useResizeObserver } from '@vueuse/core'
import { cn } from '@/shared/utils/cn'
import { markdownToPlainText, renderMarkdown } from '@/shared/utils/markdown'

interface RenderedMarkdown {
  source: string
  html: string
}

const CLAMP_TOLERANCE_PX = 1

const props = defineProps<{ description: string }>()

const contentId = useId()
const textElement = ref<HTMLElement | null>(null)
const isExpanded = ref(false)
const isClamped = ref(false)
const hasFailed = ref(false)
const rendered = ref<RenderedMarkdown | null>(null)

const plainText = computed(() => markdownToPlainText(props.description))
const isToggleShown = computed(() => isExpanded.value || isClamped.value)
const html = computed(() =>
  rendered.value?.source === props.description ? rendered.value.html : null,
)
const isHtmlShown = computed(() => isExpanded.value && html.value !== null)
const isLoading = computed(() => isExpanded.value && html.value === null && !hasFailed.value)

watch(
  () => props.description,
  () => {
    isExpanded.value = false
    hasFailed.value = false
  },
)

function measureClamp(): void {
  const element = textElement.value
  if (element === null || isExpanded.value) {
    return
  }
  isClamped.value = element.scrollHeight - element.clientHeight > CLAMP_TOLERANCE_PX
}

onMounted(measureClamp)
watch([plainText, isExpanded], measureClamp, { flush: 'post' })
useResizeObserver(textElement, measureClamp)

async function loadHtml(): Promise<void> {
  const source = props.description
  try {
    rendered.value = { source, html: await renderMarkdown(source) }
  } catch (error: unknown) {
    hasFailed.value = source === props.description
    throw error
  }
}

async function toggle(): Promise<void> {
  isExpanded.value = !isExpanded.value
  hasFailed.value = false
  if (isExpanded.value && html.value === null) {
    await loadHtml()
  }
}
</script>

<template>
  <div v-if="plainText" data-slot="job-description" class="flex min-w-0 flex-col items-start gap-2">
    <div
      v-if="isHtmlShown"
      :id="contentId"
      data-slot="job-description-html"
      class="job-markdown w-full min-w-0 animate-in text-body-sm text-ink duration-200 fade-in"
      v-html="html"
    />
    <p
      v-else
      :id="contentId"
      ref="textElement"
      data-slot="job-description-text"
      :aria-busy="isLoading ? 'true' : undefined"
      :class="
        cn('w-full min-w-0 text-body-sm wrap-break-word text-ink', !isExpanded && 'line-clamp-3')
      "
    >
      {{ plainText }}
    </p>
    <p
      v-if="hasFailed && isExpanded"
      data-slot="job-description-error"
      role="status"
      class="text-body-sm text-ink-muted"
    >
      Could not format this description, showing plain text
    </p>
    <button
      v-if="isToggleShown"
      type="button"
      data-slot="job-description-toggle"
      :aria-expanded="isExpanded"
      :aria-controls="contentId"
      class="cursor-pointer rounded-sm text-body-sm font-semibold text-link underline decoration-transparent underline-offset-4 outline-none transition-colors duration-150 hover:decoration-current focus-visible:focus-ring active:text-accent-hover"
      @click="toggle"
    >
      {{ isExpanded ? 'Show less' : 'Show more' }}
    </button>
  </div>
</template>

<style scoped>
.job-markdown {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  overflow-wrap: anywhere;
}

.job-markdown :deep(:is(h1, h2, h3, h4, h5, h6)) {
  font-weight: 600;
  color: var(--ink);
}

.job-markdown :deep(:is(h1, h2, h3, h4, h5, h6):not(:first-child)) {
  margin-top: var(--space-1);
}

.job-markdown :deep(p:empty) {
  display: none;
}

.job-markdown :deep(:is(strong, b)) {
  font-weight: 600;
}

.job-markdown :deep(:is(ul, ol)) {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  padding-left: var(--space-6);
}

.job-markdown :deep(ul) {
  list-style: disc;
}

.job-markdown :deep(ol) {
  list-style: decimal;
}

.job-markdown :deep(li::marker) {
  color: var(--ink-muted);
}

.job-markdown :deep(li > :is(ul, ol, p + p)) {
  margin-top: var(--space-1);
}

.job-markdown :deep(a[href]) {
  color: var(--link);
  text-decoration: underline;
  text-underline-offset: 2px;
  border-radius: 2px;
  transition: color 150ms ease-out;
}

.job-markdown :deep(a[href]:hover) {
  color: var(--accent-hover);
}

.job-markdown :deep(a[href]:focus-visible) {
  outline: none;
  box-shadow: var(--focus-ring);
}

.job-markdown :deep(code) {
  padding: 0 var(--space-1);
  border-radius: 4px;
  background: var(--surface-subtle);
  font-family: var(--font-mono, ui-monospace, monospace);
}

.job-markdown :deep(pre) {
  overflow-x: auto;
  padding: var(--space-3);
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--surface-subtle);
}

.job-markdown :deep(pre code) {
  padding: 0;
  background: none;
}

.job-markdown :deep(blockquote) {
  padding-left: var(--space-3);
  border-left: 2px solid var(--line-strong);
  color: var(--ink-muted);
}
</style>
