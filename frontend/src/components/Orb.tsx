/** Soft, light palettes: three blob colours and a pale base. Many of them, so neighbours rarely match. */
const PALETTES = [
  ["#ff9a8b", "#ff6a88", "#ffd29d", "#fbe3e8"],   // warm
  ["#8ec5fc", "#e0c3fc", "#a1c4fd", "#f5f7ff"],   // cool
  ["#84fab0", "#8fd3f4", "#43e97b", "#e8fff4"],   // mint-sky
  ["#fccb90", "#d57eeb", "#f6d365", "#fff4e6"],   // sunset
  ["#a18cd1", "#fbc2eb", "#6a82fb", "#f3ecff"],   // violet
  ["#f093fb", "#f5576c", "#ffc3a0", "#ffeef3"],   // rose
  ["#4facfe", "#00f2fe", "#96e6a1", "#eafcff"],   // sea
  ["#fa709a", "#fee140", "#ff9a9e", "#fff6e0"],   // citrus-pink
  ["#30cfd0", "#7b8fe0", "#a8edea", "#e6fbff"],   // lagoon
  ["#c471f5", "#fa71cd", "#7afcff", "#fbefff"],   // neon pastel
  ["#b7f8db", "#50a7c2", "#d4fc79", "#effff7"],   // mint
  ["#f9d423", "#ff9f43", "#c3f584", "#fffbe6"],   // citrus
  ["#e05780", "#b370e0", "#ffb3c6", "#fdf0f5"],   // berry
  ["#fda085", "#8e7cc3", "#f6d365", "#fdf3ee"],   // dusk
  ["#48c6ef", "#6f86d6", "#9be7d8", "#eefaff"],   // deep sea
  ["#a8c69f", "#e2d58b", "#7fb9a8", "#f5f8ee"],   // sage
  ["#ffc3a0", "#ffafbd", "#ffd6a5", "#fff5ef"],   // peach
  ["#cdb4f8", "#a0c4ff", "#ffc6ff", "#f7f3ff"],   // lavender
  ["#ff7e67", "#ffd166", "#f4978e", "#fff3ea"],   // coral
];

/** FNV-1a: the same id always gives the same seed. */
function hash(s: string): number {
  let h = 2166136261;
  for (const c of s) { h ^= c.charCodeAt(0); h = Math.imul(h, 16777619); }
  return h >>> 0;
}

/** A tiny LCG in [0, 1), seeded from the id. */
function rnd(seed: number): () => number {
  return () => { seed = (seed * 1664525 + 1013904223) >>> 0; return seed / 4294967296; };
}

const pct = (n: number) => `${n.toFixed(1)}%`;

/** The blob layer for an id, drawn in a fixed order: palette, three blobs, rotation. */
function look(id: string) {
  const r = rnd(hash(id));
  const p = PALETTES[Math.floor(r() * PALETTES.length)];
  const blob = (c: string, x: number, y: number, s: number) =>
    `radial-gradient(circle at ${pct(x)} ${pct(y)}, ${c}, transparent ${pct(s)})`;
  const background = [
    blob(p[0], 20 + r() * 30, 20 + r() * 30, 55 + r() * 15),
    blob(p[1], 50 + r() * 35, 45 + r() * 35, 50 + r() * 15),
    blob(p[2], 20 + r() * 60, 55 + r() * 30, 45 + r() * 15),
    p[3],
  ].join(", ");
  return { background, transform: `rotate(${Math.floor(r() * 360)}deg)` };
}

/** A round, grainy colour avatar for a list item, generated from its id. */
export default function Orb({ id, size = 36 }: { id: string; size?: number }) {
  const { background, transform } = look(id);
  return (
    <span className="orb" aria-hidden="true" style={{ width: size, height: size }}>
      <span className="blobs" style={{ background, transform, filter: `blur(${Math.round(size / 5)}px)` }} />
      <svg className="grain" viewBox="0 0 40 40" preserveAspectRatio="none">
        <rect width="40" height="40" filter="url(#orb-grain)" />
      </svg>
      <span className="shine" />
    </span>
  );
}

/** The one film-grain filter every orb references; render it once, near the root. */
export function OrbGrain() {
  return (
    <svg className="orb-defs" width="0" height="0" aria-hidden="true" focusable="false">
      <filter id="orb-grain">
        <feTurbulence type="fractalNoise" baseFrequency="1.1" numOctaves={2} stitchTiles="stitch" />
        <feColorMatrix type="saturate" values="0" />
      </filter>
    </svg>
  );
}
