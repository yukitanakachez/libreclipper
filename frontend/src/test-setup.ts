import "@testing-library/jest-dom/vitest";
import { beforeEach, vi } from "vitest";

// jsdom 30 has HTMLDialogElement but not showModal/close: polyfill only what's missing, as
// plain open/close bookkeeping. Dialog.tsx moves focus and handles Escape itself, so tests
// exercise that code, not this polyfill.
if (typeof HTMLDialogElement.prototype.showModal !== "function") {
  HTMLDialogElement.prototype.showModal = function (this: HTMLDialogElement) {
    this.setAttribute("open", "");
  };
}
if (typeof HTMLDialogElement.prototype.close !== "function") {
  HTMLDialogElement.prototype.close = function (this: HTMLDialogElement) {
    this.removeAttribute("open");
    this.dispatchEvent(new Event("close"));
  };
}

// jsdom has no media playback: give <video> a settable clock and fake play/pause.
const clock = new WeakMap<HTMLMediaElement, number>();
Object.defineProperty(HTMLMediaElement.prototype, "currentTime", {
  configurable: true,
  get(this: HTMLMediaElement) { return clock.get(this) ?? 0; },
  set(this: HTMLMediaElement, value: number) { clock.set(this, value); },
});

beforeEach(() => {
  HTMLMediaElement.prototype.play = vi.fn().mockResolvedValue(undefined);
  HTMLMediaElement.prototype.pause = vi.fn();
});

// jsdom has no WebGL: the Paper Shaders textures are decoration, so they render nothing here.
vi.mock("@paper-design/shaders-react", () => ({ MeshGradient: () => null, GrainGradient: () => null }));
