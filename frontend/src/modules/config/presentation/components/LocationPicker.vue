<script setup lang="ts">
import { computed, ref } from 'vue'
import { CheckIcon } from '@lucide/vue'
import { ComboboxInput } from 'reka-ui'
import {
  Combobox,
  ComboboxAnchor,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxItem,
  ComboboxItemIndicator,
  ComboboxViewport,
} from '@/shared/components/ui/combobox'
import {
  TagsInput,
  TagsInputInput,
  TagsInputItem,
  TagsInputItemDelete,
  TagsInputItemText,
} from '@/shared/components/ui/tags-input'

const PLACEHOLDER = 'Pick locations'
const NO_MATCH_TEXT = 'No location found'

const props = defineProps<{
  id: string
  modelValue: string[]
  options: string[]
  describedBy?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [values: string[]]
}>()

const searchTerm = ref('')

const picked = computed({
  get: () => props.modelValue,
  set: (next: string[]) => {
    searchTerm.value = ''
    emit('update:modelValue', next)
  },
})

const visibleOptions = computed(() => {
  const term = searchTerm.value.trim().toLowerCase()
  return props.options.filter((option) => option.toLowerCase().includes(term))
})
</script>

<template>
  <Combobox v-model="picked" multiple ignore-filter open-on-focus>
    <ComboboxAnchor as-child>
      <TagsInput
        v-model="picked"
        :delimiter="''"
        :add-on-paste="false"
        :add-on-blur="false"
        :add-on-tab="false"
      >
        <TagsInputItem v-for="location in picked" :key="location" :value="location">
          <TagsInputItemText>{{ location }}</TagsInputItemText>
          <TagsInputItemDelete :aria-label="`Remove ${location}`" />
        </TagsInputItem>
        <ComboboxInput v-model="searchTerm" as-child>
          <TagsInputInput
            :id="id"
            :placeholder="picked.length === 0 ? PLACEHOLDER : ''"
            :aria-describedby="describedBy"
            @keydown.enter.prevent
          />
        </ComboboxInput>
      </TagsInput>
    </ComboboxAnchor>
    <ComboboxContent>
      <ComboboxViewport>
        <ComboboxEmpty>{{ NO_MATCH_TEXT }}</ComboboxEmpty>
        <ComboboxItem v-for="option in visibleOptions" :key="option" :value="option">
          <span class="truncate">{{ option }}</span>
          <ComboboxItemIndicator>
            <CheckIcon />
          </ComboboxItemIndicator>
        </ComboboxItem>
      </ComboboxViewport>
    </ComboboxContent>
  </Combobox>
</template>
