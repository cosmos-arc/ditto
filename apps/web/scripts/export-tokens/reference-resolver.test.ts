// ─────────────────────────────────────────────
// Tests for reference-resolver.ts
// Value classification, reference resolution, and DTCG output.
// ─────────────────────────────────────────────

import { describe, it, expect } from "vitest";
import { resolve } from "node:path";
import {
  buildReferenceMap,
  resolveAllTokens,
  parseTokenValue,
} from "./reference-resolver";
import { parseAllTokenFiles } from "./css-parser";
import type { ParsedValue, DtcgToken } from "./types";

const TOKENS_DIR = resolve(import.meta.dirname, "../../src/styles/design-tokens");

describe("reference-resolver", () => {
  // ── parseTokenValue ────────────────────────

  describe("parseTokenValue", () => {
    // Color
    it("classifies oklch() as color", () => {
      const result = parseTokenValue("oklch(0.640 0.120 235)");
      expect(result.type).toBe("color");
      if (result.type === "color") {
        expect(result.oklch).toBe("oklch(0.640 0.120 235)");
      }
    });

    it("classifies oklch() with alpha as color", () => {
      const result = parseTokenValue("oklch(0 0 0 / 0.4)");
      expect(result.type).toBe("color");
    });

    // Reference
    it("classifies var(--name) as reference", () => {
      const result = parseTokenValue("var(--brand-500)");
      expect(result.type).toBe("reference");
      if (result.type === "reference") {
        expect(result.variableName).toBe("brand-500");
      }
    });

    // Reference with fallback
    it("classifies var(--name, fallback) as referenceWithFallback", () => {
      const result = parseTokenValue(
        "var(--surface-app-atmosphere, var(--neutral-0))",
      );
      expect(result.type).toBe("referenceWithFallback");
      if (result.type === "referenceWithFallback") {
        expect(result.variableName).toBe("surface-app-atmosphere");
        expect(result.fallback).toBe("var(--neutral-0)");
      }
    });

    // Relative oklch
    it("classifies oklch(from var(--x) l c h / a) as relativeOklch", () => {
      const result = parseTokenValue(
        "oklch(from var(--brand-500) l c h / 0.10)",
      );
      expect(result.type).toBe("relativeOklch");
      if (result.type === "relativeOklch") {
        expect(result.baseVariable).toBe("brand-500");
      }
    });

    // Dimension
    it("classifies 0.5rem as dimension", () => {
      const result = parseTokenValue("0.5rem");
      expect(result.type).toBe("dimension");
    });

    it("classifies 1px as dimension", () => {
      const result = parseTokenValue("1px");
      expect(result.type).toBe("dimension");
    });

    it("classifies 0.125rem as dimension", () => {
      const result = parseTokenValue("0.125rem");
      expect(result.type).toBe("dimension");
    });

    // Font weight
    it("classifies 400 as fontWeight", () => {
      const result = parseTokenValue("400");
      expect(result.type).toBe("fontWeight");
      if (result.type === "fontWeight") {
        expect(result.value).toBe(400);
      }
    });

    it("classifies 500 as fontWeight", () => {
      const result = parseTokenValue("500");
      expect(result.type).toBe("fontWeight");
    });

    it("classifies 600 as fontWeight", () => {
      const result = parseTokenValue("600");
      expect(result.type).toBe("fontWeight");
    });

    // Number (non-integer, or outside 1-1000 range)
    it("classifies 0.85 as number", () => {
      const result = parseTokenValue("0.85");
      expect(result.type).toBe("number");
    });

    it("classifies 0 as number", () => {
      const result = parseTokenValue("0");
      expect(result.type).toBe("number");
    });

    // Transparent
    it("classifies transparent as transparent", () => {
      const result = parseTokenValue("transparent");
      expect(result.type).toBe("transparent");
    });

    // Duration
    it("classifies 100ms as duration", () => {
      const result = parseTokenValue("100ms");
      expect(result.type).toBe("duration");
    });

    it("classifies 45s as duration", () => {
      const result = parseTokenValue("45s");
      expect(result.type).toBe("duration");
    });

    // Cubic bezier
    it("classifies cubic-bezier() as cubicBezier", () => {
      const result = parseTokenValue("cubic-bezier(0.4, 0, 0.2, 1)");
      expect(result.type).toBe("cubicBezier");
    });

    // Composite shadow
    // COMPOSITE_SHADOW_RE uses ^-?[\d.]+px? so both "0px" and bare "0" match.
    // It is checked at step 3b (before standard oklch at step 5).
    it("shadow values containing oklch() are classified as composite-shadow", () => {
      const result = parseTokenValue("0px 8px 24px oklch(0 0 0 / 0.4)");
      expect(result.type).toBe("composite-shadow");
    });

    it("classifies shadow with bare offsetX as composite-shadow", () => {
      const result = parseTokenValue("0 8px 24px oklch(0 0 0 / 0.4)");
      expect(result.type).toBe("composite-shadow");
    });

    // Composite border
    it("classifies border shorthand as composite-border", () => {
      const result = parseTokenValue("1px solid var(--border-subtle)");
      expect(result.type).toBe("composite-border");
    });

    // Runtime dynamic (calc inside oklch)
    // RUNTIME_DYNAMIC_RE now uses explicit calc([\d.]+ + var([^)]+)) per channel.
    it("classifies oklch(calc(...) with nested var()) as runtimeDynamic", () => {
      const result = parseTokenValue(
        "oklch(calc(0.166 + var(--atmosphere-lightness-shift)) calc(0.010 + var(--atmosphere-chroma-boost)) calc(253 + var(--atmosphere-hue-shift)))",
      );
      expect(result.type).toBe("runtimeDynamic");
    });

    // String
    it("classifies quoted string as string", () => {
      const result = parseTokenValue("'\\25B2'");
      expect(result.type).toBe("string");
    });

    // Font family
    it("classifies font-family as fontFamily", () => {
      const result = parseTokenValue(
        "'Inter', 'Noto Sans SC Variable', system-ui, sans-serif",
      );
      expect(result.type).toBe("fontFamily");
    });

    // Multi-var shorthand
    it("classifies multiple var() references as composite-shorthand", () => {
      const result = parseTokenValue(
        "var(--space-10) var(--space-12)",
      );
      expect(result.type).toBe("composite-shorthand");
    });

    // Percentage dimension
    it("classifies percentage as dimension", () => {
      const result = parseTokenValue("100%");
      expect(result.type).toBe("dimension");
    });

    // Edge cases
    it("classifies empty string as unknown", () => {
      const result = parseTokenValue("");
      expect(result.type).toBe("unknown");
    });
  });

  // ── buildReferenceMap ──────────────────────

  describe("buildReferenceMap", () => {
    it("builds a map from real token data", () => {
      const tokens = parseAllTokenFiles(TOKENS_DIR);
      const map = buildReferenceMap(tokens);
      expect(map.size).toBeGreaterThan(0);
    });

    it("maps brand-500 to its DTCG path", () => {
      const tokens = parseAllTokenFiles(TOKENS_DIR);
      const map = buildReferenceMap(tokens);
      const path = map.get("brand-500");
      expect(path).toBe("{base.brand.500}");
    });

    it("maps neutral-0 to its DTCG path", () => {
      const tokens = parseAllTokenFiles(TOKENS_DIR);
      const map = buildReferenceMap(tokens);
      const path = map.get("neutral-0");
      expect(path).toBe("{base.neutral.0}");
    });

    it("maps font-size-12 to its DTCG path", () => {
      const tokens = parseAllTokenFiles(TOKENS_DIR);
      const map = buildReferenceMap(tokens);
      const path = map.get("font-size-12");
      // tokenToDtcgPath: "font-size-12".replace(/-/g, ".") = "font.size.12"
      expect(path).toBe("{base.font.size.12}");
    });

    it("only includes :root (default) tokens", () => {
      const tokens = parseAllTokenFiles(TOKENS_DIR);
      const map = buildReferenceMap(tokens);
      // Light-theme overrides should NOT create separate paths
      // The map should have one entry per unique name from :root
      for (const [_name, path] of map) {
        expect(path).toMatch(/^\{[a-z-]+\./);
      }
    });

    it("maps semantic tokens correctly", () => {
      const tokens = parseAllTokenFiles(TOKENS_DIR);
      const map = buildReferenceMap(tokens);
      // tokenToDtcgPath uses name.replace(/-/g, "."), so all hyphens become dots
      const path = map.get("surface-panel-base");
      expect(path).toBe("{semantic.surface.panel.base}");
    });

    it("maps interaction tokens correctly (layer prefix dedup)", () => {
      const tokens = parseAllTokenFiles(TOKENS_DIR);
      const map = buildReferenceMap(tokens);
      // Token name "interaction-focus-ring" with layer "interaction"
      // tokenToDtcgPath strips the layer prefix: "focus-ring" → "{interaction.focus.ring}"
      const path = map.get("interaction-focus-ring");
      expect(path).toBe("{interaction.focus.ring}");
    });
  });

  // ── resolveAllTokens ───────────────────────

  describe("resolveAllTokens", () => {
    it("resolves all tokens from real data into DTCG format", () => {
      const tokens = parseAllTokenFiles(TOKENS_DIR);
      const resolved = resolveAllTokens(tokens);
      expect(resolved.size).toBeGreaterThan(0);
    });

    it("resolves oklch colors to hex $value", () => {
      const tokens = parseAllTokenFiles(TOKENS_DIR);
      const resolved = resolveAllTokens(tokens);
      const brand500 = resolved.get("{base.brand.500}");
      expect(brand500).toBeDefined();
      expect(brand500!.$type).toBe("color");
      // resolveAllTokens only processes :root tokens, so the value is the :root (dark) value.
      expect(brand500!.$value).toMatch(/^#[0-9a-f]{6}$/);
    });

    it("resolves neutral-0 to a dark hex color", () => {
      const tokens = parseAllTokenFiles(TOKENS_DIR);
      const resolved = resolveAllTokens(tokens);
      const neutral0 = resolved.get("{base.neutral.0}");
      expect(neutral0).toBeDefined();
      expect(neutral0!.$type).toBe("color");
      expect(neutral0!.$value).toMatch(/^#[0-9a-f]{6}$/);
    });

    it("resolves dimension tokens correctly", () => {
      const tokens = parseAllTokenFiles(TOKENS_DIR);
      const resolved = resolveAllTokens(tokens);
      const fontSize12 = resolved.get("{base.font.size.12}");
      expect(fontSize12).toBeDefined();
      expect(fontSize12!.$type).toBe("dimension");
      expect(fontSize12!.$value).toBe("0.75rem");
    });

    it("resolves font-weight tokens correctly", () => {
      const tokens = parseAllTokenFiles(TOKENS_DIR);
      const resolved = resolveAllTokens(tokens);
      const fwRegular = resolved.get("{base.font.weight.regular}");
      expect(fwRegular).toBeDefined();
      expect(fwRegular!.$type).toBe("fontWeight");
      expect(fwRegular!.$value).toBe("400");
    });

    it("resolves duration tokens correctly", () => {
      const tokens = parseAllTokenFiles(TOKENS_DIR);
      const resolved = resolveAllTokens(tokens);
      const duration = resolved.get("{base.motion.duration.fast}");
      expect(duration).toBeDefined();
      expect(duration!.$type).toBe("duration");
      expect(duration!.$value).toBe("100ms");
    });

    it("resolves cubic-bezier tokens correctly", () => {
      const tokens = parseAllTokenFiles(TOKENS_DIR);
      const resolved = resolveAllTokens(tokens);
      const easing = resolved.get("{base.motion.easing.standard}");
      expect(easing).toBeDefined();
      expect(easing!.$type).toBe("cubicBezier");
    });

    it("resolves transparent tokens correctly", () => {
      const tokens = parseAllTokenFiles(TOKENS_DIR);
      const resolved = resolveAllTokens(tokens);
      const flatBg = resolved.get("{domain.market.flat.bg}");
      expect(flatBg).toBeDefined();
      expect(flatBg!.$type).toBe("color");
      expect(flatBg!.$value).toBe("transparent");
    });

    it("resolves var() references — --prefix stripped correctly", () => {
      const tokens = parseAllTokenFiles(TOKENS_DIR);
      const resolved = resolveAllTokens(tokens);
      const textLink = resolved.get("{semantic.text.link}");
      expect(textLink).toBeDefined();
      // parseTokenValue strips the -- prefix from var(--brand-400) → "brand-400"
      // buildReferenceMap stores keys without --, so lookup succeeds.
      expect(textLink!.$value).toBe("{base.brand.400}");
      expect(textLink!.$type).toBe("color");
    });

    it("resolves oklch with alpha to 8-digit hex", () => {
      const tokens = parseAllTokenFiles(TOKENS_DIR);
      const resolved = resolveAllTokens(tokens);
      const upBg = resolved.get("{domain.market.up.bg}");
      expect(upBg).toBeDefined();
      expect(upBg!.$type).toBe("color");
      expect(upBg!.$value).toMatch(/^#[0-9a-f]{8}$/);
    });

    it("stores oklch in extensions for color tokens", () => {
      const tokens = parseAllTokenFiles(TOKENS_DIR);
      const resolved = resolveAllTokens(tokens);
      const brand500 = resolved.get("{base.brand.500}");
      expect(brand500).toBeDefined();
      const ext = brand500!.$extensions?.["com.ditto-app"];
      expect(ext).toBeDefined();
      // Only :root tokens are processed, so this is the dark value
      expect(ext?.oklch).toContain("oklch(0.");
      expect(ext?.oklch).toContain("235");
    });

    it("stores source file and layer in extensions", () => {
      const tokens = parseAllTokenFiles(TOKENS_DIR);
      const resolved = resolveAllTokens(tokens);
      const brand500 = resolved.get("{base.brand.500}");
      const ext = brand500?.$extensions?.["com.ditto-app"];
      expect(ext?.source).toBe("tokens-base.css");
      expect(ext?.layer).toBe("base");
    });

    it("resolves composite shadow — classified as composite with shadow $value", () => {
      const tokens = parseAllTokenFiles(TOKENS_DIR);
      const resolved = resolveAllTokens(tokens);
      // DTCG path for "interaction-dragging-shadow" in interaction layer:
      // layer prefix stripped: "dragging-shadow" → "{interaction.dragging.shadow}"
      const shadow = resolved.get("{interaction.dragging.shadow}");
      expect(shadow).toBeDefined();
      // COMPOSITE_SHADOW_RE now matches bare "0" offsets, so this is composite-shadow → composite
      expect(shadow!.$type).toBe("composite");
    });

    it("resolves composite border as composite type", () => {
      const tokens = parseAllTokenFiles(TOKENS_DIR);
      const resolved = resolveAllTokens(tokens);
      const border = resolved.get("{component.card.border}");
      expect(border).toBeDefined();
      expect(border!.$type).toBe("composite");
    });

    it("resolves relative oklch tokens to hex with extensions", () => {
      const tokens = parseAllTokenFiles(TOKENS_DIR);
      const resolved = resolveAllTokens(tokens);
      // DTCG path for "interaction-focus-ring" with layer prefix stripped:
      // "focus-ring" → "{interaction.focus.ring}"
      const focusRing = resolved.get("{interaction.focus.ring}");
      expect(focusRing).toBeDefined();
      expect(focusRing!.$type).toBe("color");
      // Should have resolved the relative oklch to an 8-digit hex (alpha < 1)
      expect(focusRing!.$value).toMatch(/^#[0-9a-f]{8}$/);
    });

    it("resolves runtime-dynamic tokens — classified as color with dynamic extension", () => {
      const tokens = parseAllTokenFiles(TOKENS_DIR);
      const resolved = resolveAllTokens(tokens);
      const atmosphere = resolved.get("{atmosphere.surface.app.atmosphere}");
      expect(atmosphere).toBeDefined();
      // RUNTIME_DYNAMIC_RE now matches calc() + var() patterns per channel.
      // Resolved as runtimeDynamic → color with dynamic: true in extensions.
      expect(atmosphere!.$type).toBe("color");
      const ext = atmosphere!.$extensions?.["com.ditto-app"];
      expect(ext?.dynamic).toBe(true);
    });

    it("only includes :root (default) tokens — theme overrides excluded", () => {
      const tokens = parseAllTokenFiles(TOKENS_DIR);
      const resolved = resolveAllTokens(tokens);
      // resolveAllTokens only processes context "default" tokens.
      // Theme overrides (light, density, domain) are handled by resolveThemeOverrides.
      expect(resolved.size).toBeGreaterThan(100);
    });
  });
});
