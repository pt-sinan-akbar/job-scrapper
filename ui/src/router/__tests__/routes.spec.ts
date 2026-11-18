import { describe, expect, it } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import { navItems } from '@/router/navigation'
import { routes } from '@/router/routes'

async function land(path: string) {
  const router = createRouter({ history: createMemoryHistory(), routes })
  await router.push(path)
  await router.isReady()
  const { path: finalPath, hash, meta } = router.currentRoute.value
  return { path: finalPath, hash, title: meta.title }
}

describe('routes', () => {
  it('opens the Runs tab at /runs', async () => {
    expect(await land('/runs')).toEqual({ path: '/runs', hash: '', title: 'Runs' })
  })

  it('opens the Discord tab at /discord', async () => {
    expect(await land('/discord')).toEqual({ path: '/discord', hash: '', title: 'Discord' })
  })

  it('sends / to the Runs tab', async () => {
    expect(await land('/')).toEqual({ path: '/runs', hash: '', title: 'Runs' })
  })

  it.each<[string, string, string]>([
    ['/#runs', '/runs', ''],
    ['/#config', '/runs', '#config'],
    ['/#discord', '/discord', ''],
    ['/#unknown', '/runs', ''],
    ['/config', '/runs', '#config'],
  ])('sends the old link %s to %s%s', async (from, path, hash) => {
    const landed = await land(from)

    expect({ path: landed.path, hash: landed.hash }).toEqual({ path, hash })
  })

  it('keeps /runs#config on the Runs tab with the config hash', async () => {
    expect(await land('/runs#config')).toEqual({ path: '/runs', hash: '#config', title: 'Runs' })
  })
})

describe('navItems', () => {
  it('shows only the Runs and Discord tabs', () => {
    expect(navItems.map(({ label, to }) => ({ label, to }))).toEqual([
      { label: 'Runs', to: '/runs' },
      { label: 'Discord', to: '/discord' },
    ])
  })
})
