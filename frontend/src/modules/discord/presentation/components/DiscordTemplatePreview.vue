<script setup lang="ts">
import { computed, ref, useId, watch } from 'vue'
import { toSampleMessage } from '@/modules/discord/domain/entities/Discord'
import MarkdownContent from '@/shared/components/MarkdownContent.vue'
import { renderMarkdown } from '@/shared/utils/markdown'

const EMPTY_TEMPLATE_HINT = 'Write a template to see the preview'
const EMPTY_MESSAGE_HINT = 'This template is empty for the sample job'

const props = defineProps<{
  messageTemplate: string
}>()

const labelId = useId()
const captionId = useId()
const renderedHtml = ref<string | null>(null)
const hasFailed = ref(false)

const sampleMessage = computed(() => toSampleMessage(props.messageTemplate))
const shownHtml = computed(() => (hasFailed.value ? null : renderedHtml.value))
const emptyHint = computed(() => {
  if (props.messageTemplate.trim() === '') {
    return EMPTY_TEMPLATE_HINT
  }
  if (sampleMessage.value.trim() === '') {
    return EMPTY_MESSAGE_HINT
  }
  return null
})

function refreshPreview(message: string): Promise<void> {
  hasFailed.value = false
  if (message.trim() === '') {
    renderedHtml.value = null
    return Promise.resolve()
  }
  return renderSampleMessage(message)
}

async function renderSampleMessage(message: string): Promise<void> {
  try {
    const html = await renderMarkdown(message, { shouldKeepLineBreaks: true })
    if (message === sampleMessage.value) {
      renderedHtml.value = html
    }
  } catch (error: unknown) {
    hasFailed.value = message === sampleMessage.value
    throw error
  }
}

watch(sampleMessage, refreshPreview, { immediate: true })
</script>

<template>
  <section
    data-slot="template-preview"
    :aria-labelledby="labelId"
    :aria-describedby="captionId"
    class="flex min-w-0 flex-col gap-2"
  >
    <p :id="labelId" class="text-body-sm font-semibold text-ink">Preview</p>
    <div
      data-slot="template-preview-panel"
      class="min-h-64 min-w-0 rounded-md border border-line bg-surface-subtle p-4 text-body-sm text-ink"
    >
      <p v-if="emptyHint !== null" data-slot="template-preview-empty" class="text-ink-muted">
        {{ emptyHint }}
      </p>
      <MarkdownContent
        v-else-if="shownHtml !== null"
        data-slot="template-preview-html"
        :sanitized-html="shownHtml"
      />
      <p
        v-else
        data-slot="template-preview-text"
        :aria-busy="hasFailed ? undefined : 'true'"
        class="wrap-anywhere whitespace-pre-wrap"
      >
        {{ sampleMessage }}
      </p>
    </div>
    <p
      v-if="hasFailed"
      data-slot="template-preview-error"
      role="status"
      class="text-body-sm text-ink-muted"
    >
      Could not format the preview, showing plain text
    </p>
    <p :id="captionId" class="text-body-sm text-ink-muted">
      Filled with a sample job, each job in the digest file looks like this
    </p>
  </section>
</template>
