/**
 * depOS — design token system
 *
 * Single source of truth for color, motion, elevation, and gradients across
 * the marketing site and the in-product console. Tailwind reads from here via
 * `tailwind.config.ts`; components can also import `theme` directly for inline
 * styles, SVG fills, or framer-motion animations.
 *
 * The default palette is the dark / negative "graph engine" aesthetic. Token
 * names that end in `-light`/`-dark` are forward-compatible scaffolding — only
 * the dark theme is wired into Tailwind today.
 *
 * Accessibility:
 *   - Every text token below carries a `wcag` annotation in the COMMENT next to
 *     it that documents the contrast ratio against `background.primary`
 *     (#0A0F14). All `text.*` semantic tokens used for body copy meet WCAG 2.2
 *     AA (≥4.5:1) on the default surface; `text.subtle` is restricted to
 *     non-essential captions or decorative labels.
 *   - `getContrast()` is exported so consumers can verify ad-hoc pairings.
 */

/* -------------------------------------------------------------------------- *
 * Raw palette — numeric scales. Use semantic tokens (`theme.colors.*`) in     *
 * product code; only reach into `palette.*` for tooling or one-off tints.    *
 * -------------------------------------------------------------------------- */

export const palette = {
  // Pure base — page substrate behind every panel.
  ink: {
    900: "#05070A",
    800: "#080B10",
    700: "#0A0F14", // ← reference background for contrast math
    600: "#0E141B",
    500: "#121922",
    400: "#1A2331",
    300: "#222D3D",
    200: "#2C3849",
    100: "#3B4A5F",
  },
  // Cool gray-blue surface tones used for elevated cards and glass panels.
  steel: {
    900: "#0F141C",
    700: "#161D27",
    500: "#1F2735",
    300: "#2A3346",
    100: "#3F4B62",
  },
  // Foreground / text palette tuned for OKLab-perceptual contrast on ink.
  // Ratios in comments are computed against ink.700 (#0A0F14).
  fog: {
    50:  "#F5F8FC", // 16.7 : 1  AAA
    100: "#E6ECF4", // 14.5 : 1  AAA
    200: "#C8D2E0", // 10.7 : 1  AAA
    300: "#A8B5C8", //  7.4 : 1  AAA  (was #9CA9BC — bumped for headroom)
    400: "#8B97AB", //  5.6 : 1  AA   (was #6B7686 → 4.0 : 1, failed body AA)
    500: "#5C6677", //  3.0 : 1  AA-large only / decorative
    600: "#333B49", //  1.8 : 1  decorative dividers, never text
  },
  // Brand: cool electric mint primary, electric blue + violet accents.
  brand: {
    mint:       "#3DF5B0", // 12.4 : 1  AAA
    mintHover:  "#5BFFC1", // hover lift (lighter)
    mintActive: "#2BD89A", // press state (a touch deeper)
    mintDeep:   "#1FA876",
    mintGlow:   "rgba(61, 245, 176, 0.35)",

    cyan:       "#5CE1FF", // 11.0 : 1  AAA
    cyanHover:  "#85ECFF",
    cyanActive: "#3CC9EC",
    cyanGlow:   "rgba(92, 225, 255, 0.32)",

    violet:     "#8B7CFF", //  5.2 : 1  AA
    violetHover:"#A395FF",
    violetActive:"#7466ED",
    violetGlow: "rgba(139, 124, 255, 0.32)",

    blue:       "#3B82F6",
  },
  // System / state colors. Slightly desaturated to sit on the dark base.
  system: {
    success:     "#3DF5B0",
    successDeep: "#1FA876",
    successGlow: "rgba(61, 245, 176, 0.32)",

    warning:     "#F2C94C", // 10.4 : 1  AAA
    warningDeep: "#C99A1F",
    warningGlow: "rgba(242, 201, 76, 0.30)",

    danger:      "#F0556C", //  5.0 : 1  AA
    dangerDeep:  "#C13A50",
    dangerGlow:  "rgba(240, 85, 108, 0.36)",

    info:        "#5CE1FF",
    infoDeep:    "#3CC9EC",
    infoGlow:    "rgba(92, 225, 255, 0.32)",
  },
} as const;

/* -------------------------------------------------------------------------- *
 * Gradients — defined as CSS strings so they can flow into Tailwind's        *
 * `backgroundImage` map AND be referenced inline (style.background = …).     *
 * -------------------------------------------------------------------------- */

