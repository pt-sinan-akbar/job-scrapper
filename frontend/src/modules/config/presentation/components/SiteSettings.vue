<script setup lang="ts">
import { computed, ref, useId, watch } from 'vue'
import type {
  LocationOption,
  SiteIssue,
  SiteSetting,
  SiteToggle,
} from '@/modules/config/domain/entities/ScraperConfig'
import SiteDetail from '@/modules/config/presentation/components/SiteDetail.vue'
import SiteList from '@/modules/config/presentation/components/SiteList.vue'
import EmptyState from '@/shared/components/EmptyState.vue'
import SelectionTransition from '@/shared/components/SelectionTransition.vue'

const props = defineProps<{
  sites: SiteSetting[]
  locationOptions: Record<string, LocationOption[]>
  issue?: SiteIssue | null
}>()

const emit = defineEmits<{
  update: [site: SiteSetting]
  toggle: [toggle: SiteToggle]
}>()

const pickedName = ref<string | null>(null)
const panelId = useId()
const headingId = useId()

const selectedSite = computed(
  () => props.sites.find((site) => site.name === pickedName.value) ?? props.sites[0] ?? null,
)

const invalidField = computed(() =>
  props.issue != null && props.issue.siteName === selectedSite.value?.name
    ? props.issue.field
    : null,
)

watch(
  () => props.sites,
  (sites) => {
    if (!sites.some((site) => site.name === pickedName.value)) {
      pickedName.value = null
    }
  },
)

watch(
  () => props.issue,
  (issue) => {
    if (issue != null) {
      pickedName.value = issue.siteName
    }
  },
)
</script>

<template>
  <EmptyState
    v-if="selectedSite === null"
    compact
    title="No sites from the scraper."
    hint="Update the scraper, then reload."
  />
  <div v-else class="grid min-w-0 gap-6 md:grid-cols-[14rem_minmax(0,1fr)] md:gap-8">
    <SiteList
      :sites="sites"
      :selected-name="selectedSite.name"
      :panel-id="panelId"
      @select="pickedName = $event"
      @toggle="emit('toggle', $event)"
    />
    <SelectionTransition>
      <section
        :id="panelId"
        :key="selectedSite.name"
        :aria-labelledby="headingId"
        class="flex min-w-0 flex-col gap-6 md:border-l md:border-line md:pl-8"
      >
        <h4 :id="headingId" class="text-body font-semibold text-ink">
          {{ selectedSite.name }} settings
        </h4>
        <SiteDetail
          :site="selectedSite"
          :location-options="locationOptions[selectedSite.name]"
          :invalid-field="invalidField"
          @update="emit('update', $event)"
          @toggle="emit('toggle', $event)"
        />
      </section>
    </SelectionTransition>
  </div>
</template>
