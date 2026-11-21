import { describe, expect, it, vi } from 'vitest'
import { renderMarkdown } from '@/shared/utils/markdown'

vi.mock('markdown-it', () => ({
  default: class PassThroughMarkdown {
    disable(): this {
      return this
    }

    render(source: string): string {
      return source
    }
  },
}))

function toDom(html: string): HTMLElement {
  const root = document.createElement('div')
  root.innerHTML = html
  return root
}

function hrefs(root: HTMLElement): (string | null)[] {
  return [...root.querySelectorAll('a')].map((link) => link.getAttribute('href'))
}

describe('renderMarkdown sanitizer', () => {
  it('removes scripts, event handlers and unsafe links from raw HTML', async () => {
    const root = toDom(
      await renderMarkdown(
        [
          '<p onclick="alert(1)" style="color:red" class="x" id="y">Text</p>',
          '<script>alert(2)</script>',
          '<img src="x" onerror="alert(3)">',
          '<a href="javascript:alert(4)">js</a>',
          '<a href="JaVaScRiPt:alert(5)">mixed</a>',
          '<a href="data:text/html,<script>alert(6)</script>">data</a>',
          '<a href="/relative">relative</a>',
          '<iframe src="https://example.com"></iframe>',
          '<style>p { color: red }</style>',
          '<svg><a href="https://example.com"><text>svg</text></a></svg>',
        ].join(''),
      ),
    )

    expect(root.querySelector('script, img, iframe, style, svg')).toBeNull()
    expect(root.querySelector('[onclick], [onerror], [style], [class], [id]')).toBeNull()
    expect(hrefs(root).filter((href) => href !== null)).toEqual([])
    expect(root.querySelector('p')?.textContent).toBe('Text')
  })

  it('keeps the allowed tags and safe links', async () => {
    const source =
      '<h3>Title</h3><p>One <em>two</em> <strong>three</strong><br>four <code>five</code></p>' +
      '<ul><li>a</li></ul><ol><li>b</li></ol><blockquote>q</blockquote><pre>pre</pre>' +
      '<a href="https://example.com">https</a><a href="http://example.com">http</a>' +
      '<a href="mailto:a@example.com">mail</a>'
    const root = toDom(await renderMarkdown(source))

    expect(
      root.querySelectorAll('h3, p, em, strong, br, code, ul, ol, li, blockquote, pre'),
    ).toHaveLength(12)
    expect(hrefs(root)).toEqual([
      'https://example.com',
      'http://example.com',
      'mailto:a@example.com',
    ])
    expect(
      [...root.querySelectorAll('a')].every(
        (link) =>
          link.getAttribute('target') === '_blank' &&
          link.getAttribute('rel') === 'noopener noreferrer',
      ),
    ).toBe(true)
  })
})
