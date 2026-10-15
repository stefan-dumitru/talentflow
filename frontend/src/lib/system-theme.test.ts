import { afterEach, describe, expect, it, vi } from 'vitest'
import { followSystemTheme } from './system-theme'

// jsdom has no matchMedia, so build a minimal stand-in whose "dark" setting a test can flip.
function stubSystemTheme(initiallyDark: boolean) {
  let changeListener: ((event: MediaQueryListEvent) => void) | undefined
  const query = {
    matches: initiallyDark,
    addEventListener: vi.fn((_type: string, listener: (event: MediaQueryListEvent) => void) => {
      changeListener = listener
    }),
    removeEventListener: vi.fn(),
  }
  vi.stubGlobal('matchMedia', vi.fn(() => query))
  return {
    query,
    switchTo(dark: boolean) {
      changeListener?.({ matches: dark } as MediaQueryListEvent)
    },
  }
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('followSystemTheme', () => {
  it('applies the dark class when the system is already dark', () => {
    stubSystemTheme(true)
    const root = document.createElement('div')

    followSystemTheme(root)

    expect(root).toHaveClass('dark')
  })

  it('leaves the dark class off when the system is light', () => {
    stubSystemTheme(false)
    const root = document.createElement('div')

    followSystemTheme(root)

    expect(root).not.toHaveClass('dark')
  })

  it('follows the system when it changes later', () => {
    const system = stubSystemTheme(false)
    const root = document.createElement('div')
    followSystemTheme(root)

    system.switchTo(true)
    expect(root).toHaveClass('dark')

    system.switchTo(false)
    expect(root).not.toHaveClass('dark')
  })

  it('stops listening once the returned cleanup function is called', () => {
    const system = stubSystemTheme(false)

    const stop = followSystemTheme(document.createElement('div'))
    stop()

    expect(system.query.removeEventListener).toHaveBeenCalledTimes(1)
  })
})
