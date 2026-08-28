import "@testing-library/jest-dom/vitest";

if (!Element.prototype.scrollIntoView) Element.prototype.scrollIntoView = vi.fn();
if (!URL.createObjectURL) URL.createObjectURL = vi.fn(() => "blob:test");
if (!URL.revokeObjectURL) URL.revokeObjectURL = vi.fn();

afterEach(() => {
  document.body.innerHTML = "";
  window.sessionStorage.clear();
  vi.restoreAllMocks();
});
