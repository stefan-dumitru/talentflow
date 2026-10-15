const DARK_MODE_QUERY = '(prefers-color-scheme: dark)'

/**
 * Makes the page follow the operating system's light/dark setting by toggling the `dark`
 * class that Tailwind and shadcn look for. A manual toggle comes later with the app shell.
 * Returns a function that stops following the system setting.
 */
export function followSystemTheme(root: HTMLElement = document.documentElement): () => void {
  const query = window.matchMedia(DARK_MODE_QUERY)

  const apply = (prefersDark: boolean) => {
    root.classList.toggle('dark', prefersDark)
  }

  apply(query.matches)
  const onChange = (event: MediaQueryListEvent) => apply(event.matches)
  query.addEventListener('change', onChange)

  return () => query.removeEventListener('change', onChange)
}
