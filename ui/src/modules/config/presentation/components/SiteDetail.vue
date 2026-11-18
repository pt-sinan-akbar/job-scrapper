<script setup lang="ts">
import { computed } from 'vue'
import {
  SITE_LIMIT_MAX,
  SITE_LIMIT_MIN,
  type LocationOption,
  type SiteField,
  type SiteSetting,
} from '@/modules/config/domain/entities/ScraperConfig'
import FilterFields from '@/modules/config/presentation/components/FilterFields.vue'
import JobFieldsInput from '@/modules/config/presentation/components/JobFieldsInput.vue'
import NumberInput from '@/modules/config/presentation/components/NumberInput.vue'
import SiteApiGroup from '@/modules/config/presentation/components/SiteApiGroup.vue'
import SiteGroup from '@/modules/config/presentation/components/SiteGroup.vue'
import { toSiteIdPrefix } from '@/modules/config/presentation/components/siteIds'
import { Checkbox } from '@/shared/components/ui/checkbox'
import { Label } from '@/shared/components/ui/label'

const LIMIT_HINT = `${SITE_LIMIT_MIN} to ${SITE_LIMIT_MAX}`

const props = defineProps<{
  site: SiteSetting
  defaultFields: string[]
  jobFields: string[]
  mandatoryFields: string[]
  locationOptions?: LocationOption[]
  invalidField?: SiteField | null
}>()

const emit = defineEmits<{
  update: [site: SiteSetting]
}>()

const idPrefix = computed(() => toSiteIdPrefix(props.site.name))

function change(changes: Partial<Omit<SiteSetting, 'name'>>): void {
  emit('update', { ...props.site, ...changes })
}
</script>

<template>
  <div class="flex min-w-0 flex-col gap-6">
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
    <SiteGroup legend="Job fields">
      <div class="flex items-center gap-3">
        <Checkbox
          :id="`${idPrefix}-own-fields`"
          :model-value="site.fields !== null"
          @update:model-value="change({ fields: $event === true ? defaultFields : null })"
        />
        <Label :for="`${idPrefix}-own-fields`" class="cursor-pointer">
          Use its own job fields
        </Label>
      </div>
      <JobFieldsInput
        v-if="site.fields !== null"
        :id-prefix="idPrefix"
        :legend="`${site.name} job fields`"
        :model-value="site.fields"
        :job-fields="jobFields"
        :mandatory-fields="mandatoryFields"
        @update:model-value="change({ fields: $event })"
      />
    </SiteGroup>
    <SiteApiGroup
      v-if="site.api !== null"
      :id-prefix="idPrefix"
      :api="site.api"
      :invalid-field="invalidField"
      :location-options="locationOptions"
      @update="change({ api: $event })"
    />
  </div>
</template>
