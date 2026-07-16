// ─────────────────────────────────────────────
// Tests for types.ts
// Token layer derivation and selector classification.
// ─────────────────────────────────────────────

import { describe, it, expect } from "vitest";
import { layerFromFilename, themeContextFromSelector, TOKEN_LAYERS } from "./types";

describe("types", () => {
  // ── TOKEN_LAYERS ───────────────────────────

  describe("TOKEN_LAYERS", () => {
    it("contains exactly 9 layers", () => {
      expect(TOKEN_LAYERS).toHaveLength(9);
    });

    it("contains all expected layers in order", () => {
      const expected = [
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
      expect(TOKEN_LAYERS).toEqual(expected);
    });
  });

  // ── layerFromFilename ──────────────────────

  describe("layerFromFilename", () => {
    it("derives base from tokens-base.css", () => {
      expect(layerFromFilename("tokens-base.css")).toBe("base");
    });

    it("derives semantic from tokens-semantic.css", () => {
      expect(layerFromFilename("tokens-semantic.css")).toBe("semantic");
    });

    it("derives atmosphere from tokens-atmosphere.css", () => {
      expect(layerFromFilename("tokens-atmosphere.css")).toBe("atmosphere");
    });

    it("derives shell from tokens-shell.css", () => {
      expect(layerFromFilename("tokens-shell.css")).toBe("shell");
    });

    it("derives data-viz from tokens-data-viz.css", () => {
      expect(layerFromFilename("tokens-data-viz.css")).toBe("data-viz");
    });

    it("derives component from tokens-component.css", () => {
      expect(layerFromFilename("tokens-component.css")).toBe("component");
    });

    it("derives interaction from tokens-interaction.css", () => {
      expect(layerFromFilename("tokens-interaction.css")).toBe("interaction");
    });

    it("derives domain from tokens-domain.css", () => {
      expect(layerFromFilename("tokens-domain.css")).toBe("domain");
    });

    it("derives density from tokens-density.css", () => {
      expect(layerFromFilename("tokens-density.css")).toBe("density");
    });

    it("throws for filename not matching tokens-{layer}.css", () => {
      expect(() => layerFromFilename("style.css")).toThrow(
        "Cannot derive layer from filename",
      );
    });

    it("throws for unknown layer name", () => {
      expect(() => layerFromFilename("tokens-unknown.css")).toThrow(
        "Unknown token layer",
      );
    });

    it("throws for filename without .css extension", () => {
      expect(() => layerFromFilename("tokens-base")).toThrow(
        "Cannot derive layer from filename",
      );
    });

    it("throws for empty string", () => {
      expect(() => layerFromFilename("")).toThrow(
        "Cannot derive layer from filename",
      );
    });
  });

  // ── themeContextFromSelector ───────────────

  describe("themeContextFromSelector", () => {
    it('classifies :root as default', () => {
      expect(themeContextFromSelector(":root")).toBe("default");
    });

    it('classifies [data-theme="light"] as light', () => {
      expect(themeContextFromSelector('[data-theme="light"]')).toBe("light");
    });

    it('classifies [data-domain="trading"] as domain', () => {
      expect(themeContextFromSelector('[data-domain="trading"]')).toBe("domain");
    });

    it('classifies [data-density="compact"] as density', () => {
      expect(themeContextFromSelector('[data-density="compact"]')).toBe("density");
    });

    it('classifies [data-market-region="intl"] as intl', () => {
      expect(themeContextFromSelector('[data-market-region="intl"]')).toBe("intl");
    });

    it('classifies [data-theme="light"][data-domain="markets"] as lightDomain', () => {
      expect(
        themeContextFromSelector('[data-theme="light"][data-domain="markets"]'),
      ).toBe("lightDomain");
    });

    it('classifies compound light+domain with spaces as lightDomain', () => {
      expect(
        themeContextFromSelector(
          '[data-theme="light"] [data-domain="markets"]',
        ),
      ).toBe("lightDomain");
    });

    it('classifies market-intl selector as intl', () => {
      expect(
        themeContextFromSelector('[data-market-intl="true"]'),
      ).toBe("intl");
    });

    it('classifies unknown selector as default', () => {
      expect(themeContextFromSelector('[data-unknown="value"]')).toBe("default");
    });

    it('classifies empty string as default', () => {
      expect(themeContextFromSelector("")).toBe("default");
    });
  });
});
