import { describe, expect, it } from 'vitest'
import { markdownToPlainText, renderMarkdown } from '@/shared/utils/markdown'

function toDom(html: string): HTMLElement {
  const root = document.createElement('div')
  root.innerHTML = html
  return root
}

function hrefs(root: HTMLElement): (string | null)[] {
  return [...root.querySelectorAll('a')].map((link) => link.getAttribute('href'))
}

const LONG_SPACE_RUN = 15_000
const HUGE_WORD_COUNT = 100_000
const HOSTILE_REPEATS = 1_000_000
const MAX_PLAIN_TEXT_CHARS = 20_000
const SLOW_STRIP_MS = 1000

describe('markdownToPlainText', () => {
  it('strips headings', () => {
    expect(markdownToPlainText('# About us\n\n### The role ###\n\nBuild things')).toBe(
      'About us The role Build things',
    )
  })

  it('strips emphasis and strikethrough', () => {
    expect(markdownToPlainText('**Bold** and *italic* and __strong__ and _em_ and ~~old~~')).toBe(
      'Bold and italic and strong and em and old',
    )
  })

  it('keeps underscores and asterisks that are not emphasis', () => {
    expect(markdownToPlainText('Use snake_case_names and 2 * 3 * 4')).toBe(
      'Use snake_case_names and 2 * 3 * 4',
    )
  })

  it('strips list markers', () => {
    expect(markdownToPlainText('- one\n* two\n+ three\n1. four\n2) five\n  - nested')).toBe(
      'one two three four five nested',
    )
  })

  it('keeps the text of links and images', () => {
    expect(
      markdownToPlainText(
        'See [our site](https://example.com "Home") or [docs][1] ![logo](https://example.com/a.png) <https://example.com/jobs>',
      ),
    ).toBe('See our site or docs logo https://example.com/jobs')
  })

  it('strips code fences and inline code marks', () => {
    expect(
      markdownToPlainText('Run `npm test`\n\n```ts\nconst a = 1\n```\n\n~~~\nplain\n~~~'),
    ).toBe('Run npm test const a = 1 plain')
  })

  it('strips HTML tags', () => {
    expect(
      markdownToPlainText('<p>Hello <b>there</b><br/>friend</p><script>alert(1)</script>'),
    ).toBe('Hello there friend alert(1)')
  })

  it('strips quotes, rules and escapes', () => {
    expect(markdownToPlainText('> Quoted\n\n---\n\nTitle\n=====\n\n5\\+ years \\- C\\# \\*')).toBe(
      'Quoted Title 5+ years - C# *',
    )
  })

  it('collapses whitespace', () => {
    expect(markdownToPlainText('  one\n\n\n two\t\tthree \r\n four  ')).toBe('one two three four')
  })

  it('returns an empty string for blank markdown', () => {
    expect(markdownToPlainText(' \n\n ')).toBe('')
  })

  it('strips a closing heading mark after a few spaces', () => {
    expect(markdownToPlainText('## Title ##\n\nBody')).toBe('Title Body')
  })

  it('reads only the start of a huge description', () => {
    const text = markdownToPlainText('word '.repeat(HUGE_WORD_COUNT))

    expect(text.startsWith('word word')).toBe(true)
    expect(text.length).toBeLessThanOrEqual(MAX_PLAIN_TEXT_CHARS)
  })

  it.each([['['], ['<!--'], ['*a ']])('stays fast on %s repeated without a close', (piece) => {
    const startedAt = performance.now()

    markdownToPlainText(piece.repeat(HOSTILE_REPEATS))

    expect(performance.now() - startedAt).toBeLessThan(SLOW_STRIP_MS)
  })

  it('collapses a very long run of spaces', () => {
    const text = markdownToPlainText(`Title${' '.repeat(LONG_SPACE_RUN)}x`)

    expect(text).toBe('Title x')
  })
})

describe('renderMarkdown', () => {
  it('renders paragraphs, emphasis, headings and lists', async () => {
    const root = toDom(await renderMarkdown('## Role\n\nBuild **great** things\n\n- one\n- two'))

    expect(root.querySelector('h2')?.textContent).toBe('Role')
    expect(root.querySelector('p strong')?.textContent).toBe('great')
    expect([...root.querySelectorAll('ul li')].map((item) => item.textContent)).toEqual([
      'one',
      'two',
    ])
  })

  it('opens every link in a new tab without an opener', async () => {
    const root = toDom(
      await renderMarkdown('[site](https://example.com) and mail [us](mailto:jobs@example.com)'),
    )
    const links = [...root.querySelectorAll('a')]

    expect(links).toHaveLength(2)
    expect(links.map((link) => link.getAttribute('target'))).toEqual(['_blank', '_blank'])
    expect(links.map((link) => link.getAttribute('rel'))).toEqual([
      'noopener noreferrer',
      'noopener noreferrer',
    ])
    expect(hrefs(root)).toEqual(['https://example.com', 'mailto:jobs@example.com'])
  })

  it('turns bare URLs into links', async () => {
    const root = toDom(await renderMarkdown('Apply at https://example.com/apply today'))

    expect(hrefs(root)).toEqual(['https://example.com/apply'])
  })

  it('does not let a script tag, an onerror attribute or a javascript link survive', async () => {
    const html = await renderMarkdown(
      [
        'Hello <script>alert(1)</script>',
        '<img src="x" onerror="alert(2)">',
        '[click me](javascript:alert(3))',
        '<a href="javascript:alert(4)">raw link</a>',
        '![pic](https://example.com/a.png)',
      ].join('\n\n'),
    )
    const root = toDom(html)

    expect(root.querySelector('script')).toBeNull()
    expect(root.querySelector('img')).toBeNull()
    expect(root.querySelector('[onerror]')).toBeNull()
    expect(hrefs(root).filter((href) => href?.toLowerCase().includes('javascript'))).toEqual([])
    expect(root.textContent).toContain('click me')
  })

  it('renders an empty string for blank markdown', async () => {
    expect((await renderMarkdown('  \n ')).trim()).toBe('')
  })
})
