<script setup lang="ts">
import AuthBrandPanel from '@/modules/auth/presentation/components/AuthBrandPanel.vue'
import AuthThemeMenu from '@/modules/auth/presentation/components/AuthThemeMenu.vue'
</script>

<template>
  <div
    class="relative min-h-dvh bg-surface text-ink lg:grid lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]"
  >
    <AuthBrandPanel />
    <div class="flex min-h-dvh min-w-0 flex-col">
      <header class="flex items-center gap-3 px-4 pt-4 sm:px-6 sm:pt-6">
        <span
          data-testid="auth-lockup"
          class="min-w-0 truncate text-heading font-bold text-ink lg:hidden"
          >Job Agent Scraper</span
        >
        <div class="ml-auto">
          <AuthThemeMenu />
        </div>
      </header>
      <main class="flex flex-1 items-center justify-center px-4 py-12 sm:px-8">
        <div
          data-testid="auth-column"
          class="flex w-full max-w-96 animate-in flex-col gap-8 duration-300 ease-out fill-mode-both fade-in slide-in-from-bottom-2"
        >
          <slot />
        </div>
      </main>
    </div>
  </div>
</template>
