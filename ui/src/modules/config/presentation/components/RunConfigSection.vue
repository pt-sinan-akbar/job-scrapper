<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, useId } from 'vue'
import { isNavigationFailure, NavigationFailureType, useRoute, useRouter } from 'vue-router'
import { ChevronDown, ChevronUp } from '@lucide/vue'
import ConfigForm from '@/modules/config/presentation/components/ConfigForm.vue'
import {
  readConfigCardOpen,
  writeConfigCardOpen,
} from '@/modules/config/presentation/components/configCardStorage'
import { useConfigStore } from '@/modules/config/presentation/stores/useConfigStore'
import PageLoadState from '@/shared/components/PageLoadState.vue'
import PageSection from '@/shared/components/PageSection.vue'
import { Button } from '@/shared/components/ui/button'
import { Skeleton } from '@/shared/components/ui/skeleton'

const CONFIG_HASH = '#config'

const store = useConfigStore()
const route = useRoute()
const router = useRouter()
const isOpen = ref(readConfigCardOpen())
const bodyId = useId()

function toggle(): void {
  isOpen.value = !isOpen.value
  writeConfigCardOpen(isOpen.value)
}

function expandForLink(): void {
  isOpen.value = true
}

if (route.hash === CONFIG_HASH) {
  expandForLink()
}

const stopListening = router.afterEach((to, _from, failure) => {
  const isDuplicate = isNavigationFailure(failure, NavigationFailureType.duplicated)
  if (to.hash === CONFIG_HASH && (!failure || isDuplicate)) {
    expandForLink()
  }
})

onBeforeUnmount(stopListening)

onMounted(() => {
  if (store.status === 'idle') {
    void store.load()
  }
})
</script>

<template>
  <PageSection title="Config">
    <template #actions>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        :aria-label="isOpen ? 'Hide config' : 'Show config'"
        :aria-controls="bodyId"
        :aria-expanded="isOpen"
        @click="toggle"
      >
        <ChevronUp v-if="isOpen" aria-hidden="true" />
        <ChevronDown v-else aria-hidden="true" />
      </Button>
    </template>
    <div v-if="isOpen" :id="bodyId" class="flex min-w-0 flex-col gap-6 md:gap-4">
      <PageLoadState
        v-if="store.values === null"
        :is-error="store.status === 'error'"
        loading-label="Loading config"
        error-title="Could not load config"
        :error-message="store.errorMessage"
        @retry="store.load"
      >
        <div class="flex flex-col gap-6 md:gap-4">
          <Skeleton v-for="index in 3" :key="index" class="h-48 w-full rounded-lg" />
        </div>
      </PageLoadState>
      <ConfigForm v-else :is-save-bar-sticky="false" />
    </div>
  </PageSection>
</template>
