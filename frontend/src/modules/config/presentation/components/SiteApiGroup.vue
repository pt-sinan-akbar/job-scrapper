<script setup lang="ts">
import type {
  ApiSetting,
  LocationOption,
  SiteField,
  SiteToggleField,
} from '@/modules/config/domain/entities/ScraperConfig'
import LocationPicker from '@/modules/config/presentation/components/LocationPicker.vue'
import NumberInput from '@/modules/config/presentation/components/NumberInput.vue'
import SiteGroup from '@/modules/config/presentation/components/SiteGroup.vue'
import { Checkbox } from '@/shared/components/ui/checkbox'
import { Label } from '@/shared/components/ui/label'

const NO_SEARCH_WARNING = 'No city and no country search: this site finds nothing'

const props = defineProps<{
  idPrefix: string
  api: ApiSetting
  locationOptions?: LocationOption[]
  invalidField?: SiteField | null
}>()

const emit = defineEmits<{
  update: [api: ApiSetting]
  toggle: [field: SiteToggleField, isOn: boolean]
}>()

function change(changes: Partial<ApiSetting>): void {
  emit('update', { ...props.api, ...changes })
}
</script>

<template>
  <SiteGroup legend="API">
    <div class="flex flex-col gap-4">
      <div class="flex items-center gap-3">
        <Checkbox
          :id="`${idPrefix}-api-enabled`"
          :model-value="api.isEnabled"
          @update:model-value="emit('toggle', 'apiEnabled', $event === true)"
        />
        <Label :for="`${idPrefix}-api-enabled`" class="cursor-pointer">Use the API</Label>
      </div>
      <div class="flex items-center gap-3">
        <Checkbox
          :id="`${idPrefix}-api-country`"
          :model-value="api.isCountryWide"
          @update:model-value="emit('toggle', 'apiCountryWide', $event === true)"
        />
        <Label :for="`${idPrefix}-api-country`" class="cursor-pointer">
          Also search the whole country
        </Label>
      </div>
    </div>
    <div
      v-if="locationOptions !== undefined && locationOptions.length > 0"
      class="flex flex-col gap-2"
    >
      <Label :for="`${idPrefix}-api-locations`">API locations</Label>
      <LocationPicker
        :id="`${idPrefix}-api-locations`"
        :model-value="api.locations"
        :options="locationOptions"
        @update:model-value="change({ locations: $event })"
      />
      <p
        v-if="api.locations.length === 0 && !api.isCountryWide"
        role="status"
        class="text-body-sm text-danger"
      >
        {{ NO_SEARCH_WARNING }}
      </p>
    </div>
    <div class="grid gap-8 sm:grid-cols-2 sm:gap-6">
      <div class="flex flex-col gap-2">
        <Label :for="`${idPrefix}-api-delay-min`">Min delay in seconds</Label>
        <NumberInput
          :id="`${idPrefix}-api-delay-min`"
          :model-value="api.delayMin"
          allow-decimal
          placeholder="Min delay"
          :is-invalid="invalidField === 'delayMin'"
          @update:model-value="change({ delayMin: $event })"
        />
      </div>
      <div class="flex flex-col gap-2">
        <Label :for="`${idPrefix}-api-delay-max`">Max delay in seconds</Label>
        <NumberInput
          :id="`${idPrefix}-api-delay-max`"
          :model-value="api.delayMax"
          allow-decimal
          placeholder="Max delay"
          :is-invalid="invalidField === 'delayMax'"
          @update:model-value="change({ delayMax: $event })"
        />
      </div>
    </div>
  </SiteGroup>
</template>
