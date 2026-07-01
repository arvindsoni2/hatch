import '@testing-library/jest-dom';
import { vi } from 'vitest';

// @testing-library/dom uses `jest.advanceTimersByTime` when fake timers are
// detected. Vitest exposes the same API on `vi`, so we alias it here so that
// `waitFor` and other async utilities work correctly with vi.useFakeTimers().
(global as typeof globalThis & { jest: unknown }).jest = vi;

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), back: vi.fn() }),
  usePathname: () => '/',
  useSearchParams: () => new URLSearchParams(),
}));

global.fetch = vi.fn();

// matchMedia is not available in jsdom
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});
