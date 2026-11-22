<script setup lang="ts">
import { computed } from 'vue'
import type { FilterSetting } from '@/modules/config/domain/entities/ScraperConfig'
import ListInput from '@/modules/config/presentation/components/ListInput.vue'
import LocationPicker from '@/modules/config/presentation/components/LocationPicker.vue'
import { Label } from '@/shared/components/ui/label'

const NO_LOCATION_HINT = 'No location picked: searches all of Indonesia'

const props = defineProps<{
  idPrefix: string
  modelValue: FilterSetting
  locationOptions: string[]
}>()

const emit = defineEmits<{
  'update:modelValue': [filter: FilterSetting]
}>()

const hasNoLocation = computed(() => props.modelValue.location.length === 0)
const locationHintId = computed(() => `${props.idPrefix}-location-hint`)

function change(changes: Partial<FilterSetting>): void {
  emit('update:modelValue', { ...props.modelValue, ...changes })
}
</script>

<template>
  <div class="flex flex-col gap-8">
    <div class="flex flex-col gap-2">
      <Label :for="`${idPrefix}-location`">Locations</Label>
      <LocationPicker
        :id="`${idPrefix}-location`"
        :model-value="modelValue.location"
        :options="locationOptions"
        :described-by="hasNoLocation ? locationHintId : undefined"
        @update:model-value="change({ location: $event })"
      />
      <p v-if="hasNoLocation" :id="locationHintId" class="text-body-sm text-ink-muted">
        {{ NO_LOCATION_HINT }}
      </p>
    </div>
    <div class="flex flex-col gap-2">
      <Label :for="`${idPrefix}-employment`">Employment types, separated by commas</Label>
      <ListInput
        :id="`${idPrefix}-employment`"
        placeholder="Employment types"
        :model-value="modelValue.employmentType"
        @update:model-value="change({ employmentType: $event })"
      />
    </div>
    <div class="flex flex-col gap-2">
      <Label :for="`${idPrefix}-work`">Work types, separated by commas</Label>
      <ListInput
        :id="`${idPrefix}-work`"
        placeholder="Work types"
        :model-value="modelValue.workType"
        @update:model-value="change({ workType: $event })"
      />
    </div>
  </div>
</template>
