<script setup lang="ts">
import { computed, nextTick, onMounted, ref, useId, useTemplateRef } from 'vue'
import { useRouter } from 'vue-router'
import { CircleAlert, LoaderCircle } from '@lucide/vue'
import AuthLayout from '@/modules/auth/presentation/components/AuthLayout.vue'
import { useAuthStore } from '@/modules/auth/presentation/stores/useAuthStore'
import PasswordInput from '@/shared/components/PasswordInput.vue'
import { Button } from '@/shared/components/ui/button'

const HOME_PATH = '/'
const FIELD_NAME = 'password'
const NAVIGATION_ERROR_MESSAGE = 'Signed in, but the page did not open. Reload to continue'

const auth = useAuthStore()
const router = useRouter()
const errorId = useId()
const formRef = useTemplateRef<HTMLFormElement>('form')
const password = ref('')
const isSubmitting = ref(false)
const navigationError = ref<string | null>(null)

const isPasswordInvalid = computed(() => auth.errorMessage !== null)
const errorMessage = computed(() => auth.errorMessage ?? navigationError.value)
const isSubmitDisabled = computed(() => password.value === '' || isSubmitting.value)

async function focusPassword(): Promise<void> {
  await nextTick()
  const field = formRef.value?.elements.namedItem(FIELD_NAME)
  if (field instanceof HTMLInputElement) {
    field.focus()
    field.select()
  }
}

async function openHome(): Promise<boolean> {
  try {
    await router.push(HOME_PATH)
    return true
  } catch {
    navigationError.value = NAVIGATION_ERROR_MESSAGE
    return false
  }
}

async function signIn(): Promise<boolean> {
  isSubmitting.value = true
  navigationError.value = null
  try {
    const isSignedIn = await auth.login(password.value)
    return isSignedIn && (await openHome())
  } finally {
    isSubmitting.value = false
  }
}

async function submit(): Promise<void> {
  if (isSubmitDisabled.value) {
    return
  }
  const isDone = await signIn()
  if (!isDone) {
    await focusPassword()
  }
}

onMounted(focusPassword)
</script>

<template>
  <AuthLayout>
    <h1 class="text-title text-ink">Sign in</h1>
    <form ref="form" class="flex flex-col gap-4" :aria-busy="isSubmitting" @submit.prevent="submit">
      <PasswordInput
        v-model="password"
        label="Password"
        is-label-hidden
        :name="FIELD_NAME"
        placeholder="Enter your password"
        autocomplete="current-password"
        required
        :is-invalid="isPasswordInvalid"
        :described-by="errorMessage ? errorId : undefined"
      />
      <p
        v-if="errorMessage"
        :id="errorId"
        role="alert"
        class="flex items-start gap-2 rounded-md bg-danger-soft px-3 py-2 text-body-sm text-danger"
      >
        <CircleAlert class="mt-0.5 size-5 shrink-0" aria-hidden="true" />
        <span>{{ errorMessage }}</span>
      </p>
      <Button type="submit" variant="primary" class="w-full" :disabled="isSubmitDisabled">
        <LoaderCircle v-if="isSubmitting" class="animate-spin" aria-hidden="true" />
        {{ isSubmitting ? 'Signing in' : 'Sign in' }}
      </Button>
    </form>
  </AuthLayout>
</template>
