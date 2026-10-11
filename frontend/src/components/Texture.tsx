import { GrainGradient, MeshGradient } from "@paper-design/shaders-react";
import { useEffect, useRef, useSyncExternalStore, type ComponentProps, type RefObject } from "react";

/** The element a shader mounts on, taken from the component's own `ref` prop. */
type ShaderElement = Extract<ComponentProps<typeof MeshGradient>["ref"], RefObject<unknown>> extends RefObject<infer T>
  ? NonNullable<T> : never;

const QUERY = "(prefers-reduced-motion: reduce)";
const subscribe = (cb: () => void) => {
  const mq = window.matchMedia?.(QUERY);
  mq?.addEventListener("change", cb);
  return () => mq?.removeEventListener("change", cb);
};
/** Whether the textures may move: never under reduced motion. */
function useMotion(): boolean {
  return useSyncExternalStore(subscribe, () => !window.matchMedia?.(QUERY).matches, () => false);
}

// Paper Shaders (WebGL). All of them are decoration: hidden from assistive tech, never
// focusable, and sized by their CSS class. Colours stay within a pale, cool blue.
const FILL = { width: "100%", height: "100%" } as const;

/**
 * Makes a shader answer the pointer: its centre leans towards the cursor (by up to `reach`, in
 * the shader's own -1…1 offset units) and its flow quickens while the cursor moves, then
 * settles back to `rest`. Written straight to the shader's uniforms, so React never re-renders;
 * the frame loop runs only while something is still easing. Off under reduced motion.
 */
function usePointerDrift(rest: number, reach: number) {
  const ref = useRef<ShaderElement>(null);
  const motion = useMotion();
  useEffect(() => {
    if (!motion) return;
    let raf = 0, x = 0, y = 0, toX = 0, toY = 0, energy = 0;
    const tick = () => {
      raf = 0;
      x += (toX - x) * 0.06;
      y += (toY - y) * 0.06;
      energy *= 0.94;
      const mount = ref.current?.paperShaderMount;
      const moving = Math.abs(toX - x) + Math.abs(toY - y) > 0.0005 || energy > 0.01;
      mount?.setUniforms({ u_offsetX: x, u_offsetY: y });
      mount?.setSpeed(moving ? rest + energy : rest);
      if (moving) raf = requestAnimationFrame(tick);
    };
    const onMove = (e: PointerEvent) => {
      toX = (e.clientX / window.innerWidth - 0.5) * reach;
      toY = (e.clientY / window.innerHeight - 0.5) * reach;
      energy = Math.min(1.2, energy + Math.hypot(e.movementX, e.movementY) * 0.004);
      if (!raf) raf = requestAnimationFrame(tick);
    };
    window.addEventListener("pointermove", onMove, { passive: true });
    return () => {
      window.removeEventListener("pointermove", onMove);
      cancelAnimationFrame(raf);
    };
  }, [motion, rest, reach]);
  return { ref, speed: motion ? rest : 0 };
}

/** What the whole app sits on: a soft mesh of pale blues that leans towards the pointer. */
export function Backdrop() {
  const { ref, speed } = usePointerDrift(0.12, 0.5);
  return (
    <div className="backdrop" aria-hidden="true">
      <MeshGradient ref={ref} style={FILL} speed={speed} maxPixelCount={1280 * 800}
                    colors={["#f3f6fc", "#d9e5fb", "#eef2f9", "#c9d9f8", "#f7f9fd"]}
                    distortion={0.7} swirl={0.3} grainMixer={0} grainOverlay={0} scale={1.3} />
    </div>
  );
}

/** A grainy wash of blue behind the Next up panel: it drifts slowly, and leans with the pointer too. */
export function HeroTexture() {
  const { ref, speed } = usePointerDrift(0.18, 0.3);
  return (
    <div className="texture" aria-hidden="true">
      <GrainGradient ref={ref} style={FILL} shape="wave" speed={speed} maxPixelCount={1600 * 480}
                     colorBack="#f3f7ff" colors={["#dfe9ff", "#c9dbff", "#eef3ff"]}
                     softness={0.85} intensity={0.3} noise={0.3} scale={1.6} />
    </div>
  );
}
