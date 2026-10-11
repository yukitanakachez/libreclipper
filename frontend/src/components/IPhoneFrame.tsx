import { useLayoutEffect, useRef, useState, type ReactNode } from "react";

const PHONE_W = 428;
const PHONE_H = 868;
/** Room kept under the phone for `below` (e.g. the Source · Rendered tabs): 12 px gap + 32 px row. */
const BELOW_GAP = 12;
const BELOW_H = 32;

/**
 * devices.css iPhone 14 Pro (MIT), scaled to fit its box: the box's height sets the size, and
 * a box squeezed narrower than that (a small window) shrinks the phone instead of overflowing.
 */
export default function IPhoneFrame({ children, screenRef, below }: {
  children?: ReactNode; screenRef?: (el: HTMLDivElement | null) => void; below?: ReactNode;
}) {
  const box = useRef<HTMLDivElement>(null);
  const [fit, setFit] = useState({ scale: 1, left: 0 });
  const hasBelow = below !== undefined && below !== null;
  useLayoutEffect(() => {
    const el = box.current;
    if (!el) return;
    const measure = () => {
      const h = el.clientHeight - (hasBelow ? BELOW_GAP + BELOW_H : 0);
      const w = el.clientWidth;
      // 0 means "not laid out" (jsdom, a hidden tab): ignore that side rather than vanish.
      const scale = Math.min(h > 0 ? h / PHONE_H : Infinity, w > 0 ? w / PHONE_W : Infinity);
      const s = Number.isFinite(scale) ? scale : 1;
      setFit({ scale: s, left: w > 0 ? Math.max(0, (w - PHONE_W * s) / 2) : 0 });
    };
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [hasBelow]);
  return (
    <div className="phone-box" ref={box}>
      <div className="device device-iphone-14-pro device-spacegray"
           style={{ transform: `scale(${fit.scale})`, left: fit.left }}>
        <div className="device-frame">
          <div className="device-screen" ref={screenRef}>{children}</div>
        </div>
        <div className="device-stripe" /><div className="device-header" /><div className="device-sensors" />
        <div className="device-btns" /><div className="device-power" /><div className="device-home" />
      </div>
      {hasBelow && (
        <div className="phone-below"
             style={{ top: PHONE_H * fit.scale + BELOW_GAP, left: fit.left, width: PHONE_W * fit.scale }}>
          {below}
        </div>
      )}
    </div>
  );
}
