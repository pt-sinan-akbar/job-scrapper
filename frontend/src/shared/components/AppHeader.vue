<script setup lang="ts">
import { ChevronDown, LogOut, ShieldUser } from '@lucide/vue'
import { nextTick, ref, watch, type ComponentPublicInstance } from 'vue'
import { RouterLink } from 'vue-router'

import type { NavItem } from '@/shared/components/types'
import SignOutConfirmDialog from '@/shared/components/SignOutConfirmDialog.vue'
import ThemeMenuGroup from '@/shared/components/ThemeMenuGroup.vue'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/shared/components/ui/dropdown-menu'
import { cn } from '@/shared/utils/cn'
import { THEME_MODE_LABELS, type ThemeMode } from '@/shared/utils/theme'

const NAV_LINK_CLASS =
  'flex size-11 items-center justify-center gap-2 rounded-md text-body-sm font-semibold text-ink-muted outline-none hover:bg-surface-subtle hover:text-ink focus-visible:focus-ring sm:w-auto sm:px-3'
const NAV_LINK_ACTIVE_CLASS = 'bg-surface-subtle text-ink'

defineProps<{
  items: NavItem[]
  canSignOut: boolean
}>()

defineEmits<{
  signOut: []
}>()

const isSignOutDialogOpen = ref(false)
const adminTrigger = ref<InstanceType<typeof DropdownMenuTrigger> | null>(null)
const themeAnnouncement = ref('')

function focusButton(button: ComponentPublicInstance | null): void {
  const element = button?.$el as HTMLElement | undefined
  element?.focus()
}

watch(isSignOutDialogOpen, (isOpen) => {
  if (!isOpen) {
    void nextTick(() => focusButton(adminTrigger.value))
  }
})

function announceTheme(mode: ThemeMode): void {
  themeAnnouncement.value = `Theme changed to ${THEME_MODE_LABELS[mode]}`
}

function requestSignOut(): void {
  void nextTick(() => {
    isSignOutDialogOpen.value = true
  })
}
</script>

<template>
  <header
    data-slot="app-header"
    class="sticky top-0 z-30 border-b border-line bg-surface px-4 md:px-12"
  >
    <div class="mx-auto flex h-16 w-full max-w-content items-center gap-3">
      <h1 class="min-w-0 truncate text-heading font-bold text-ink">Job Agent Scraper</h1>

      <nav aria-label="Main" class="ml-auto flex items-center gap-1">
        <RouterLink
          v-for="item in items"
          :key="item.id"
          v-slot="{ href, navigate, isExactActive }"
          :to="item.to"
          custom
        >
          <a
            :href="href"
            :aria-current="isExactActive ? 'page' : undefined"
            :class="cn(NAV_LINK_CLASS, isExactActive && NAV_LINK_ACTIVE_CLASS)"
            @click="navigate"
          >
            <component :is="item.icon" class="size-5" aria-hidden="true" />
            <span class="max-sm:sr-only">{{ item.label }}</span>
          </a>
        </RouterLink>
      </nav>

      <span class="sr-only" role="status" aria-live="polite" data-slot="theme-announcement">{{
        themeAnnouncement
      }}</span>
      <DropdownMenu>
        <DropdownMenuTrigger
          ref="adminTrigger"
          aria-label="Admin menu"
          class="group/account flex shrink-0 cursor-pointer items-center gap-2 rounded-md bg-accent-soft py-1 pr-2 pl-1 outline-none focus-visible:focus-ring"
        >
          <span
            aria-hidden="true"
            class="flex size-9 items-center justify-center rounded-full bg-accent text-on-accent"
          >
            <ShieldUser class="size-5" />
          </span>
          <ChevronDown
            class="size-4 text-ink-muted transition-transform duration-150 group-data-[state=open]/account:rotate-180"
            aria-hidden="true"
          />
        </DropdownMenuTrigger>
        <DropdownMenuContent side="bottom" align="end" aria-label="Admin">
          <ThemeMenuGroup @change="announceTheme" />
          <template v-if="canSignOut">
            <DropdownMenuSeparator />
            <DropdownMenuItem variant="danger" @select="requestSignOut">
              <LogOut aria-hidden="true" />
              Sign out
            </DropdownMenuItem>
          </template>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
    <SignOutConfirmDialog v-model:open="isSignOutDialogOpen" @confirm="$emit('signOut')" />
  </header>
</template>
