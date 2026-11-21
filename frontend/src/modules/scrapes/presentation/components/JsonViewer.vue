<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { CheckIcon, CopyIcon, Maximize2Icon } from '@lucide/vue'
import type { JsonValue } from '@/modules/scrapes/domain/entities/Scrape'
import {
  MAX_HIGHLIGHT_CHARS,
  prettyJson,
  tokenizeJson,
  type JsonTokenKind,
} from '@/modules/scrapes/presentation/components/jsonTokens'
import { Button } from '@/shared/components/ui/button'

type CopyState = 'idle' | 'copied' | 'failed'

const FEEDBACK_MS = 2000
const FULLSCREEN_LABEL = 'Open full screen'
const TOKEN_CLASSES: Record<JsonTokenKind, string> = {
  key: 'text-syntax-key',
  string: 'text-syntax-string',
  number: 'text-syntax-number',
  literal: 'font-semibold text-syntax-literal',
  punct: 'text-ink-muted',
  plain: '',
}
const COPY_LABELS: Record<CopyState, string> = {
  idle: 'Copy JSON',
  copied: 'Copied',
  failed: 'Copy JSON',
}
const COPY_STATUSES: Record<CopyState, string> = {
  idle: '',
  copied: 'JSON copied',
  failed: 'Could not copy. Select the text and copy it by hand',
}
const ACTION_CLASS =
  'text-ink-muted hover:bg-accent-soft hover:text-accent active:bg-accent-soft active:text-accent'

const props = withDefaults(
  defineProps<{ value: JsonValue; label?: string; isFullscreenHidden?: boolean }>(),
  { label: 'JSON output' },
)
const emit = defineEmits<{ fullscreen: [] }>()

const text = computed(() => prettyJson(props.value))
const isHighlighted = computed(() => text.value.length <= MAX_HIGHLIGHT_CHARS)
const tokens = computed(() => (isHighlighted.value ? tokenizeJson(text.value) : []))

const copyState = ref<CopyState>('idle')
let resetTimer: ReturnType<typeof setTimeout> | null = null

function showCopyState(next: CopyState): void {
  copyState.value = next
  if (resetTimer !== null) {
    clearTimeout(resetTimer)
  }
  resetTimer = setTimeout(() => {
    copyState.value = 'idle'
    resetTimer = null
  }, FEEDBACK_MS)
}

async function copy(): Promise<void> {
  try {
    await navigator.clipboard.writeText(text.value)
    showCopyState('copied')
  } catch {
    showCopyState('failed')
  }
}

onBeforeUnmount(() => {
  if (resetTimer !== null) {
    clearTimeout(resetTimer)
  }
})
</script>

<template>
  <div data-slot="json-viewer" class="flex h-full min-h-0 min-w-0 flex-1 flex-col gap-2">
    <div class="relative flex min-h-0 min-w-0 flex-1 flex-col">
      <div
        data-slot="json-scroll"
        tabindex="0"
        role="region"
        :aria-label="label"
        class="min-h-0 flex-1 overflow-auto rounded-md border border-line bg-surface-subtle p-4 outline-none focus-visible:focus-ring"
      >
        <pre
          class="font-mono text-code whitespace-pre text-ink"
        ><code v-if="!isHighlighted">{{ text }}</code><code v-else><template
          v-for="(token, index) in tokens"
          :key="index"
        ><span v-if="token.kind === 'plain'">{{ token.text }}</span><span
          v-else
          :data-token="token.kind"
          :class="TOKEN_CLASSES[token.kind]"
        >{{ token.text }}</span></template></code></pre>
      </div>
      <div
        data-slot="json-actions"
        class="absolute top-2 right-4 flex items-center gap-1 rounded-full border border-line bg-surface p-1 shadow-sm"
      >
        <Button
          v-if="!isFullscreenHidden"
          data-slot="json-fullscreen"
          variant="ghost"
          size="icon"
          :aria-label="FULLSCREEN_LABEL"
          :title="FULLSCREEN_LABEL"
          :class="ACTION_CLASS"
          @click="emit('fullscreen')"
        >
          <Maximize2Icon data-icon="fullscreen" aria-hidden="true" />
        </Button>
        <Button
          data-slot="json-copy"
          variant="ghost"
          size="icon"
          :aria-label="COPY_LABELS[copyState]"
          :title="COPY_LABELS[copyState]"
          :class="[ACTION_CLASS, copyState === 'copied' && 'bg-accent-soft text-accent']"
          @click="copy"
        >
          <CheckIcon v-if="copyState === 'copied'" data-icon="check" aria-hidden="true" />
          <CopyIcon v-else data-icon="copy" aria-hidden="true" />
        </Button>
      </div>
    </div>
    <p
      data-slot="json-copy-status"
      role="status"
      :class="copyState === 'failed' ? 'text-body-sm text-danger' : 'sr-only'"
    >
      {{ COPY_STATUSES[copyState] }}
    </p>
  </div>
</template>
