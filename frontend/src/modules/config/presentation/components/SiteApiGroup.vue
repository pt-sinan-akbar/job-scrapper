<script setup lang="ts">
import type {
  ApiSetting,
  SiteField,
  SiteToggleField,
} from '@/modules/config/domain/entities/ScraperConfig'
import NumberInput from '@/modules/config/presentation/components/NumberInput.vue'
import SiteGroup from '@/modules/config/presentation/components/SiteGroup.vue'
import { Checkbox } from '@/shared/components/ui/checkbox'
import { Label } from '@/shared/components/ui/label'

const props = defineProps<{
  idPrefix: string
  api: ApiSetting
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
    <div class="flex items-center gap-3">
      <Checkbox
        :id="`${idPrefix}-api-enabled`"
        :model-value="api.isEnabled"
        @update:model-value="emit('toggle', 'apiEnabled', $event === true)"
      />
      <Label :for="`${idPrefix}-api-enabled`" class="cursor-pointer">Use the API</Label>
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
