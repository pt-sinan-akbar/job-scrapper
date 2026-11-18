import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import { navItems } from '@/router/navigation'
import AppHeader from '@/shared/components/AppHeader.vue'
import { useThemeStore } from '@/shared/stores/useThemeStore'

function stubBrowser(): void {
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe = vi.fn<ResizeObserver['observe']>()
      unobserve = vi.fn<ResizeObserver['unobserve']>()
      disconnect = vi.fn<ResizeObserver['disconnect']>()
    },
  )
  vi.stubGlobal(
    'matchMedia',
    vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      addEventListener: vi.fn<MediaQueryList['addEventListener']>(),
      removeEventListener: vi.fn<MediaQueryList['removeEventListener']>(),
      addListener: vi.fn<MediaQueryList['addListener']>(),
      removeListener: vi.fn<MediaQueryList['removeListener']>(),
    })),
  )
}

const blank = { render: () => null }

async function mountHeader(canSignOut = true, path = '/runs') {
  stubBrowser()
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/runs', component: blank },
      { path: '/discord', component: blank },
    ],
  })
  router.push(path)
  await router.isReady()

  const wrapper = mount(AppHeader, {
    props: { items: navItems, canSignOut },
    global: { plugins: [router, createPinia()] },
    attachTo: document.body,
  })
  await flushPromises()
  return wrapper
}

async function openAdminMenu(): Promise<HTMLElement> {
  document.body
    .querySelector('[data-slot="dropdown-menu-trigger"]')!
    .dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))
  await flushPromises()
  return document.body.querySelector<HTMLElement>('[role="menu"]')!
}

function menuRows(menu: HTMLElement): (string | undefined)[] {
  return [...menu.querySelectorAll('[role="menuitem"], [role="menuitemradio"]')].map((row) =>
    row.textContent?.trim(),
  )
}

describe('AppHeader', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    document.body.innerHTML = ''
  })

  it('shows the Job Agent Scraper wordmark', async () => {
    const wrapper = await mountHeader()

    expect(wrapper.get('[data-slot="app-header"]').text()).toContain('Job Agent Scraper')
  })

  it('links to the Runs and Discord tabs inside the Main navigation', async () => {
    const wrapper = await mountHeader()
    const nav = wrapper.get('nav[aria-label="Main"]')

    expect(nav.findAll('a').map((link) => link.attributes('href'))).toEqual(['/runs', '/discord'])
    expect(nav.text()).toContain('Runs')
    expect(nav.text()).toContain('Discord')
    expect(nav.text()).not.toContain('Config')
  })

  it.each<[string, (string | undefined)[]]>([
    ['/runs', ['page', undefined]],
    ['/runs#config', ['page', undefined]],
    ['/discord', [undefined, 'page']],
  ])('marks only the current tab as the page on %s', async (path, expected) => {
    const wrapper = await mountHeader(true, path)

    const values = wrapper
      .get('nav[aria-label="Main"]')
      .findAll('a')
      .map((link) => link.attributes('aria-current'))
    expect(values).toEqual(expected)
  })

  it('highlights the current tab as a pill and leaves the others plain', async () => {
    const wrapper = await mountHeader(true, '/discord')
    const [runs, discord] = wrapper.get('nav[aria-label="Main"]').findAll('a')

    expect(discord!.classes()).toEqual(expect.arrayContaining(['bg-surface-subtle', 'text-ink']))
    expect(discord!.classes()).not.toContain('text-ink-muted')
    expect(runs!.classes()).toContain('text-ink-muted')
    expect(runs!.classes()).not.toContain('bg-surface-subtle')
  })

  it('moves the pill when the user switches tabs', async () => {
    const wrapper = await mountHeader()
    const links = () => wrapper.get('nav[aria-label="Main"]').findAll('a')

    await links()[1]!.trigger('click')
    await flushPromises()

    expect(links().map((link) => link.attributes('aria-current'))).toEqual([undefined, 'page'])
  })

  it('names the product in the only h1', async () => {
    const wrapper = await mountHeader()

    expect(wrapper.findAll('h1').map((heading) => heading.text())).toEqual(['Job Agent Scraper'])
  })

  it('gives the Admin trigger one accessible name', async () => {
    const wrapper = await mountHeader()

    const trigger = wrapper.get('[data-slot="dropdown-menu-trigger"]')
    expect(trigger.attributes('aria-label')).toBe('Admin menu')
    expect(trigger.find('.sr-only').exists()).toBe(false)
  })

  it('labels the account menu Admin', async () => {
    const wrapper = await mountHeader()
    const trigger = wrapper.get('[data-slot="dropdown-menu-trigger"]')

    expect(trigger.text()).toContain('Admin')
    expect(trigger.attributes('aria-expanded')).toBe('false')
  })

  it('offers the theme options and Sign out in the Admin menu', async () => {
    await mountHeader()
    const menu = await openAdminMenu()

    expect(menuRows(menu)).toEqual(['Light', 'Dark', 'System', 'Sign out'])
  })

  it('leaves Sign out out of the menu when sign-in is turned off', async () => {
    await mountHeader(false)
    const menu = await openAdminMenu()

    expect(menuRows(menu)).toEqual(['Light', 'Dark', 'System'])
    expect(menu.querySelectorAll('[data-slot="dropdown-menu-separator"]')).toHaveLength(0)
  })

  it('sets the theme chosen from the Admin menu', async () => {
    await mountHeader()
    const menu = await openAdminMenu()
    const dark = [...menu.querySelectorAll<HTMLElement>('[role="menuitemradio"]')].find(
      (option) => option.textContent?.trim() === 'Dark',
    )!

    dark.click()
    await flushPromises()

    expect(useThemeStore().mode).toBe('dark')
  })

  it('asks for confirmation before emitting signOut', async () => {
    const wrapper = await mountHeader()
    const menu = await openAdminMenu()
    const signOut = [...menu.querySelectorAll<HTMLElement>('[role="menuitem"]')].find(
      (item) => item.textContent?.trim() === 'Sign out',
    )!

    signOut.click()
    await flushPromises()
    expect(wrapper.emitted('signOut')).toBeUndefined()

    const dialog = document.body.querySelector('[role="dialog"]')!
    const confirm = [...dialog.querySelectorAll<HTMLButtonElement>('button')].find(
      (button) => button.textContent?.trim() === 'Sign out',
    )!
    confirm.click()
    await flushPromises()

    expect(wrapper.emitted('signOut')).toHaveLength(1)
  })
})
