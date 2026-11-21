import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { stubClampedText } from '@/__tests__/clampedText'
import type { ScrapeJob } from '@/modules/scrapes/domain/entities/Scrape'
import { nextTick } from 'vue'
import ScrapeJobCard from '@/modules/scrapes/presentation/components/ScrapeJobCard.vue'
import { formatExactTime } from '@/modules/scrapes/presentation/components/relativeTime'

const NOW = new Date('2026-11-19T12:00:00+00:00')
const POSTED_AT = '2026-11-18T10:21:43+00:00'

const DESCRIPTION = [
  '## About the role',
  '',
  'We are looking for a **senior engineer** who enjoys shipping reliable data pipelines.',
  '',
  '- Design scraping jobs that survive layout changes',
  '- Review code from the rest of the [platform team](https://example.com/team)',
  '- Keep the on call rotation calm and well documented',
].join('\n')

const OLD_JOB: ScrapeJob = {
  site: 'jobstreet',
  matchedKeyword: null,
  title: 'ML Engineer',
  company: 'Acme',
  location: 'Remote',
  url: 'https://example.com/1',
  postedAt: POSTED_AT,
  salary: null,
  workType: null,
  employmentType: null,
  experienceLevel: null,
  description: null,
  json: {},
}

const FULL_JOB: ScrapeJob = {
  ...OLD_JOB,
  matchedKeyword: 'AI Engineering',
  salary: 'IDR 20M to 30M per month',
  workType: 'Hybrid',
  employmentType: 'Full time',
  experienceLevel: 'Senior',
  description: DESCRIPTION,
  json: { title: 'ML Engineer' },
}

function mountCard(job: Partial<ScrapeJob> = {}, isSelected = false) {
  return mount(ScrapeJobCard, {
    props: { job: { ...FULL_JOB, ...job }, isSelected },
    attachTo: document.body,
  })
}

type Wrapper = ReturnType<typeof mountCard>

function facts(wrapper: Wrapper): [string, string][] {
  const list = wrapper.get('[data-slot="job-facts"]')
  const labels = list.findAll('dt').map((node) => node.text())
  const values = list.findAll('dd').map((node) => node.text())
  return labels.map((label, index) => [label, values[index] ?? ''])
}

function toggle(wrapper: Wrapper) {
  return wrapper.get('[data-slot="job-description-toggle"]')
}

async function expand(wrapper: Wrapper): Promise<void> {
  await nextTick()
  await toggle(wrapper).trigger('click')
  await vi.waitFor(() => {
    expect(wrapper.find('[data-slot="job-description-html"]').exists()).toBe(true)
  })
}