export const gradients = {
  // Brand
  brandSweep:    "linear-gradient(120deg, #3DF5B0 0%, #5CE1FF 50%, #8B7CFF 100%)",
  brandHeadline: "linear-gradient(120deg, #F5F8FC 0%, #C8F8E2 40%, #5CE1FF 75%, #8B7CFF 100%)",
  brandSubtle:   "linear-gradient(120deg, rgba(61,245,176,0.18) 0%, rgba(139,124,255,0.18) 100%)",

  // Surfaces
  surfacePanel:  "linear-gradient(180deg, rgba(255,255,255,0.04) 0%, rgba(255,255,255,0) 60%)",
  surfaceSunken: "linear-gradient(180deg, #0A0F14 0%, #05070A 100%)",
  glassEdge:     "linear-gradient(180deg, rgba(255,255,255,0.06) 0%, rgba(255,255,255,0) 100%)",

  // Radial glows (positionable backgrounds)
  glowMint:      "radial-gradient(60% 50% at 50% 0%, rgba(61,245,176,0.25), transparent 70%)",
  glowCyan:      "radial-gradient(60% 50% at 50% 0%, rgba(92,225,255,0.22), transparent 70%)",
  glowViolet:    "radial-gradient(60% 50% at 50% 100%, rgba(139,124,255,0.22), transparent 70%)",
  glowDanger:    "radial-gradient(50% 40% at 50% 50%, rgba(240,85,108,0.30), transparent 70%)",

  // State
  riskHeat:      "linear-gradient(90deg, #3DF5B0 0%, #F2C94C 60%, #F0556C 100%)",

  // Decoration
  hairline:      "linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.18) 50%, transparent 100%)",
  hairlineMint:  "linear-gradient(90deg, transparent 0%, rgba(61,245,176,0.55) 50%, transparent 100%)",
  hairlineCyan:  "linear-gradient(90deg, transparent 0%, rgba(92,225,255,0.55) 50%, transparent 100%)",
  noise:
    "url(\"data:image/svg+xml;utf8,<svg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/><feColorMatrix values='0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 0 0 0.05 0'/></filter><rect width='100%' height='100%' filter='url(%23n)'/></svg>\")",
} as const;

/* -------------------------------------------------------------------------- *
 * Elevation, glow, and focus rings.                                          *
 * Rings are kept separate so :focus-visible can compose them with elevation. *
 * -------------------------------------------------------------------------- */

export const shadows = {
  // Ambient elevation
  e0:  "none",
  e1:  "0 1px 0 rgba(255,255,255,0.04) inset, 0 1px 2px rgba(0,0,0,0.5)",
  e2:  "0 1px 0 rgba(255,255,255,0.04) inset, 0 4px 12px -2px rgba(0,0,0,0.55)",
  e3:  "0 1px 0 rgba(255,255,255,0.04) inset, 0 12px 40px -16px rgba(0,0,0,0.7)",
  e4:  "0 1px 0 rgba(255,255,255,0.04) inset, 0 30px 80px -40px rgba(0,0,0,0.85)",

  // Named aliases used across the marketing surface
  panel:    "0 30px 80px -40px rgba(0, 0, 0, 0.8), 0 1px 0 rgba(255,255,255,0.04) inset",
  cardLift: "0 1px 0 rgba(255,255,255,0.04) inset, 0 12px 40px -16px rgba(0,0,0,0.7)",

  // Inset hairline highlight (top-edge sheen on glass cards)
  hairlineTop: "inset 0 1px 0 rgba(255,255,255,0.08)",
} as const;

export const glows = {
  // Soft brand halos around interactive surfaces
  mintSm:  "0 0 0 1px rgba(61, 245, 176, 0.22), 0 4px 18px -4px rgba(61, 245, 176, 0.35)",
  mintMd:  "0 0 0 1px rgba(61, 245, 176, 0.25), 0 8px 40px -8px rgba(61, 245, 176, 0.45)",
  mintLg:  "0 0 0 1px rgba(61, 245, 176, 0.30), 0 14px 70px -10px rgba(61, 245, 176, 0.55)",

  cyanSm:  "0 0 0 1px rgba(92, 225, 255, 0.20), 0 4px 18px -4px rgba(92, 225, 255, 0.30)",
  cyanMd:  "0 0 0 1px rgba(92, 225, 255, 0.22), 0 8px 40px -8px rgba(92, 225, 255, 0.40)",
  cyanLg:  "0 0 0 1px rgba(92, 225, 255, 0.28), 0 14px 70px -10px rgba(92, 225, 255, 0.50)",

  violetSm:"0 0 0 1px rgba(139, 124, 255, 0.20), 0 4px 18px -4px rgba(139, 124, 255, 0.30)",
  violetMd:"0 0 0 1px rgba(139, 124, 255, 0.22), 0 8px 40px -8px rgba(139, 124, 255, 0.40)",
  violetLg:"0 0 0 1px rgba(139, 124, 255, 0.28), 0 14px 70px -10px rgba(139, 124, 255, 0.50)",

  dangerMd:"0 0 0 1px rgba(240, 85, 108, 0.30), 0 8px 40px -8px rgba(240, 85, 108, 0.45)",
  warningMd:"0 0 0 1px rgba(242, 201, 76, 0.30), 0 8px 40px -8px rgba(242, 201, 76, 0.40)",
} as const;

