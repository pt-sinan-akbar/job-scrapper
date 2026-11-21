<script setup lang="ts">
import { computed, onMounted, ref, useId, watch } from 'vue'
import { useResizeObserver } from '@vueuse/core'
import MarkdownContent from '@/shared/components/MarkdownContent.vue'
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
const expandedHtml = computed(() => (isExpanded.value ? html.value : null))
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
    <MarkdownContent
      v-if="expandedHtml !== null"
      :id="contentId"
      data-slot="job-description-html"
      class="w-full min-w-0 animate-in text-body-sm text-ink duration-200 fade-in"
      :sanitized-html="expandedHtml"
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
