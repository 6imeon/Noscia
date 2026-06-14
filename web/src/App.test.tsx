import { afterEach, expect, test, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import App from './App'

afterEach(cleanup)

// /health is polled on mount; stub fetch so the shell renders deterministically.
vi.stubGlobal(
  'fetch',
  vi.fn(async () =>
    new Response(JSON.stringify({ status: 'ok', db: true, version: '0.1.0' }), {
      headers: { 'content-type': 'application/json' },
    }),
  ),
)

test('renders the shell with the rail and search view', () => {
  render(<App />)
  expect(screen.getByLabelText('Search')).toBeInTheDocument()
  expect(screen.getByLabelText('Settings')).toBeInTheDocument()
  expect(screen.getByPlaceholderText(/search the esg corpus/i)).toBeInTheDocument()
})
