import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import { provideAuthUseCases } from '@/modules/auth/presentation/stores/authUseCases'
import LoginPage from '@/modules/auth/presentation/pages/LoginPage.vue'

const getSession = { execute: vi.fn() }
const login = { execute: vi.fn() }
const logout = { execute: vi.fn() }

async function mountLogin() {
  const blank = { render: () => null }
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/login', component: LoginPage },
      { path: '/', component: blank },
    ],
  })
  router.push('/login')
  await router.isReady()
  const wrapper = mount(LoginPage, {
    global: { plugins: [router, createPinia()] },
    attachTo: document.body,
  })
  return { wrapper, router }
}

function submitButton(wrapper: Awaited<ReturnType<typeof mountLogin>>['wrapper']) {
  return wrapper.get('button[type="submit"]')
}

function deferLogin(): () => void {
  const release = vi.fn<() => void>()
  const pending = new Promise<void>((resolve) => {
    release.mockImplementation(resolve)
  })
  login.execute.mockReturnValue(pending)
  return release
}

describe('LoginPage', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    vi.stubGlobal(
      'matchMedia',
      vi.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        addEventListener: vi.fn<MediaQueryList['addEventListener']>(),
        removeEventListener: vi.fn<MediaQueryList['removeEventListener']>(),
      })),
    )
    provideAuthUseCases({ getSession, login, logout })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    document.body.innerHTML = ''
  })

  it('titles the page Sign in without repeating the product name', async () => {
    const { wrapper } = await mountLogin()

    const heading = wrapper.get('h1')

    expect(heading.text()).toBe('Sign in')
  })

  it('hints what to type inside the password input', async () => {
    const { wrapper } = await mountLogin()

    const placeholder = wrapper.get('input').attributes('placeholder')

    expect(placeholder).toBe('Enter your password')
  })

  it('keeps Sign in disabled until a password is typed', async () => {
    const { wrapper } = await mountLogin()

    expect(submitButton(wrapper).attributes('disabled')).toBeDefined()
    await wrapper.get('input').setValue('secret')
    expect(submitButton(wrapper).attributes('disabled')).toBeUndefined()
  })

  it('shows and hides the password', async () => {
    const { wrapper } = await mountLogin()
    const input = wrapper.get('input')
    const toggle = wrapper.get('button[aria-controls]')

    expect(input.attributes('type')).toBe('password')
    await toggle.trigger('click')
    expect(input.attributes('type')).toBe('text')
    expect(toggle.text()).toContain('Hide')
  })

  it('shows the error under the form after a wrong password', async () => {
    login.execute.mockRejectedValue(new Error('Wrong password.'))
    const { wrapper } = await mountLogin()

    await wrapper.get('input').setValue('nope')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toBe('Wrong password.')
    expect(wrapper.get('input').attributes('aria-invalid')).toBe('true')
  })

  it('ties the error banner to the password input for screen readers', async () => {
    login.execute.mockRejectedValue(new Error('Wrong password.'))
    const { wrapper } = await mountLogin()

    await wrapper.get('input').setValue('nope')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    const bannerId = wrapper.get('[role="alert"]').attributes('id')
    const describedBy = wrapper.get('input').attributes('aria-describedby') ?? ''
    expect(bannerId).toBeTruthy()
    expect(describedBy.split(' ')).toContain(bannerId)
  })

  it('does not describe the password input by an error before any sign-in', async () => {
    const { wrapper } = await mountLogin()

    const describedBy = wrapper.get('input').attributes('aria-describedby')

    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(describedBy).toBeUndefined()
  })

  it('disables the button and reads Signing in while a sign-in is pending', async () => {
    const resolveLogin = deferLogin()
    const { wrapper, router } = await mountLogin()

    await wrapper.get('input').setValue('secret')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(submitButton(wrapper).attributes('disabled')).toBeDefined()
    expect(submitButton(wrapper).text()).toBe('Signing in')
    expect(wrapper.get('form').attributes('aria-busy')).toBe('true')

    resolveLogin()
    await flushPromises()

    expect(router.currentRoute.value.path).toBe('/')
  })

  it('reads Sign in again after a wrong password', async () => {
    login.execute.mockRejectedValue(new Error('Wrong password.'))
    const { wrapper } = await mountLogin()

    await wrapper.get('input').setValue('nope')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(submitButton(wrapper).text()).toBe('Sign in')
    expect(submitButton(wrapper).attributes('disabled')).toBeUndefined()
  })

  it('returns focus to the password input with its text selected after a wrong password', async () => {
    login.execute.mockRejectedValue(new Error('Wrong password.'))
    const { wrapper } = await mountLogin()
    const input = wrapper.get('input').element

    await wrapper.get('input').setValue('nope')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(document.activeElement).toBe(input)
    expect(input.selectionStart).toBe(0)
    expect(input.selectionEnd).toBe('nope'.length)
  })

  it('focuses the password input when the page opens', async () => {
    const { wrapper } = await mountLogin()
    await flushPromises()

    expect(document.activeElement).toBe(wrapper.get('input').element)
  })

  it('signs in once when the form is submitted twice while a sign-in is pending', async () => {
    const resolveLogin = deferLogin()
    const { wrapper } = await mountLogin()

    await wrapper.get('input').setValue('secret')
    await wrapper.get('form').trigger('submit')
    await wrapper.get('form').trigger('submit')
    resolveLogin()
    await flushPromises()

    expect(login.execute).toHaveBeenCalledTimes(1)
  })

  it('does not sign in when the form is submitted with an empty password', async () => {
    const { wrapper } = await mountLogin()

    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(login.execute).not.toHaveBeenCalled()
  })

  it('says so when the page after a right password does not open', async () => {
    login.execute.mockResolvedValue(undefined)
    const { wrapper, router } = await mountLogin()
    vi.spyOn(router, 'push').mockRejectedValueOnce(new Error('Failed to load page'))

    await wrapper.get('input').setValue('secret')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toBe(
      'Signed in, but the page did not open. Reload to continue',
    )
    expect(wrapper.get('input').attributes('aria-invalid')).toBeUndefined()
    expect(submitButton(wrapper).text()).toBe('Sign in')
  })

  it('goes to Runs after a right password', async () => {
    login.execute.mockResolvedValue(undefined)
    const { wrapper, router } = await mountLogin()

    await wrapper.get('input').setValue('secret')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(login.execute).toHaveBeenCalledWith('secret')
    expect(router.currentRoute.value.path).toBe('/')
  })
})
