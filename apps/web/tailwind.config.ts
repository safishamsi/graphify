import type { Config } from "tailwindcss";
import { palette, theme, gradients, shadows, glows, rings } from "./styles/theme";

const { colors } = theme;

const config: Config = {
  darkMode: "class",
  content: [
    "./app/**/*.{ts,tsx,mdx}",
    "./components/**/*.{ts,tsx,mdx}",
    "./styles/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      /* ---------------------------------------------------------------- *
       * COLORS                                                           *
       * ---------------------------------------------------------------- */
      colors: {
        // Raw scales
        ink:   palette.ink,
        steel: palette.steel,
        fog:   palette.fog,

        // Brand — `bg-brand` defaults to primary, but full palette is exposed
        brand: {
          DEFAULT:        palette.brand.mint,
          mint:           palette.brand.mint,
          mintHover:      palette.brand.mintHover,
          mintActive:     palette.brand.mintActive,
          mintDeep:       palette.brand.mintDeep,
          cyan:           palette.brand.cyan,
          cyanHover:      palette.brand.cyanHover,
          cyanActive:     palette.brand.cyanActive,
          violet:         palette.brand.violet,
          violetHover:    palette.brand.violetHover,
          violetActive:   palette.brand.violetActive,
          blue:           palette.brand.blue,
          // Semantic aliases
          primary:        colors.brand.primary,
          primaryHover:   colors.brand.primaryHover,
          primaryActive:  colors.brand.primaryActive,
          secondary:      colors.brand.secondary,
          secondaryHover: colors.brand.secondaryHover,
          secondaryActive:colors.brand.secondaryActive,
          accent:         colors.brand.accent,
          accentHover:    colors.brand.accentHover,
          accentActive:   colors.brand.accentActive,
        },

        // Surface (background) tokens
        bg: {
          primary:   colors.background.primary,
          secondary: colors.background.secondary,
          elevated:  colors.background.elevated,
          sunken:    colors.background.sunken,
          glass:     colors.background.glass,
          hover:     colors.background.hover,
          active:    colors.background.active,
          selected:  colors.background.selected,
          inverse:   colors.background.inverse,
        },

        // Foreground (text) tokens
        text: {
          primary:   colors.text.primary,
          secondary: colors.text.secondary,
          muted:     colors.text.muted,
          subtle:    colors.text.subtle,
          disabled:  colors.text.disabled,
          inverse:   colors.text.inverse,
          onAccent:  colors.text.onAccent,
          link:      colors.text.link,
          linkHover: colors.text.linkHover,
        },

        // Border tokens (use the `border-edge-*` prefix to avoid clashes with
        // Tailwind's own `border-{color}` utility that also reads opacity).
        edge: {
          subtle: colors.border.subtle,
          soft:   colors.border.soft,
          strong: colors.border.strong,
          hover:  colors.border.hover,
          focus:  colors.border.focus,
          brand:  colors.border.brand,
          danger: colors.border.danger,
        },

        // State colors
        state: {
          success:     colors.state.success,
          successDeep: colors.state.successDeep,
          warning:     colors.state.warning,
          warningDeep: colors.state.warningDeep,
          error:       colors.state.error,
          errorDeep:   colors.state.errorDeep,
          info:        colors.state.info,
          infoDeep:    colors.state.infoDeep,
        },

        // Graph palette
        graph: colors.graph,
      },

      /* ---------------------------------------------------------------- *
       * TYPOGRAPHY + SHAPE                                               *
       * ---------------------------------------------------------------- */
      fontFamily: {
        display: ["var(--font-display)", "ui-serif", "Georgia", "serif"],
        sans:    ["var(--font-ui)", "ui-sans-serif", "system-ui", "sans-serif"],
        mono:    ["ui-monospace", "SF Mono", "Menlo", "Monaco", "Consolas", "monospace"],
      },
      borderRadius: {
        xs:    theme.radii.xs,
        sm:    theme.radii.sm,
        md:    theme.radii.md,
        lg:    theme.radii.lg,
        xl:    theme.radii.xl,
        "2xl": theme.radii["2xl"],
      },

      /* ---------------------------------------------------------------- *
       * SHADOWS, GLOWS, FOCUS RINGS                                      *
       * Naming convention:                                               *
       *   shadow-e1 … e4       — ambient elevation                       *
       *   shadow-glow-{c}-{s}  — colored brand halos                     *
       *   shadow-ring-{c}      — focus rings (compose with elevation)    *
       *   shadow-panel / card-lift / hairline-top — named aliases        *
       * ---------------------------------------------------------------- */
      boxShadow: {
        // Elevation
        e0: shadows.e0,
        e1: shadows.e1,
        e2: shadows.e2,
        e3: shadows.e3,
        e4: shadows.e4,

        // Aliases
        panel:          shadows.panel,
        "card-lift":    shadows.cardLift,
        "hairline-top": shadows.hairlineTop,

        // Glows — small / medium / large per accent
        "glow-mint-sm":   glows.mintSm,
        "glow-mint":      glows.mintMd,
        "glow-mint-md":   glows.mintMd,
        "glow-mint-lg":   glows.mintLg,

        "glow-cyan-sm":   glows.cyanSm,
        "glow-cyan":      glows.cyanMd,
        "glow-cyan-md":   glows.cyanMd,
        "glow-cyan-lg":   glows.cyanLg,

        "glow-violet-sm": glows.violetSm,
        "glow-violet":    glows.violetMd,
        "glow-violet-md": glows.violetMd,
        "glow-violet-lg": glows.violetLg,

        "glow-danger":    glows.dangerMd,
        "glow-warning":   glows.warningMd,

        // Focus rings — use `focus-visible:shadow-ring-mint`
        "ring-mint":    rings.mint,
        "ring-cyan":    rings.cyan,
        "ring-violet":  rings.violet,
        "ring-danger":  rings.danger,
        "ring-neutral": rings.neutral,
      },

      /* ---------------------------------------------------------------- *
       * GRADIENTS                                                         *
       * Surfaces consume these via `bg-gradient-brand` etc.              *
       * ---------------------------------------------------------------- */
      backgroundImage: {
        "gradient-brand":          gradients.brandSweep,
        "gradient-brand-headline": gradients.brandHeadline,
        "gradient-brand-subtle":   gradients.brandSubtle,
        "gradient-surface-panel":  gradients.surfacePanel,
        "gradient-surface-sunken": gradients.surfaceSunken,
        "gradient-glass-edge":     gradients.glassEdge,
        "gradient-glow-mint":      gradients.glowMint,
        "gradient-glow-cyan":      gradients.glowCyan,
        "gradient-glow-violet":    gradients.glowViolet,
        "gradient-glow-danger":    gradients.glowDanger,
        "gradient-risk":           gradients.riskHeat,
        "gradient-hairline":       gradients.hairline,
        "gradient-hairline-mint":  gradients.hairlineMint,
        "gradient-hairline-cyan":  gradients.hairlineCyan,
        "noise":                   gradients.noise,

        // Legacy aliases (kept so existing components don't break)
        "grid-fade":
          "linear-gradient(to bottom, rgba(255,255,255,0.04) 0%, transparent 70%)",
        "radial-glow":   gradients.glowMint,
        "radial-violet": gradients.glowViolet,
      },

      /* ---------------------------------------------------------------- *
       * MOTION                                                           *
       * ---------------------------------------------------------------- */
      transitionDuration: {
        fast:  `${theme.motion.duration.fast * 1000}ms`,
        base:  `${theme.motion.duration.base * 1000}ms`,
        slow:  `${theme.motion.duration.slow * 1000}ms`,
        crawl: `${theme.motion.duration.crawl * 1000}ms`,
      },
      transitionTimingFunction: {
        out:   `cubic-bezier(${theme.motion.ease.out.join(",")})`,
        inOut: `cubic-bezier(${theme.motion.ease.inOut.join(",")})`,
      },
      keyframes: {
        "pulse-glow": {
          "0%, 100%": { opacity: "0.4", transform: "scale(1)" },
          "50%":      { opacity: "1",   transform: "scale(1.04)" },
        },
        "drift": {
          "0%, 100%": { transform: "translate3d(0,0,0)" },
          "50%":      { transform: "translate3d(8px,-12px,0)" },
        },
        "draw": {
          "0%":   { strokeDashoffset: "1" },
          "100%": { strokeDashoffset: "0" },
        },
        "shimmer-x": {
          "0%":   { transform: "translateX(-100%)" },
          "100%": { transform: "translateX(100%)" },
        },
        "ripple": {
          "0%":   { transform: "scale(0.4)", opacity: "0.6" },
          "100%": { transform: "scale(2.2)", opacity: "0" },
        },
      },
      animation: {
        "pulse-glow": "pulse-glow 2.6s ease-in-out infinite",
        "drift-slow": "drift 14s ease-in-out infinite",
        "drift-fast": "drift 8s ease-in-out infinite",
        "shimmer":    "shimmer-x 2.4s ease-in-out infinite",
        "ripple":     "ripple 3.2s ease-out infinite",
      },
    },
  },
  plugins: [],
};

export default config;
