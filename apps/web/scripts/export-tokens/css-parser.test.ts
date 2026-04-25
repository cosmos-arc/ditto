// ─────────────────────────────────────────────
// Tests for css-parser.ts
// Reads 9 tokens-*.css files and extracts all --name: value declarations.
// Uses REAL data from the actual design-tokens/ directory.
// ─────────────────────────────────────────────

import { describe, it, expect } from "vitest";
import { resolve } from "node:path";
import { parseAllTokenFiles, parseCssFile } from "./css-parser";

const TOKENS_DIR = resolve(import.meta.dirname, "../../src/styles/design-tokens");

describe("css-parser", () => {
  // ── parseAllTokenFiles ──────────────────────

  describe("parseAllTokenFiles", () => {
    it("parses all 9 token files and returns a non-empty array", () => {
      const tokens = parseAllTokenFiles(TOKENS_DIR);
      expect(tokens.length).toBeGreaterThan(0);
    });

    it("finds tokens from every layer", () => {
      const tokens = parseAllTokenFiles(TOKENS_DIR);
      const layers = new Set(tokens.map((t) => t.layer));
      const expectedLayers = [
        "base",
        "semantic",
        "atmosphere",
        "shell",
        "data-viz",
        "component",
        "interaction",
        "domain",
        "density",
      ];
      for (const layer of expectedLayers) {
        expect(layers.has(layer), `Missing layer: ${layer}`).toBe(true);
      }
    });

    it("extracts neutral-0 from base layer correctly", () => {
      const tokens = parseAllTokenFiles(TOKENS_DIR);
      const neutral0 = tokens.find(
        (t) => t.name === "neutral-0" && t.selector === ":root",
      );
      expect(neutral0).toBeDefined();
      expect(neutral0!.value).toContain("oklch");
      expect(neutral0!.sourceFile).toBe("tokens-base.css");
      expect(neutral0!.layer).toBe("base");
      expect(neutral0!.context).toBe("default");
    });

    it("extracts brand-500 from base layer", () => {
      const tokens = parseAllTokenFiles(TOKENS_DIR);
      const brand500 = tokens.find(
        (t) => t.name === "brand-500" && t.selector === ":root",
      );
      expect(brand500).toBeDefined();
      expect(brand500!.value).toBe("oklch(0.640 0.120 235)");
      expect(brand500!.layer).toBe("base");
    });

    it("extracts font-size tokens with dimension values", () => {
      const tokens = parseAllTokenFiles(TOKENS_DIR);
      const fontSize12 = tokens.find(
        (t) => t.name === "font-size-12" && t.selector === ":root",
      );
      expect(fontSize12).toBeDefined();
      expect(fontSize12!.value).toBe("0.75rem");
    });

    it("extracts font-weight tokens with numeric values", () => {
      const tokens = parseAllTokenFiles(TOKENS_DIR);
      const fwRegular = tokens.find(
        (t) => t.name === "font-weight-regular" && t.selector === ":root",
      );
      expect(fwRegular).toBeDefined();
      expect(fwRegular!.value).toBe("400");
    });

    it("extracts motion tokens (duration and easing)", () => {
      const tokens = parseAllTokenFiles(TOKENS_DIR);
      const duration = tokens.find(
        (t) => t.name === "motion-duration-fast" && t.selector === ":root",
      );
      expect(duration).toBeDefined();
      expect(duration!.value).toBe("100ms");

      const easing = tokens.find(
        (t) => t.name === "motion-easing-standard" && t.selector === ":root",
      );
      expect(easing).toBeDefined();
      expect(easing!.value).toContain("cubic-bezier");
    });

    it("extracts font-family tokens with quoted strings", () => {
      const tokens = parseAllTokenFiles(TOKENS_DIR);
      const ff = tokens.find(
        (t) => t.name === "font-family-ui" && t.selector === ":root",
      );
      expect(ff).toBeDefined();
      expect(ff!.value).toContain("'Inter'");
    });

    it("extracts CSS string value tokens (indicator symbols)", () => {
      const tokens = parseAllTokenFiles(TOKENS_DIR);
      const upSym = tokens.find(
        (t) => t.name === "indicator-up-sym" && t.selector === ":root",
      );
      expect(upSym).toBeDefined();
      expect(upSym!.value).toBe("'\\25B2'");
    });

    it("extracts semantic layer tokens with var() references", () => {
      const tokens = parseAllTokenFiles(TOKENS_DIR);
      const surfaceApp = tokens.find(
        (t) => t.name === "surface-app" && t.selector === ":root",
      );
      expect(surfaceApp).toBeDefined();
      expect(surfaceApp!.value).toContain("var(--surface-app-atmosphere");
      expect(surfaceApp!.layer).toBe("semantic");
    });

    it("extracts interaction layer tokens with relative oklch", () => {
      const tokens = parseAllTokenFiles(TOKENS_DIR);
      const focusRing = tokens.find(
        (t) => t.name === "interaction-focus-ring" && t.selector === ":root",
      );
      expect(focusRing).toBeDefined();
      expect(focusRing!.value).toContain("from var(--brand-500)");
      expect(focusRing!.layer).toBe("interaction");
    });

    it("extracts composite shadow tokens", () => {
      const tokens = parseAllTokenFiles(TOKENS_DIR);
      const shadow = tokens.find(
        (t) => t.name === "interaction-dragging-shadow" && t.selector === ":root",
      );
      expect(shadow).toBeDefined();
      expect(shadow!.value).toMatch(/^0 8px 24px oklch/);
    });

    it("extracts composite border tokens", () => {
      const tokens = parseAllTokenFiles(TOKENS_DIR);
      const border = tokens.find(
        (t) => t.name === "card-border" && t.selector === ":root",
      );
      expect(border).toBeDefined();
      expect(border!.value).toContain("1px solid");
    });

    it("classifies :root tokens as default context", () => {
      const tokens = parseAllTokenFiles(TOKENS_DIR);
      const rootTokens = tokens.filter((t) => t.selector === ":root");
      expect(rootTokens.length).toBeGreaterThan(0);
      expect(rootTokens.every((t) => t.context === "default")).toBe(true);
    });

    it("classifies light theme tokens correctly", () => {
      const tokens = parseAllTokenFiles(TOKENS_DIR);
      const lightTokens = tokens.filter(
        (t) => t.selector === '[data-theme="light"]',
      );
      expect(lightTokens.length).toBeGreaterThan(0);
      expect(lightTokens.every((t) => t.context === "light")).toBe(true);
    });

    it("classifies density tokens correctly", () => {
      const tokens = parseAllTokenFiles(TOKENS_DIR);
      const densityTokens = tokens.filter(
        (t) => t.context === "density",
      );
      expect(densityTokens.length).toBeGreaterThan(0);
      expect(densityTokens.every((t) => t.layer === "density")).toBe(true);
    });

    it("strips -- prefix from token names", () => {
      const tokens = parseAllTokenFiles(TOKENS_DIR);
      for (const token of tokens) {
        expect(token.name).not.toMatch(/^--/);
      }
    });

    it("normalizes multi-line values (collapses whitespace)", () => {
      const tokens = parseAllTokenFiles(TOKENS_DIR);
      const atmosphere = tokens.find(
        (t) => t.name === "surface-app-atmosphere" && t.selector === ":root",
      );
      expect(atmosphere).toBeDefined();
      // Multi-line calc() should be collapsed to single-line
      expect(atmosphere!.value).not.toContain("\n");
      expect(atmosphere!.value).toContain("calc(");
    });

    it("finds light-mode overrides for base tokens", () => {
      const tokens = parseAllTokenFiles(TOKENS_DIR);
      const lightNeutral0 = tokens.find(
        (t) => t.name === "neutral-0" && t.selector === '[data-theme="light"]',
      );
      expect(lightNeutral0).toBeDefined();
      expect(lightNeutral0!.value).toBe("oklch(0.988 0.001 253)");
    });

    it("finds tokens with transparent values", () => {
      const tokens = parseAllTokenFiles(TOKENS_DIR);
      const flatBg = tokens.find(
        (t) => t.name === "market-flat-bg" && t.selector === ":root",
      );
      expect(flatBg).toBeDefined();
      expect(flatBg!.value).toBe("transparent");
    });

    it("finds tokens with alpha oklch values", () => {
      const tokens = parseAllTokenFiles(TOKENS_DIR);
      const upBg = tokens.find(
        (t) => t.name === "market-up-bg" && t.selector === ":root",
      );
      expect(upBg).toBeDefined();
      expect(upBg!.value).toContain("/");
    });
  });

  // ── parseCssFile (single file) ──────────────

  describe("parseCssFile", () => {
    it("parses tokens-base.css and returns tokens", () => {
      const filePath = resolve(TOKENS_DIR, "tokens-base.css");
      const tokens = parseCssFile(filePath);
      expect(tokens.length).toBeGreaterThan(0);
    });

    it("all tokens from tokens-base.css have layer 'base'", () => {
      const filePath = resolve(TOKENS_DIR, "tokens-base.css");
      const tokens = parseCssFile(filePath);
      expect(tokens.every((t) => t.layer === "base")).toBe(true);
    });

    it("all tokens from tokens-semantic.css have layer 'semantic'", () => {
      const filePath = resolve(TOKENS_DIR, "tokens-semantic.css");
      const tokens = parseCssFile(filePath);
      expect(tokens.every((t) => t.layer === "semantic")).toBe(true);
    });

    it("throws for a filename that does not match tokens-{layer}.css", () => {
      expect(() => parseCssFile("/some/path/style.css")).toThrow(
        "Cannot derive layer from filename",
      );
    });

    it("strips CSS comments before parsing", () => {
      const filePath = resolve(TOKENS_DIR, "tokens-base.css");
      const tokens = parseCssFile(filePath);
      // No token value should contain comment artifacts
      for (const token of tokens) {
        expect(token.value).not.toContain("/*");
        expect(token.value).not.toContain("*/");
      }
    });
  });
});
