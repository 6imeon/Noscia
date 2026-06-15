import { afterEach, expect, test, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import App from './App'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  localStorage.clear()
})

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), { headers: { 'content-type': 'application/json' } })
}

// Route the stubbed fetch by URL fragment; anything unmatched returns {}.
function stubFetch(routes: Array<[string, unknown]>) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      const u = String(url)
      for (const [frag, body] of routes) if (u.includes(frag)) return json(body)
      return json({})
    }),
  )
}

const HEALTH = { status: 'ok', db: true, version: '0.1.0' }
const PROVIDERS = { providers: [], default_provider: 'openrouter', default_tier: 'quality' }

test('a loaded+active vertical boots straight to the search view (no gate)', async () => {
  stubFetch([
    ['/health', HEALTH],
    ['/providers', PROVIDERS],
    [
      '/industries',
      {
        industries: [{ id: 'esg', label: 'ESG', blurb: 'b', icon: 'leaf', active: true, loaded: true }],
        active: 'esg',
      },
    ],
  ])
  render(<App />)
  // boot resolves async → the rail + search bar appear, no setup modal
  expect(await screen.findByPlaceholderText(/search the esg corpus/i)).toBeInTheDocument()
  expect(screen.getByLabelText('Settings')).toBeInTheDocument()
  expect(screen.queryByText(/choose a field/i)).not.toBeInTheDocument()
})

test('a not-yet-loaded active vertical shows the setup gate', async () => {
  stubFetch([
    ['/health', HEALTH],
    ['/providers', PROVIDERS],
    [
      '/industries',
      {
        industries: [{ id: 'esg', label: 'ESG', blurb: 'b', icon: 'leaf', active: true, loaded: false }],
        active: 'esg',
      },
    ],
  ])
  render(<App />)
  expect(await screen.findByText(/choose a field/i)).toBeInTheDocument()
  expect(screen.queryByPlaceholderText(/search the esg corpus/i)).not.toBeInTheDocument()
})

test('a stored choice skips the gate and lands on search', async () => {
  localStorage.setItem('noscia.industry', 'esg')
  stubFetch([
    ['/health', HEALTH],
    ['/providers', PROVIDERS],
    ['/industries', { industries: [], active: 'esg' }],
  ])
  render(<App />)
  expect(await screen.findByPlaceholderText(/search the esg corpus/i)).toBeInTheDocument()
})