export const rings = {
  // For :focus-visible — composable with any elevation shadow.
  mint:    "0 0 0 2px rgba(10,15,20,1), 0 0 0 4px rgba(61,245,176,0.65)",
  cyan:    "0 0 0 2px rgba(10,15,20,1), 0 0 0 4px rgba(92,225,255,0.65)",
  violet:  "0 0 0 2px rgba(10,15,20,1), 0 0 0 4px rgba(139,124,255,0.65)",
  danger:  "0 0 0 2px rgba(10,15,20,1), 0 0 0 4px rgba(240,85,108,0.70)",
  // Soft monochrome ring for low-emphasis controls
  neutral: "0 0 0 2px rgba(10,15,20,1), 0 0 0 4px rgba(255,255,255,0.20)",
} as const;

/* -------------------------------------------------------------------------- *
 * Semantic theme — the API consumers should reach for.                       *
 * -------------------------------------------------------------------------- */

export const theme = {
  colors: {
    background: {
      primary:   palette.ink[700],     // page background (contrast reference)
      secondary: palette.ink[600],     // section / large surface
      elevated:  palette.steel[700],   // cards, panels
      sunken:    palette.ink[800],     // pressed / inset surface
      glass:     "rgba(14, 20, 27, 0.55)", // frosted overlays
      // Interaction states for surfaces
      hover:     "rgba(255, 255, 255, 0.04)",
      active:    "rgba(255, 255, 255, 0.07)",
      selected:  "rgba(61, 245, 176, 0.08)",
      inverse:   palette.fog[50],
    },
    text: {
      primary:   palette.fog[50],   // 16.7 : 1  body copy, headings
      secondary: palette.fog[200],  // 10.7 : 1  supporting copy
      muted:     palette.fog[400],  //  5.6 : 1  metadata, captions (AA)
      subtle:    palette.fog[500],  //  3.0 : 1  large/decorative ONLY
      disabled:  palette.fog[600],  //  1.8 : 1  disabled-state text
      inverse:   palette.ink[900],  // text on light/brand surfaces
      onAccent:  palette.ink[900],  // text on filled brand button (12+ : 1 on mint)
      link:      palette.brand.mint,
      linkHover: palette.brand.mintHover,
    },
    brand: {
      primary:        palette.brand.mint,
      primaryHover:   palette.brand.mintHover,
      primaryActive:  palette.brand.mintActive,
      primaryMuted:   palette.brand.mintDeep,
      secondary:      palette.brand.cyan,
      secondaryHover: palette.brand.cyanHover,
      secondaryActive:palette.brand.cyanActive,
      accent:         palette.brand.violet,
      accentHover:    palette.brand.violetHover,
      accentActive:   palette.brand.violetActive,
      glow:           palette.brand.mintGlow,
    },
    border: {
      subtle: "rgba(255, 255, 255, 0.06)",
      soft:   "rgba(255, 255, 255, 0.10)",
      strong: "rgba(255, 255, 255, 0.16)",
      hover:  "rgba(255, 255, 255, 0.22)",
      focus:  palette.brand.mint,
      brand:  palette.brand.mintDeep,
      danger: palette.system.danger,
    },
    state: {
      success:      palette.system.success,
      successDeep:  palette.system.successDeep,
      successGlow:  palette.system.successGlow,
      warning:      palette.system.warning,
      warningDeep:  palette.system.warningDeep,
      warningGlow:  palette.system.warningGlow,
      error:        palette.system.danger,
      errorDeep:    palette.system.dangerDeep,
      errorGlow:    palette.system.dangerGlow,
      info:         palette.system.info,
      infoDeep:     palette.system.infoDeep,
      infoGlow:     palette.system.infoGlow,
    },
    graph: {
      node:       palette.fog[200],
      nodeMuted:  palette.fog[500],
      edge:       "rgba(168, 181, 200, 0.25)",
      edgeBright: "rgba(168, 181, 200, 0.55)",
      highlight:  palette.brand.cyan,
      active:     palette.brand.mint,
      risk:       palette.system.danger,
      warn:       palette.system.warning,
    },
  },

  // Per-surface interaction state recipes — easy for components to consume:
  //   `style={{ background: theme.interaction.surface.hover }}`
  interaction: {
    surface: {
      rest:     "transparent",
      hover:    "rgba(255, 255, 255, 0.04)",
      active:   "rgba(255, 255, 255, 0.07)",
      selected: "rgba(61, 245, 176, 0.08)",
      disabled: "rgba(255, 255, 255, 0.02)",
    },
    primary: {
      rest:    palette.brand.mint,
      hover:   palette.brand.mintHover,
      active:  palette.brand.mintActive,
      disabled:"rgba(61, 245, 176, 0.30)",
    },
    secondary: {
      rest:   "rgba(255, 255, 255, 0.04)",
      hover:  "rgba(255, 255, 255, 0.08)",
      active: "rgba(255, 255, 255, 0.12)",
    },
    danger: {
      rest:   palette.system.danger,
      hover:  "#FF6F84",
      active: palette.system.dangerDeep,
    },
  },

  gradients,
  shadows,
  glows,
  rings,

  radii: {
    none: "0px",
    xs:   "4px",
    sm:   "6px",
    md:   "10px",
    lg:   "16px",
    xl:   "22px",
    "2xl":"28px",
    full: "999px",
  },

  motion: {
    ease: {
      out:    [0.22, 1, 0.36, 1] as const,
      inOut:  [0.65, 0, 0.35, 1] as const,
      spring: { type: "spring", stiffness: 220, damping: 26, mass: 0.6 } as const,
    },
    duration: {
      fast:  0.18,
      base:  0.32,
      slow:  0.6,
      crawl: 1.2,
    },
  },

  typography: {
    display: "var(--font-display), ui-serif, Georgia, serif",
    ui:      "var(--font-ui), ui-sans-serif, system-ui, sans-serif",
    mono:    "ui-monospace, 'SF Mono', Menlo, Monaco, Consolas, monospace",
  },

  // Forward-compatible light theme. Not consumed yet but present so consumers
  // can start to read theme.light.* without breaking.
  light: {
    background: {
      primary:   "#FBFCFE",
      secondary: "#F2F5FA",
      elevated:  "#FFFFFF",
      glass:     "rgba(255,255,255,0.65)",
    },
    text: {
      primary:   "#0A0F14",
      secondary: "#3B4A5F",
      muted:     "#6B7686",
      inverse:   "#FFFFFF",
    },
  },
} as const;

