import "@testing-library/jest-dom/vitest";
import { afterEach, beforeEach } from "vitest";

// Mantine reads these browser APIs; jsdom has neither.
if (typeof window.matchMedia !== "function") {
  window.matchMedia = (query: string): MediaQueryList =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      addListener: () => undefined,
      removeListener: () => undefined,
      dispatchEvent: () => false,
    }) as MediaQueryList;
}
class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
globalThis.ResizeObserver ??= ResizeObserverStub as unknown as typeof ResizeObserver;
if (typeof window.HTMLElement.prototype.scrollIntoView !== "function") {
  window.HTMLElement.prototype.scrollIntoView = () => undefined;
}

// The address hash is the route; keep tests independent of each other.
beforeEach(() => {
  window.location.hash = "";
});
afterEach(() => {
  window.location.hash = "";
});
