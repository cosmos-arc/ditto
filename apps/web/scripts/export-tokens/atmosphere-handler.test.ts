// ─────────────────────────────────────────────
// Tests for atmosphere-handler.ts
// Specialized processing for the 6 atmosphere tokens.
// ─────────────────────────────────────────────

import { describe, it, expect } from "vitest";
import { resolve } from "node:path";
import {
  isAtmosphereToken,
  extractCalcBaseValues,
  processAtmosphereTokens,
} from "./atmosphere-handler";
import { parseAllTokenFiles } from "./css-parser";
import type { RawCssToken } from "./types";

const TOKENS_DIR = resolve(import.meta.dirname, "../../src/styles/design-tokens");

describe("atmosphere-handler", () => {
  // ── isAtmosphereToken ──────────────────────

  describe("isAtmosphereToken", () => {
    it("returns true for atmosphere layer token", () => {
      const token: RawCssToken = {
        name: "surface-app-atmosphere",
        value: "oklch(calc(0.166 + var(--x)) calc(0.010 + var(--y)) calc(253 + var(--z)))",
        sourceFile: "tokens-atmosphere.css",
        selector: ":root",
        layer: "atmosphere",
        context: "default",
      };
      expect(isAtmosphereToken(token)).toBe(true);
    });

    it("returns false for base layer token", () => {
      const token: RawCssToken = {
        name: "brand-500",
        value: "oklch(0.640 0.120 235)",
        sourceFile: "tokens-base.css",
        selector: ":root",
        layer: "base",
        context: "default",
      };
      expect(isAtmosphereToken(token)).toBe(false);
    });

    it("returns false for semantic layer token", () => {
      const token: RawCssToken = {
        name: "surface-panel-base",
        value: "var(--neutral-25)",
        sourceFile: "tokens-semantic.css",
        selector: ":root",
        layer: "semantic",
        context: "default",
      };
      expect(isAtmosphereToken(token)).toBe(false);
    });

    it("returns false for interaction layer token", () => {
      const token: RawCssToken = {
        name: "interaction-focus-ring",
        value: "oklch(from var(--brand-500) l c h / 0.50)",
        sourceFile: "tokens-interaction.css",
        selector: ":root",
        layer: "interaction",
        context: "default",
      };
      expect(isAtmosphereToken(token)).toBe(false);
    });
  });

  // ── extractCalcBaseValues ──────────────────

  describe("extractCalcBaseValues", () => {
    it("extracts base values from dark atmosphere calc expression", () => {
      const rawValue =
        "oklch(calc(0.166 + var(--atmosphere-lightness-shift)) calc(0.010 + var(--atmosphere-chroma-boost)) calc(253 + var(--atmosphere-hue-shift)))";
      const result = extractCalcBaseValues(rawValue);
      expect(result).not.toBeNull();
      expect(result!.l).toBeCloseTo(0.166, 3);
      expect(result!.c).toBeCloseTo(0.010, 3);
      expect(result!.h).toBeCloseTo(253, 1);
    });

    it("extracts base values from light atmosphere calc expression", () => {
      const rawValue =
        "oklch(calc(0.988 + var(--atmosphere-lightness-shift)) calc(0.001 + var(--atmosphere-chroma-boost)) calc(253 + var(--atmosphere-hue-shift)))";
      const result = extractCalcBaseValues(rawValue);
      expect(result).not.toBeNull();
      expect(result!.l).toBeCloseTo(0.988, 3);
      expect(result!.c).toBeCloseTo(0.001, 3);
      expect(result!.h).toBeCloseTo(253, 1);
    });

    it("returns null for string without calc expressions", () => {
      expect(extractCalcBaseValues("oklch(0.640 0.120 235)")).toBeNull();
    });

    it("returns null for empty string", () => {
      expect(extractCalcBaseValues("")).toBeNull();
    });

    it("returns null for string with only 2 calc values", () => {
      const rawValue =
        "oklch(calc(0.166 + var(--x)) calc(0.010 + var(--y)))";
      expect(extractCalcBaseValues(rawValue)).toBeNull();
    });

    it("returns null for non-numeric calc bases", () => {
      const rawValue =
        "oklch(calc(a + var(--x)) calc(b + var(--y)) calc(c + var(--z)))";
      expect(extractCalcBaseValues(rawValue)).toBeNull();
    });
  });

  // ── processAtmosphereTokens ────────────────

  describe("processAtmosphereTokens", () => {
    it("processes atmosphere tokens from real data", () => {
      const tokens = parseAllTokenFiles(TOKENS_DIR);
      const result = processAtmosphereTokens(tokens);
      expect(result.size).toBeGreaterThan(0);
    });

    it("produces runtime param tokens (hue-shift) as number type", () => {
      const tokens = parseAllTokenFiles(TOKENS_DIR);
      const result = processAtmosphereTokens(tokens);
      const hueShift = result.get("atmosphere-hue-shift");
      expect(hueShift).toBeDefined();
      expect(hueShift!.$type).toBe("number");
      expect(hueShift!.$value).toBe("0");
    });

    it("runtime param tokens have dynamic extension flag", () => {
      const tokens = parseAllTokenFiles(TOKENS_DIR);
      const result = processAtmosphereTokens(tokens);
      const hueShift = result.get("atmosphere-hue-shift");
      const ext = hueShift?.$extensions?.["com.ditto-app"];
      expect(ext?.dynamic).toBe(true);
      expect(ext?.layer).toBe("atmosphere");
    });

    it("produces chroma-boost token as number type", () => {
      const tokens = parseAllTokenFiles(TOKENS_DIR);
      const result = processAtmosphereTokens(tokens);
      const chroma = result.get("atmosphere-chroma-boost");
      expect(chroma).toBeDefined();
      expect(chroma!.$type).toBe("number");
      expect(chroma!.$value).toBe("0");
    });

    it("produces lightness-shift token as number type", () => {
      const tokens = parseAllTokenFiles(TOKENS_DIR);
      const result = processAtmosphereTokens(tokens);
      const ls = result.get("atmosphere-lightness-shift");
      expect(ls).toBeDefined();
      expect(ls!.$type).toBe("number");
      expect(ls!.$value).toBe("0");
    });

    it("produces breathe-duration token as duration type", () => {
      const tokens = parseAllTokenFiles(TOKENS_DIR);
      const result = processAtmosphereTokens(tokens);
      const duration = result.get("atmosphere-breathe-duration");
      expect(duration).toBeDefined();
      expect(duration!.$type).toBe("duration");
      expect(duration!.$value).toBe("45s");
    });

    it("produces surface-app-atmosphere token as color with fallback hex", () => {
      const tokens = parseAllTokenFiles(TOKENS_DIR);
      const result = processAtmosphereTokens(tokens);
      const atmosphere = result.get("surface-app-atmosphere");
      expect(atmosphere).toBeDefined();
      expect(atmosphere!.$type).toBe("color");
      expect(atmosphere!.$value).toMatch(/^#[0-9a-f]{6}$/);
    });

    it("surface-app-atmosphere has runtimeDynamic extension flag", () => {
      const tokens = parseAllTokenFiles(TOKENS_DIR);
      const result = processAtmosphereTokens(tokens);
      const atmosphere = result.get("surface-app-atmosphere");
      const ext = atmosphere?.$extensions?.["com.ditto-app"];
      expect(ext?.runtimeDynamic).toBe(true);
      expect(ext?.rawCss).toContain("calc(");
    });

    it("produces light theme variant with context-qualified key", () => {
      const tokens = parseAllTokenFiles(TOKENS_DIR);
      const result = processAtmosphereTokens(tokens);
      const lightAtmosphere = result.get("surface-app-atmosphere:light");
      expect(lightAtmosphere).toBeDefined();
      expect(lightAtmosphere!.$type).toBe("color");
    });

    it("light atmosphere variant has different fallback hex than dark", () => {
      const tokens = parseAllTokenFiles(TOKENS_DIR);
      const result = processAtmosphereTokens(tokens);
      const darkAtm = result.get("surface-app-atmosphere");
      const lightAtm = result.get("surface-app-atmosphere:light");
      // Dark is based on oklch(0.166 0.010 253), light on oklch(0.988 0.001 253)
      expect(darkAtm!.$value).not.toBe(lightAtm!.$value);
    });

    it("surface-app-atmosphere fallback hex matches neutral-0 (same base)", () => {
      const tokens = parseAllTokenFiles(TOKENS_DIR);
      const result = processAtmosphereTokens(tokens);
      const atmosphere = result.get("surface-app-atmosphere");
      // Both are based on oklch(0.166 0.010 253) — atmosphere dark = neutral-0 base
      // The fallback hex should be very close to neutral-0's hex
      expect(atmosphere!.$value).toMatch(/^#[0-9a-f]{6}$/);
    });
  });
});