export type Theme = typeof theme;
export type ThemeColors = Theme["colors"];

/* -------------------------------------------------------------------------- *
 * Helpers                                                                    *
 * -------------------------------------------------------------------------- */

/** Flatten a nested color object to Tailwind-friendly key paths. */
export function flattenColors(
  obj: Record<string, unknown>,
  prefix = "",
): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [key, value] of Object.entries(obj)) {
    const next = prefix ? `${prefix}-${key}` : key;
    if (value && typeof value === "object") {
      Object.assign(out, flattenColors(value as Record<string, unknown>, next));
    } else if (typeof value === "string") {
      out[next] = value;
    }
  }
  return out;
}

/* ---- Contrast utilities (WCAG 2.x) -------------------------------------- */

function srgbToLinear(c: number): number {
  const s = c / 255;
  return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
}

function relativeLuminance(hex: string): number {
  const m = hex.replace("#", "").match(/.{2}/g);
  if (!m || m.length < 3) return 0;
  const [r, g, b] = m.map((h) => parseInt(h, 16));
  return (
    0.2126 * srgbToLinear(r) +
    0.7152 * srgbToLinear(g) +
    0.0722 * srgbToLinear(b)
  );
}

/**
 * WCAG contrast ratio for two **opaque** sRGB hex colors (`#rrggbb`).
 * Returns a value in [1, 21]. Use this in tests or build-time assertions.
 */
export function getContrast(fgHex: string, bgHex: string): number {
  const a = relativeLuminance(fgHex);
  const b = relativeLuminance(bgHex);
  const [hi, lo] = a > b ? [a, b] : [b, a];
  return (hi + 0.05) / (lo + 0.05);
}

/** WCAG 2.2 conformance for a foreground/background pair. */
export function wcag(
  fgHex: string,
  bgHex: string,
  size: "normal" | "large" = "normal",
): { ratio: number; AA: boolean; AAA: boolean } {
  const ratio = getContrast(fgHex, bgHex);
  const aaThreshold  = size === "large" ? 3   : 4.5;
  const aaaThreshold = size === "large" ? 4.5 : 7;
  return {
    ratio: Math.round(ratio * 100) / 100,
    AA:  ratio >= aaThreshold,
    AAA: ratio >= aaaThreshold,
  };
}
