import '@testing-library/jest-dom'

// ResizeObserver polyfill for jsdom
globalThis.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

// scrollIntoView polyfill for jsdom
Element.prototype.scrollIntoView = function () {}
