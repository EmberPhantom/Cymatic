import '@testing-library/jest-dom/vitest'

const storage = new Map<string, string>()

const mockLocalStorage = {
  getItem: (key: string) => storage.get(key) ?? null,
  setItem: (key: string, value: string) => storage.set(key, value),
  removeItem: (key: string) => storage.delete(key),
  clear: () => storage.clear(),
  key: (index: number) => Array.from(storage.keys())[index] ?? null,
  get length() {
    return storage.size
  },
} as unknown as Storage

// jsdom 30 makes window.localStorage read-only getter — use defineProperty
if (typeof window !== 'undefined') {
  try {
    Object.defineProperty(window, 'localStorage', {
      value: mockLocalStorage,
      writable: true,
      configurable: true,
    })
  } catch {
    // fallback for older jsdom
    (globalThis as unknown as { localStorage: Storage }).localStorage = mockLocalStorage
  }
}
if (typeof globalThis !== 'undefined') {
  try {
    Object.defineProperty(globalThis, 'localStorage', {
      value: mockLocalStorage,
      writable: true,
      configurable: true,
    })
  } catch {
    (globalThis as unknown as { localStorage: Storage }).localStorage = mockLocalStorage
  }
}
