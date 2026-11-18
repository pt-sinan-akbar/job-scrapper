<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Input } from '@/shared/components/ui/input'

const WHOLE_NUMBER = /^-?\d+$/
const DECIMAL_NUMBER = /^-?(?:\d+\.?\d*|\.\d+)$/

const props = withDefaults(
  defineProps<{ modelValue: number | null; allowDecimal?: boolean; isInvalid?: boolean }>(),
  { allowDecimal: false, isInvalid: false },
)

const emit = defineEmits<{
  'update:modelValue': [value: number | null]
}>()

function toText(value: number | null): string {
  return value === null ? '' : String(value)
}

function parse(text: string): number | null | undefined {
  const trimmed = text.trim()
  if (trimmed === '') {
    return null
  }
  const pattern = props.allowDecimal ? DECIMAL_NUMBER : WHOLE_NUMBER
  return pattern.test(trimmed) ? Number(trimmed) : undefined
}

const text = ref(toText(props.modelValue))
const isUnparsed = computed(() => parse(text.value) === undefined)

watch(
  () => props.modelValue,
  (value) => {
    if (parse(text.value) !== value) {
      text.value = toText(value)
    }
  },
)

function changeText(value: string | number): void {
  text.value = String(value)
  const parsed = parse(text.value)
  if (parsed !== undefined) {
    emit('update:modelValue', parsed)
  }
}

function restoreText(): void {
  if (isUnparsed.value) {
    text.value = toText(props.modelValue)
  }
}
</script>

<template>
  <Input
    :model-value="text"
    type="text"
    :inputmode="allowDecimal ? 'decimal' : 'numeric'"
    :aria-invalid="isInvalid || isUnparsed || undefined"
    @update:model-value="changeText"
    @blur="restoreText"
  />
</template>
