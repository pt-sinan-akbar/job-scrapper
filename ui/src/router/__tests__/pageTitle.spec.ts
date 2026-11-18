import { beforeEach, describe, expect, it } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import { authRoutes } from '@/modules/auth/routes'
import { discordRoutes } from '@/modules/discord/routes'
import { runRoutes } from '@/modules/runs/routes'
import { installPageTitle } from '@/router/pageTitle'

const blank = { render: () => null }

function createTitledRouter() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: blank },
      { path: '/titled', component: blank, meta: { title: 'Titled' } },
      { path: '/other', component: blank, meta: { title: 'Other' } },
    ],
  })
  installPageTitle(router)
  return router
}

describe('installPageTitle', () => {
  beforeEach(() => {
    document.title = 'Loading'
  })

  it('sets the tab title to the route meta title with no brand or suffix', async () => {
    const router = createTitledRouter()

    await router.push('/titled')

    expect(document.title).toBe('Titled')
  })

  it('follows the route as the user navigates', async () => {
    const router = createTitledRouter()

    await router.push('/titled')
    await router.push('/other')

    expect(document.title).toBe('Other')
  })

  it('leaves the title alone for routes without a meta title', async () => {
    const router = createTitledRouter()

    await router.push('/titled')
    await router.push('/')

    expect(document.title).toBe('Titled')
  })
})

describe('installPageTitle on hash links', () => {
  beforeEach(() => {
    document.title = 'Loading'
  })

  it('keeps the current title when only the hash changes', async () => {
    const router = createTitledRouter()
    await router.push('/titled')
    document.title = 'Discord'

    await router.push('/titled#discord')

    expect(document.title).toBe('Discord')
  })
})

describe('route titles', () => {
  it('titles the login route Sign in', () => {
    const login = authRoutes.find((route) => route.path === '/login')

    expect(login?.meta?.title).toBe('Sign in')
  })

  it('titles the Runs tab Runs', () => {
    expect(runRoutes.find((route) => route.path === '/runs')?.meta?.title).toBe('Runs')
  })

  it('titles the Discord tab Discord', () => {
    expect(discordRoutes.find((route) => route.path === '/discord')?.meta?.title).toBe('Discord')
  })

  it.each(
    [...runRoutes, ...discordRoutes, ...authRoutes]
      .filter((route) => route.component)
      .map((route) => [route.path, route.meta?.title]),
  )('gives %s a title', (_path, title) => {
    expect(title).toBeTruthy()
  })
})
