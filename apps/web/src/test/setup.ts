/**
 * Vitest setup: jsdom lacks a few browser APIs that the layout and the ECharts wrapper probe for.
 *
 * `matchMedia` is always (re)defined so this never depends on which jsdom build is installed, and the
 * polyfill reports the light scheme (a stable, deterministic chart theme for assertions).
 */

import "@testing-library/jest-dom/vitest";

const mediaQueryList = (query: string) => ({
  matches: false,
  media: query,
  onchange: null,
  addListener: () => undefined,
  removeListener: () => undefined,
  addEventListener: () => undefined,
  removeEventListener: () => undefined,
  dispatchEvent: () => false,
});

if (typeof window !== "undefined") {
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    writable: true,
    value: mediaQueryList,
  });
}

if (typeof globalThis.ResizeObserver === "undefined") {
  class NoopResizeObserver {
    observe(): void {}
    unobserve(): void {}
    disconnect(): void {}
  }
  (globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = NoopResizeObserver;
}

/**
 * jsdom has no canvas backend, so ECharts/zrender would throw on `clearRect`. The chart wrapper is
 * still exercised for real (it builds options and calls setOption); only the raster backend is faked.
 */
function createCanvasContext(): unknown {
  const gradient = { addColorStop: () => undefined };
  const base: Record<string, unknown> = {
    measureText: () => ({ width: 10 }),
    createLinearGradient: () => gradient,
    createRadialGradient: () => gradient,
    createPattern: () => null,
    getImageData: () => ({ data: new Uint8ClampedArray(4), width: 1, height: 1 }),
    putImageData: () => undefined,
    setLineDash: () => undefined,
    getLineDash: () => [],
  };
  return new Proxy(base, {
    get(target, property) {
      if (property in target) return target[property as string];
      return typeof property === "string" ? () => undefined : undefined;
    },
    set(target, property, value) {
      target[property as string] = value;
      return true;
    },
  });
}

if (typeof HTMLCanvasElement !== "undefined") {
  HTMLCanvasElement.prototype.getContext = function getContext(
    this: HTMLCanvasElement,
    contextId: string,
  ): unknown {
    if (contextId === "2d") return createCanvasContext();
    return null;
  } as HTMLCanvasElement["getContext"];

  Object.defineProperty(HTMLCanvasElement.prototype, "clientWidth", { configurable: true, value: 800 });
  Object.defineProperty(HTMLCanvasElement.prototype, "clientHeight", { configurable: true, value: 400 });
}

/**
 * jsdom installs its own `AbortController`, while `fetch` comes from Node's undici, which rejects a
 * foreign `AbortSignal` (`Expected signal to be an instance of AbortSignal`). The production code is
 * correct for a browser, so the shim lives here: in tests the timeout still works (the promise race
 * in the client is unaffected), only the cancellation token is dropped.
 */
if (typeof globalThis.fetch === "function") {
  const nativeFetch = globalThis.fetch.bind(globalThis);
  globalThis.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
    if (init && "signal" in init && init.signal) {
      const { signal: _signal, ...rest } = init;
      void _signal;
      return nativeFetch(input, rest);
    }
    return nativeFetch(input, init);
  }) as typeof globalThis.fetch;
}