describe('ScrapeJobCard', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(NOW)
    stubClampedText(true)
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
    document.body.innerHTML = ''
  })

  describe('title row', () => {
    it('renders an article that is not a keyboard stop itself', () => {
      const card = mountCard()

      expect(card.element.tagName).toBe('ARTICLE')
      expect(card.attributes('data-slot')).toBe('job-card')
      expect(card.attributes('role')).toBeUndefined()
      expect(card.attributes('tabindex')).toBeUndefined()
    })

    it('links the title to the job in a new tab without an opener', () => {
      const link = mountCard().get('[data-slot="job-title"] a')

      expect(link.text()).toContain('ML Engineer')
      expect(link.attributes('href')).toBe('https://example.com/1')
      expect(link.attributes('target')).toBe('_blank')
      expect(link.attributes('rel')).toBe('noopener noreferrer')
      expect(link.get('.sr-only').text()).toBe('(opens in new tab)')
    })

    it('shows a plain title when the job has no link', () => {
      const title = mountCard({ url: null }).get('[data-slot="job-title"]')

      expect(title.find('a').exists()).toBe(false)
      expect(title.text()).toBe('ML Engineer')
    })

    it('falls back to a placeholder title', () => {
      const wrapper = mountCard({ title: null })

      expect(wrapper.get('[data-slot="job-title"]').text()).toContain('Untitled job')
    })

    it('shows the site badge only when the site is known', () => {
      expect(mountCard().get('[data-slot="job-site"]').text()).toBe('jobstreet')
      expect(mountCard({ site: null }).find('[data-slot="job-site"]').exists()).toBe(false)
    })
  })

  describe('meta line', () => {
    it('joins company, location and posted time', () => {
      expect(mountCard().get('[data-slot="job-meta"]').text()).toBe('Acme · Remote · 1 day ago')
    })

    it('skips the parts that are missing', () => {
      expect(mountCard({ company: null }).get('[data-slot="job-meta"]').text()).toBe(
        'Remote · 1 day ago',
      )
      expect(
        mountCard({ location: null, postedAt: null }).get('[data-slot="job-meta"]').text(),
      ).toBe('Acme')
    })

    it('shows no meta line when every part is missing', () => {
      const wrapper = mountCard({ company: null, location: null, postedAt: null })

      expect(wrapper.find('[data-slot="job-meta"]').exists()).toBe(false)
    })

    it('shows the posted time as relative text with the exact time on hover', () => {
      const time = mountCard().get('time')

      expect(time.text()).toBe('1 day ago')
      expect(time.attributes('datetime')).toBe(POSTED_AT)
      expect(time.attributes('title')).toBe(formatExactTime(POSTED_AT))
      expect(time.attributes('title')).toContain('2026')
    })

    it('shows the raw posted text when it is not a date', () => {
      const wrapper = mountCard({ postedAt: '2 days ago' })

      expect(wrapper.find('time').exists()).toBe(false)
      expect(wrapper.get('[data-slot="job-meta"]').text()).toBe('Acme · Remote · 2 days ago')
    })
  })

  describe('facts', () => {
    it('lists every fact in a fixed order', () => {
      expect(facts(mountCard())).toEqual([
        ['Salary', 'IDR 20M to 30M per month'],
        ['Work type', 'Hybrid'],
        ['Employment', 'Full time'],
        ['Level', 'Senior'],
        ['Keyword', 'AI Engineering'],
      ])
    })

    it('uses a description list', () => {
      expect(mountCard().get('[data-slot="job-facts"]').element.tagName).toBe('DL')
    })

    it('skips the facts that are missing or blank', () => {
      const wrapper = mountCard({ salary: null, employmentType: '  ', matchedKeyword: null })

      expect(facts(wrapper)).toEqual([
        ['Work type', 'Hybrid'],
        ['Level', 'Senior'],
      ])
    })

    it('renders an old job with no facts and no description', () => {
      const wrapper = mount(ScrapeJobCard, { props: { job: OLD_JOB, isSelected: false } })

      expect(wrapper.find('dl').exists()).toBe(false)
      expect(wrapper.find('[data-slot="job-description"]').exists()).toBe(false)
      expect(wrapper.get('[data-slot="job-title"]').text()).toContain('ML Engineer')
      expect(wrapper.get('[data-slot="job-meta"]').text()).toBe('Acme · Remote · 1 day ago')
      expect(wrapper.get('[data-slot="job-site"]').text()).toBe('jobstreet')
    })

    it('renders a job that carries only the first seven fields', () => {
      const { site, matchedKeyword, title, company, location, url, postedAt } = OLD_JOB
      const legacy = { site, matchedKeyword, title, company, location, url, postedAt }
      const wrapper = mount(ScrapeJobCard, {
        props: { job: legacy as ScrapeJob, isSelected: false },
      })

      expect(wrapper.find('dl').exists()).toBe(false)
      expect(wrapper.find('[data-slot="job-description"]').exists()).toBe(false)
      expect(wrapper.get('[data-slot="job-meta"]').text()).toBe('Acme · Remote · 1 day ago')
    })
  })

  describe('selection', () => {
    it('marks the selected card', () => {
      expect(mountCard({}, true).attributes('data-selected')).toBe('true')
      expect(mountCard({}, false).attributes('data-selected')).toBeUndefined()
    })

    it('emits select when the card body is clicked', async () => {
      const wrapper = mountCard()

      await wrapper.get('[data-slot="job-meta"]').trigger('click')
      await wrapper.trigger('click')

      expect(wrapper.emitted('select')).toHaveLength(2)
    })

    it('does not emit select when the title link is clicked', async () => {
      const wrapper = mountCard()
      const link = wrapper.get('[data-slot="job-title"] a')
      link.element.addEventListener('click', (event) => event.preventDefault())

      await link.trigger('click')
      await link.get('.sr-only').trigger('click')

      expect(wrapper.emitted('select')).toBeUndefined()
    })

    it('does not emit select when the description toggle is clicked', async () => {
      const wrapper = mountCard()

      await expand(wrapper)
      await toggle(wrapper).trigger('click')

      expect(wrapper.emitted('select')).toBeUndefined()
    })

    it('does not emit select when a link inside the description is clicked', async () => {
      const wrapper = mountCard()
      await expand(wrapper)
      const link = wrapper.get('[data-slot="job-description-html"] a')
      link.element.addEventListener('click', (event) => event.preventDefault())

      await link.trigger('click')

      expect(wrapper.emitted('select')).toBeUndefined()
    })

    it('does not emit select while text in the card is being selected', async () => {
      const wrapper = mountCard()
      const meta = wrapper.get('[data-slot="job-meta"]')
      window.getSelection()?.selectAllChildren(meta.element)

      await meta.trigger('click')
      expect(wrapper.emitted('select')).toBeUndefined()

      window.getSelection()?.removeAllRanges()
      await meta.trigger('click')
      expect(wrapper.emitted('select')).toHaveLength(1)
    })

    it('shows no JSON button', () => {
      expect(mountCard().find('[data-slot="job-json"]').exists()).toBe(false)
    })
  })

  describe('description', () => {
    it('shows a clamped plain text preview with the markdown stripped', async () => {
      const wrapper = mountCard()
      await nextTick()
      const text = wrapper.get('[data-slot="job-description-text"]')

      expect(text.text()).toContain('About the role We are looking for a senior engineer who')
      expect(text.text()).toContain('platform team')
      expect(text.text()).not.toMatch(/[#*[\]]/)
      expect(text.classes()).toContain('line-clamp-3')
      expect(wrapper.find('[data-slot="job-description-html"]').exists()).toBe(false)
      expect(toggle(wrapper).text()).toBe('Show more')
      expect(toggle(wrapper).attributes('aria-expanded')).toBe('false')
    })

    it('expands to the description rendered from markdown', async () => {
      const wrapper = mountCard()

      await expand(wrapper)
      const html = wrapper.get('[data-slot="job-description-html"]')

      expect(html.get('h2').text()).toBe('About the role')
      expect(html.get('strong').text()).toBe('senior engineer')
      expect(html.findAll('li')).toHaveLength(3)
      expect(html.get('a').attributes('target')).toBe('_blank')
      expect(html.get('a').attributes('rel')).toBe('noopener noreferrer')
      expect(wrapper.find('[data-slot="job-description-text"]').exists()).toBe(false)
      expect(toggle(wrapper).text()).toBe('Show less')
      expect(toggle(wrapper).attributes('aria-expanded')).toBe('true')
    })

    it('collapses back to the clamped preview', async () => {
      const wrapper = mountCard()

      await expand(wrapper)
      await toggle(wrapper).trigger('click')

      expect(wrapper.find('[data-slot="job-description-html"]').exists()).toBe(false)
      expect(wrapper.get('[data-slot="job-description-text"]').classes()).toContain('line-clamp-3')
      expect(toggle(wrapper).text()).toBe('Show more')
      expect(toggle(wrapper).attributes('aria-expanded')).toBe('false')
    })

    it('ties the toggle to the text it controls', async () => {
      const wrapper = mountCard()
      await nextTick()
      const controlled = toggle(wrapper).attributes('aria-controls')

      expect(controlled).toBeTruthy()
      expect(wrapper.get('[data-slot="job-description-text"]').attributes('id')).toBe(controlled)
    })

    it('hides the toggle when the whole text fits in the preview', () => {
      stubClampedText(false)
      const wrapper = mountCard({ description: 'A **short** note' })

      expect(wrapper.get('[data-slot="job-description-text"]').text()).toBe('A short note')
      expect(wrapper.find('[data-slot="job-description-toggle"]').exists()).toBe(false)
    })

    it('shows no description when it is missing or blank', () => {
      expect(mountCard({ description: null }).find('[data-slot="job-description"]').exists()).toBe(
        false,
      )
      expect(
        mountCard({ description: ' \n ' }).find('[data-slot="job-description"]').exists(),
      ).toBe(false)
    })

    it('does not let unsafe markup from the description reach the page', async () => {
      const unsafe = [
        DESCRIPTION,
        '<script>window.__jobCardHacked = true</script>',
        '<img src="x" onerror="window.__jobCardHacked = true">',
        '[bad link](javascript:window.__jobCardHacked=true)',
        '<a href="javascript:window.__jobCardHacked=true">raw</a>',
        '![tracker](https://example.com/pixel.png)',
      ].join('\n\n')
      const wrapper = mountCard({ description: unsafe })

      await expand(wrapper)
      const html = wrapper.get('[data-slot="job-description-html"]')

      expect(html.find('script').exists()).toBe(false)
      expect(html.find('img').exists()).toBe(false)
      expect(html.find('[onerror]').exists()).toBe(false)
      expect(
        html.findAll('a').filter((link) => !/^https?:/.test(link.attributes('href') ?? '')),
      ).toEqual([])
      expect('__jobCardHacked' in window).toBe(false)
    })
  })
})
