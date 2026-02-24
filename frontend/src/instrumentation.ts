/**
 * Next.js instrumentation hook — runs once when the server starts.
 *
 * Node.js 22+ exposes a global `localStorage` that is NOT the Web Storage API.
 * Its `getItem`/`setItem` methods are missing or broken unless
 * `--localstorage-file` is supplied, which crashes libraries (SWR, etc.)
 * that feature-detect `localStorage` during SSR.
 *
 * Fix: replace it with a no-op shim so server-side code never throws.
 */
export async function register() {
  if (typeof window === "undefined") {
    // Running on the server — patch the broken global
    const noop = () => null;
    (globalThis as Record<string, unknown>).localStorage = {
      getItem: noop,
      setItem: noop,
      removeItem: noop,
      clear: noop,
      key: noop,
      length: 0,
    };
  }
}
