<script setup lang="ts">
import { computed } from 'vue'
import { toast } from 'vue-sonner'
import type { SiteSetting } from '@/modules/config/domain/entities/ScraperConfig'
import JobFieldsInput from '@/modules/config/presentation/components/JobFieldsInput.vue'
import SiteSettings from '@/modules/config/presentation/components/SiteSettings.vue'
import { useConfigStore } from '@/modules/config/presentation/stores/useConfigStore'
import PageSection from '@/shared/components/PageSection.vue'
import { Button } from '@/shared/components/ui/button'
import { cn } from '@/shared/utils/cn'

withDefaults(defineProps<{ isSaveBarSticky?: boolean }>(), { isSaveBarSticky: true })

const SAVED_MESSAGE = 'Config saved'
const store = useConfigStore()
const isStale = computed(() => store.snapshot?.isStale ?? true)
const jobFields = computed(() => store.snapshot?.jobFields ?? [])
const mandatoryFields = computed(() => store.snapshot?.mandatoryFields ?? [])
const locationOptions = computed(() => store.snapshot?.locationOptions ?? {})

function updateSite(next: SiteSetting): void {
  if (store.values !== null) {
    store.values.sites = store.values.sites.map((site) => (site.name === next.name ? next : site))
  }
}

async function save(): Promise<void> {
  if (await store.save()) {
    toast.success(SAVED_MESSAGE)
  }
}
</script>

<template>
  <div v-if="store.values !== null" class="flex min-w-0 flex-col gap-6 md:gap-4">
    <div
      v-if="store.status === 'error'"
      role="alert"
      class="flex flex-wrap items-center justify-between gap-3 rounded-md border border-line-strong p-4"
    >
      <p class="text-body-sm text-ink">
        Could not refresh the config, so it may be out of date. {{ store.errorMessage }}
      </p>
      <Button size="sm" @click="store.load">Try again</Button>
    </div>
    <p
      v-if="isStale"
      role="status"
      class="rounded-md border border-line-strong p-4 text-body-sm text-ink"
    >
      The scraper is busy, so these values may be out of date. Saving is off until it is free
    </p>

    <form class="flex flex-col gap-6 md:gap-4" @submit.prevent="save">
      <fieldset :disabled="isStale" class="flex min-w-0 flex-col gap-6 border-0 p-0 md:gap-4">
        <PageSection title="Job fields">
          <JobFieldsInput
            id-prefix="default"
            legend="Job fields"
            v-model="store.values.defaultFields"
            :job-fields="jobFields"
            :mandatory-fields="mandatoryFields"
          />
        </PageSection>

        <PageSection title="Sites">
          <SiteSettings
            :sites="store.values.sites"
            :default-fields="store.values.defaultFields"
            :job-fields="jobFields"
            :mandatory-fields="mandatoryFields"
            :location-options="locationOptions"
            :issue="store.siteIssue"
            @update="updateSite"
          />
        </PageSection>
      </fieldset>

      <div
        data-slot="save-bar"
        :class="
          cn(
            'flex flex-wrap items-center justify-end gap-3 py-3',
            isSaveBarSticky && 'sticky bottom-0 z-20 -mx-4 bg-surface px-4 md:mx-0',
          )
        "
      >
        <p v-if="store.saveError" role="alert" class="mr-auto text-body-sm text-danger">
          {{ store.saveError }}
        </p>
        <Button type="button" :disabled="!store.isDirty || store.isSaving" @click="store.discard">
          Discard
        </Button>
        <Button type="submit" variant="primary" :disabled="store.isSaving || isStale">
          {{ store.isSaving ? 'Saving' : 'Save' }}
        </Button>
      </div>
    </form>
  </div>
</template>
