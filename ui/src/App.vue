<script setup lang="ts">
import { computed } from 'vue'
import { RouterView, useRoute } from 'vue-router'
import { useAuthStore } from '@/modules/auth/presentation/stores/useAuthStore'
import { useRunToasts } from '@/modules/runs/presentation/composables/useRunToasts'
import { navItems } from '@/router/navigation'
import { useSignOut } from '@/session/useSignOut'
import AppHeader from '@/shared/components/AppHeader.vue'
import AppShell from '@/shared/components/AppShell.vue'
import SelectionTransition from '@/shared/components/SelectionTransition.vue'
import { Toaster } from '@/shared/components/ui/sonner'

const auth = useAuthStore()
const route = useRoute()
const isPublicPage = computed(() => route.meta.isPublic === true)

useRunToasts()

const signOut = useSignOut()
</script>

<template>
  <RouterView v-if="isPublicPage" />
  <AppShell v-else>
    <template #header>
      <AppHeader :items="navItems" :can-sign-out="auth.isAuthRequired" @sign-out="signOut" />
    </template>
    <RouterView v-slot="{ Component, route: current }">
      <SelectionTransition>
        <component :is="Component" :key="current.matched[0]?.path" />
      </SelectionTransition>
    </RouterView>
  </AppShell>
  <Toaster />
</template>
