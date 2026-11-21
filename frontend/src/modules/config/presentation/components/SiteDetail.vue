<script setup lang="ts">
import { computed } from 'vue'
import {
  SITE_LIMIT_MAX,
  SITE_LIMIT_MIN,
  type LocationOption,
  type SiteField,
  type SiteSetting,
  type SiteToggle,
  type SiteToggleField,
} from '@/modules/config/domain/entities/ScraperConfig'
import FilterFields from '@/modules/config/presentation/components/FilterFields.vue'
import NumberInput from '@/modules/config/presentation/components/NumberInput.vue'
import SiteApiGroup from '@/modules/config/presentation/components/SiteApiGroup.vue'
import SiteGroup from '@/modules/config/presentation/components/SiteGroup.vue'
import SiteSourceGroup from '@/modules/config/presentation/components/SiteSourceGroup.vue'
import { toSiteIdPrefix } from '@/modules/config/presentation/components/siteIds'
import { Label } from '@/shared/components/ui/label'

const LIMIT_HINT = `${SITE_LIMIT_MIN} to ${SITE_LIMIT_MAX}`

const props = defineProps<{
  site: SiteSetting
  locationOptions?: LocationOption[]
  invalidField?: SiteField | null
}>()

const emit = defineEmits<{
  update: [site: SiteSetting]
  toggle: [toggle: SiteToggle]
}>()

const idPrefix = computed(() => toSiteIdPrefix(props.site.name))

function emitToggle(field: SiteToggleField, isOn: boolean): void {
  emit('toggle', { siteName: props.site.name, field, isOn })
}

function change(changes: Partial<Omit<SiteSetting, 'name'>>): void {
  emit('update', { ...props.site, ...changes })
}
</script>

<template>
  <div class="flex min-w-0 flex-col gap-6">
    <SiteSourceGroup :id-prefix="idPrefix" :site="site" />
    <SiteGroup legend="Basics">
      <div class="grid gap-8 sm:grid-cols-2 sm:gap-6">
        <div class="flex flex-col gap-2">
          <Label :for="`${idPrefix}-limit`">Job limit</Label>
          <NumberInput
            :id="`${idPrefix}-limit`"
            :model-value="site.limit"
            required
            :placeholder="LIMIT_HINT"
            :is-invalid="invalidField === 'limit'"
            @update:model-value="change({ limit: $event })"
          />
        </div>
        <div class="flex flex-col gap-2">
          <Label :for="`${idPrefix}-max-age`">Max job age in hours</Label>
          <NumberInput
            :id="`${idPrefix}-max-age`"
            :model-value="site.maxAgeHours"
            placeholder="Any age"
            :is-invalid="invalidField === 'maxAgeHours'"
            @update:model-value="change({ maxAgeHours: $event })"
          />
        </div>
      </div>
    </SiteGroup>
    <SiteGroup legend="Filter">
      <FilterFields
        :id-prefix="idPrefix"
        :model-value="site.filter"
        @update:model-value="change({ filter: $event })"
      />
    </SiteGroup>
    <SiteApiGroup
      v-if="site.api !== null"
      :id-prefix="idPrefix"
      :api="site.api"
      :invalid-field="invalidField"
      :location-options="locationOptions"
      @update="change({ api: $event })"
      @toggle="emitToggle"
    />
  </div>
</template>
