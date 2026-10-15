import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { SystemStatus } from './SystemStatus'

function respondWith(status: number) {
  return Promise.resolve(new Response(JSON.stringify({ status: 'x' }), { status }))
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('SystemStatus', () => {
  it('shows a checking state while the request is in flight', () => {
    // A promise that never settles keeps the component in its loading state.
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})))

    render(<SystemStatus />)

    expect(screen.getByRole('status')).toHaveTextContent('Checking…')
    expect(screen.getByRole('button', { name: 'Retry' })).toBeDisabled()
  })

  it('shows ready when the API reports it is ready', async () => {
    vi.stubGlobal('fetch', vi.fn(() => respondWith(200)))

    render(<SystemStatus />)

    expect(await screen.findByText('API and database ready')).toBeInTheDocument()
  })

  it('shows unavailable when the API answers 503 (database down)', async () => {
    vi.stubGlobal('fetch', vi.fn(() => respondWith(503)))

    render(<SystemStatus />)

    expect(await screen.findByText('API unavailable')).toBeInTheDocument()
  })

  it('shows unavailable when the API cannot be reached at all', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new TypeError('Failed to fetch'))))

    render(<SystemStatus />)

    expect(await screen.findByText('API unavailable')).toBeInTheDocument()
  })

  it('checks again when Retry is clicked and recovers once the API is back', async () => {
    const fetchMock = vi
      .fn()
      .mockImplementationOnce(() => respondWith(503))
      .mockImplementationOnce(() => respondWith(200))
    vi.stubGlobal('fetch', fetchMock)

    render(<SystemStatus />)
    await screen.findByText('API unavailable')

    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))

    expect(await screen.findByText('API and database ready')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })
})
