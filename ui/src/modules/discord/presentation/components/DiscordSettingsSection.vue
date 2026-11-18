<script setup lang="ts">
import {
  computed,
  nextTick,
  onMounted,
  ref,
  useTemplateRef,
  watch,
  type ComponentPublicInstance,
} from 'vue'
import { toast } from 'vue-sonner'
import {
  MAX_MESSAGE_CHARS,
  toSettingsChanges,
  toSettingsForm,
  type DiscordSettingsForm,
} from '@/modules/discord/domain/entities/Discord'
import TemplateVariables from '@/modules/discord/presentation/components/TemplateVariables.vue'
import { useDiscordSettingsStore } from '@/modules/discord/presentation/stores/useDiscordSettingsStore'
import { useConfigStore } from '@/modules/config/presentation/stores/useConfigStore'
import PageLoadState from '@/shared/components/PageLoadState.vue'
import PageSection from '@/shared/components/PageSection.vue'
import PasswordInput from '@/shared/components/PasswordInput.vue'
import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'
import { Skeleton } from '@/shared/components/ui/skeleton'
import { Textarea } from '@/shared/components/ui/textarea'

const SAVED_MESSAGE = 'Discord settings saved'
const TOKEN_PLACEHOLDER = 'Bot token'
const ID_PATTERN = '[0-9]{17,20}'
const TEMPLATE_ID = 'discord-template'
const TEMPLATE_VARIABLES_ID = 'discord-template-variables'

const store = useDiscordSettingsStore()
const form = ref<DiscordSettingsForm | null>(null)
const tokenPlaceholder = computed(() => store.settings?.tokenHint ?? TOKEN_PLACEHOLDER)
const configStore = useConfigStore()
const templateFields = computed(() => configStore.snapshot?.jobFields ?? [])

const templateRef = useTemplateRef<ComponentPublicInstance>('template')

function templateElement(): HTMLTextAreaElement | null {
  const element: unknown = templateRef.value?.$el
  return element instanceof HTMLTextAreaElement ? element : null
}

async function insertVariable(token: string): Promise<void> {
  if (form.value === null) {
    return
  }
  const current = form.value.messageTemplate
  const element = templateElement()
  const start = element?.selectionStart ?? current.length
  const end = element?.selectionEnd ?? current.length
  form.value = {
    ...form.value,
    messageTemplate: current.slice(0, start) + token + current.slice(end),
  }
  await nextTick()
  const caret = start + token.length
  element?.focus()
  element?.setSelectionRange(caret, caret)
}

watch(
  () => store.settings,
  (settings) => {
    form.value = settings === null ? null : toSettingsForm(settings)
  },
  { immediate: true },
)

async function save(): Promise<void> {
  if (form.value === null || store.settings === null) {
    return
  }
  if (await store.save(toSettingsChanges(form.value, store.settings))) {
    toast.success(SAVED_MESSAGE)
  }
}

onMounted(() => {
  if (store.settings === null) {
    void store.load()
  }
  if (configStore.status === 'idle' || configStore.status === 'error') {
    void configStore.load()
  }
})
</script>

<template>
  <PageSection title="Bot settings">
    <PageLoadState
      v-if="form === null"
      :is-error="store.status === 'error'"
      loading-label="Loading Discord settings"
      error-title="Could not load Discord settings"
      :error-message="store.errorMessage"
      @retry="store.load"
    >
      <Skeleton v-for="index in 3" :key="index" class="h-10 w-full" />
    </PageLoadState>

    <form v-else class="flex flex-col gap-8" @submit.prevent="save">
      <PasswordInput
        id="discord-token"
        v-model="form.token"
        label="Bot token"
        :placeholder="tokenPlaceholder"
        autocomplete="off"
      />
      <div data-slot="settings-ids-row" class="grid gap-8 sm:gap-6 sm:grid-cols-3">
        <div class="flex flex-col gap-2">
          <Label for="discord-default-channel">Default channel ID</Label>
          <Input
            id="discord-default-channel"
            v-model="form.defaultChannelId"
            placeholder="Default channel ID"
            inputmode="numeric"
            :pattern="ID_PATTERN"
            title="17 to 20 digits"
            autocomplete="off"
          />
        </div>
        <div class="flex flex-col gap-2">
          <Label for="discord-mention-user">Mention user ID</Label>
          <Input
            id="discord-mention-user"
            v-model="form.mentionUserId"
            placeholder="Mention user ID"
            inputmode="numeric"
            :pattern="ID_PATTERN"
            title="17 to 20 digits"
            autocomplete="off"
          />
        </div>
        <div class="flex flex-col gap-2">
          <Label for="discord-max-chars">Max characters per message</Label>
          <Input
            id="discord-max-chars"
            v-model="form.maxChars"
            placeholder="Max characters"
            type="number"
            required
            min="1"
            :max="MAX_MESSAGE_CHARS"
          />
        </div>
      </div>
      <div class="flex flex-col gap-2">
        <Label :for="TEMPLATE_ID">Message template</Label>
        <Textarea
          :id="TEMPLATE_ID"
          ref="template"
          v-model="form.messageTemplate"
          placeholder="Message template"
          :aria-describedby="templateFields.length > 0 ? TEMPLATE_VARIABLES_ID : undefined"
          required
        />
        <TemplateVariables
          v-if="templateFields.length > 0"
          :id="TEMPLATE_VARIABLES_ID"
          :fields="templateFields"
          :target-id="TEMPLATE_ID"
          @insert="insertVariable"
        />
      </div>
      <div class="flex flex-wrap items-center justify-end gap-3">
        <p
          v-if="store.bot"
          role="status"
          class="mr-auto min-w-0 text-body-sm font-semibold text-accent"
        >
          Connected as {{ store.bot.name }}
        </p>
        <p v-if="store.testError" role="alert" class="mr-auto min-w-0 text-body-sm text-danger">
          {{ store.testError }}
        </p>
        <p v-if="store.saveError" role="alert" class="mr-auto min-w-0 text-body-sm text-danger">
          {{ store.saveError }}
        </p>
        <Button
          type="button"
          :disabled="store.isTesting || !store.settings?.isConfigured"
          @click="store.testConnection"
        >
          {{ store.isTesting ? 'Testing' : 'Test connection' }}
        </Button>
        <Button type="submit" variant="primary" :disabled="store.isSaving">
          {{ store.isSaving ? 'Saving' : 'Save' }}
        </Button>
      </div>
    </form>
  </PageSection>
</template>
