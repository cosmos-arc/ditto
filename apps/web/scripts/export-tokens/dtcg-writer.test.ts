// ─────────────────────────────────────────────
// Tests for dtcg-writer.ts
// JSON output: path utilities, nested value setting, grouping.
// ─────────────────────────────────────────────

import { describe, it, expect } from "vitest";
import {
  tokenNameToNestedPath,
  setNestedValue,
  groupBySelector,
} from "./dtcg-writer";
import type { RawCssToken, DtcgToken } from "./types";

describe("dtcg-writer", () => {
  // ── tokenNameToNestedPath ──────────────────

  describe("tokenNameToNestedPath", () => {
    it("splits simple color names correctly", () => {
      expect(tokenNameToNestedPath("neutral-0")).toEqual(["neutral", "0"]);
      expect(tokenNameToNestedPath("brand-500")).toEqual(["brand", "500"]);
      expect(tokenNameToNestedPath("brand-300")).toEqual(["brand", "300"]);
    });

    it("splits surface with sub-type prefix", () => {
      // "panel" is in SUB_PREFIXES, so it becomes its own nesting level
      expect(tokenNameToNestedPath("surface-panel-base")).toEqual(["surface", "panel", "base"]);
    });

    it("splits component names with size prefix", () => {
      // "sm" is in SUB_PREFIXES but "padding" is not → "sm" + "padding" merge
      expect(tokenNameToNestedPath("btn-sm-padding-y")).toEqual(["btn", "sm-padding-y"]);
      // "padding" is not in SUB_PREFIXES, no numeric separator → stays merged
      expect(tokenNameToNestedPath("btn-padding-y")).toEqual(["btn-padding-y"]);
    });

    it("splits font tokens correctly", () => {
      // "size" is in SUB_PREFIXES, "12" is numeric → 3 levels
      expect(tokenNameToNestedPath("font-size-12")).toEqual(["font", "size", "12"]);
      // "weight" is in SUB_PREFIXES, but "regular" is not → merge
      expect(tokenNameToNestedPath("font-weight-regular")).toEqual(["font", "weight-regular"]);
      // "family" is in SUB_PREFIXES, but "ui"/"numeric" are not → merge
      expect(tokenNameToNestedPath("font-family-ui")).toEqual(["font", "family-ui"]);
      expect(tokenNameToNestedPath("font-size-10")).toEqual(["font", "size", "10"]);
      expect(tokenNameToNestedPath("font-family-numeric")).toEqual(["font", "family-numeric"]);
    });

    it("splits density tokens correctly", () => {
      expect(tokenNameToNestedPath("density-row-height")).toEqual(["density", "row-height"]);
      expect(tokenNameToNestedPath("density-panel-padding")).toEqual(["density", "panel-padding"]);
    });

    it("splits market tokens correctly", () => {
      // "up" is in SUB_PREFIXES but "fg" is not → merge back
      expect(tokenNameToNestedPath("market-up-fg")).toEqual(["market", "up-fg"]);
      // "down" + "bg" where bg IS in SUB_PREFIXES → separate
      expect(tokenNameToNestedPath("market-down-bg")).toEqual(["market", "down", "bg"]);
      expect(tokenNameToNestedPath("market-flat-fg")).toEqual(["market", "flat-fg"]);
      // "strong" in SUB_PREFIXES but "fg" is not → merge
      expect(tokenNameToNestedPath("market-strong-fg")).toEqual(["market", "strong-fg"]);
    });

    it("splits risk tokens correctly", () => {
      // "high" in SUB_PREFIXES, "fg" not → merge
      expect(tokenNameToNestedPath("risk-high-fg")).toEqual(["risk", "high-fg"]);
      // "low" in SUB_PREFIXES, "bg" in SUB_PREFIXES → separate
      expect(tokenNameToNestedPath("risk-low-bg")).toEqual(["risk", "low", "bg"]);
      expect(tokenNameToNestedPath("risk-critical-bg")).toEqual(["risk", "critical", "bg"]);
      // "near" in SUB_PREFIXES, "limit" not → merge
      expect(tokenNameToNestedPath("risk-near-limit-fg")).toEqual(["risk", "near-limit-fg"]);
    });

    it("splits execution tokens correctly", () => {
      // "pending" in SUB_PREFIXES, "fg" not → merge
      expect(tokenNameToNestedPath("execution-pending-fg")).toEqual(["execution", "pending-fg"]);
      // "filled" in SUB_PREFIXES, "bg" in SUB_PREFIXES → separate
      expect(tokenNameToNestedPath("execution-filled-bg")).toEqual(["execution", "filled", "bg"]);
    });

    it("splits interaction tokens correctly", () => {
      // "focus" is NOT in SUB_PREFIXES → merged with first segment
      expect(tokenNameToNestedPath("interaction-focus-ring")).toEqual(["interaction-focus-ring"]);
      // "hover" not in SUB_PREFIXES → "interaction-hover" merged, then "subtle" IS → new level, "bg" → merge
      expect(tokenNameToNestedPath("interaction-hover-subtle-bg")).toEqual(["interaction-hover", "subtle", "bg"]);
      // "dragging" not in SUB_PREFIXES → all merged
      expect(tokenNameToNestedPath("interaction-dragging-shadow")).toEqual(["interaction-dragging-shadow"]);
    });

    it("splits text tokens correctly", () => {
      // "primary" in SUB_PREFIXES, no more segments → 2 levels
      expect(tokenNameToNestedPath("text-primary")).toEqual(["text", "primary"]);
      expect(tokenNameToNestedPath("text-secondary")).toEqual(["text", "secondary"]);
      // "data" in SUB_PREFIXES, "stale" also in SUB_PREFIXES → separate
      expect(tokenNameToNestedPath("text-data-stale")).toEqual(["text", "data", "stale"]);
      // "link" NOT in SUB_PREFIXES → merge
      expect(tokenNameToNestedPath("text-link-hover")).toEqual(["text", "link-hover"]);
    });

    it("splits border tokens correctly", () => {
      // "subtle" in SUB_PREFIXES
      expect(tokenNameToNestedPath("border-subtle")).toEqual(["border", "subtle"]);
      expect(tokenNameToNestedPath("border-default")).toEqual(["border", "default"]);
      expect(tokenNameToNestedPath("border-strong")).toEqual(["border", "strong"]);
      // "focus" NOT in SUB_PREFIXES → merged
      expect(tokenNameToNestedPath("border-focus")).toEqual(["border-focus"]);
    });

    it("splits brand tokens with sub-type correctly", () => {
      // "accent" in SUB_PREFIXES
      expect(tokenNameToNestedPath("brand-accent")).toEqual(["brand", "accent"]);
      // "accent" in SUB_PREFIXES, "subtle" in SUB_PREFIXES → separate
      expect(tokenNameToNestedPath("brand-accent-subtle")).toEqual(["brand", "accent", "subtle"]);
      // "accent" in SUB_PREFIXES, "fg" not → merge
      expect(tokenNameToNestedPath("brand-accent-fg")).toEqual(["brand", "accent-fg"]);
      // "signature" in SUB_PREFIXES, "fg" not → merge
      expect(tokenNameToNestedPath("brand-signature-fg")).toEqual(["brand", "signature-fg"]);
    });

    it("splits atmosphere tokens correctly", () => {
      // "hue" in SUB_PREFIXES, "shift" in SUB_PREFIXES → separate
      expect(tokenNameToNestedPath("atmosphere-hue-shift")).toEqual(["atmosphere", "hue", "shift"]);
      // "chroma" in SUB_PREFIXES, "boost" not → merge
      expect(tokenNameToNestedPath("atmosphere-chroma-boost")).toEqual(["atmosphere", "chroma-boost"]);
      // "lightness" in SUB_PREFIXES, "shift" in SUB_PREFIXES → separate
      expect(tokenNameToNestedPath("atmosphere-lightness-shift")).toEqual(["atmosphere", "lightness", "shift"]);
    });

    it("splits motion tokens correctly", () => {
      expect(tokenNameToNestedPath("motion-duration-fast")).toEqual(["motion", "duration-fast"]);
      expect(tokenNameToNestedPath("motion-easing-standard")).toEqual(["motion", "easing-standard"]);
    });

    it("splits domain tokens correctly", () => {
      expect(tokenNameToNestedPath("domain-bg-green")).toEqual(["domain", "bg-green"]);
    });

    it("handles single-segment names", () => {
      expect(tokenNameToNestedPath("brand")).toEqual(["brand"]);
    });

    it("handles empty string", () => {
      expect(tokenNameToNestedPath("")).toEqual([""]);
    });

    it("splits spacing tokens correctly", () => {
      expect(tokenNameToNestedPath("space-8")).toEqual(["space", "8"]);
      expect(tokenNameToNestedPath("space-16")).toEqual(["space", "16"]);
    });

    it("splits radius tokens correctly", () => {
      expect(tokenNameToNestedPath("radius-4")).toEqual(["radius", "4"]);
      expect(tokenNameToNestedPath("radius-12")).toEqual(["radius", "12"]);
    });
  });

  // ── setNestedValue ─────────────────────────

  describe("setNestedValue", () => {
    it("sets a value at a single-level path", () => {
      const obj: Record<string, unknown> = {};
      const token: DtcgToken = { $value: "#ff0000", $type: "color" };
      setNestedValue(obj, ["brand"], token);
      expect(obj["brand"]).toEqual(token);
    });

    it("sets a value at a two-level path", () => {
      const obj: Record<string, unknown> = {};
      const token: DtcgToken = { $value: "#2e97ca", $type: "color" };
      setNestedValue(obj, ["brand", "500"], token);
      expect(obj["brand"]).toBeDefined();
      expect((obj["brand"] as Record<string, unknown>)["500"]).toEqual(token);
    });

    it("sets a value at a three-level path", () => {
      const obj: Record<string, unknown> = {};
      const token: DtcgToken = { $value: "0.75rem", $type: "dimension" };
      setNestedValue(obj, ["font", "size", "12"], token);
      expect(obj["font"]).toBeDefined();
      expect((obj["font"] as Record<string, unknown>)["size"]).toBeDefined();
      expect(((obj["font"] as Record<string, unknown>)["size"] as Record<string, unknown>)["12"]).toEqual(token);
    });

    it("creates intermediate objects when they do not exist", () => {
      const obj: Record<string, unknown> = {};
      const token: DtcgToken = { $value: "#ff0000", $type: "color" };
      setNestedValue(obj, ["a", "b", "c", "d"], token);
      expect((obj["a"] as Record<string, unknown>)["b"]).toBeDefined();
      expect(((obj["a"] as Record<string, unknown>)["b"] as Record<string, unknown>)["c"]).toBeDefined();
      expect((((obj["a"] as Record<string, unknown>)["b"] as Record<string, unknown>)["c"] as Record<string, unknown>)["d"]).toEqual(token);
    });

    it("overwrites non-object intermediate values with objects", () => {
      const obj: Record<string, unknown> = { brand: "old-value" };
      const token: DtcgToken = { $value: "#2e97ca", $type: "color" };
      setNestedValue(obj, ["brand", "500"], token);
      expect(obj["brand"]).toBeDefined();
      expect(typeof obj["brand"]).toBe("object");
      expect((obj["brand"] as Record<string, unknown>)["500"]).toEqual(token);
    });

    it("overwrites null intermediate values with objects", () => {
      const obj: Record<string, unknown> = { brand: null };
      const token: DtcgToken = { $value: "#2e97ca", $type: "color" };
      setNestedValue(obj, ["brand", "500"], token);
      expect(typeof obj["brand"]).toBe("object");
    });

    it("overwrites array intermediate values with objects", () => {
      const obj: Record<string, unknown> = { brand: [1, 2, 3] };
      const token: DtcgToken = { $value: "#2e97ca", $type: "color" };
      setNestedValue(obj, ["brand", "500"], token);
      expect(Array.isArray(obj["brand"])).toBe(false);
      expect((obj["brand"] as Record<string, unknown>)["500"]).toEqual(token);
    });

    it("allows setting multiple values at different paths", () => {
      const obj: Record<string, unknown> = {};
      const token1: DtcgToken = { $value: "#2e97ca", $type: "color" };
      const token2: DtcgToken = { $value: "#ff0000", $type: "color" };
      setNestedValue(obj, ["brand", "500"], token1);
      setNestedValue(obj, ["brand", "600"], token2);
      expect((obj["brand"] as Record<string, unknown>)["500"]).toEqual(token1);
      expect((obj["brand"] as Record<string, unknown>)["600"]).toEqual(token2);
    });

    it("allows overwriting existing values", () => {
      const obj: Record<string, unknown> = {};
      const token1: DtcgToken = { $value: "#2e97ca", $type: "color" };
      const token2: DtcgToken = { $value: "#ff0000", $type: "color" };
      setNestedValue(obj, ["brand", "500"], token1);
      setNestedValue(obj, ["brand", "500"], token2);
      expect((obj["brand"] as Record<string, unknown>)["500"]).toEqual(token2);
    });
  });

  // ── groupBySelector ────────────────────────

  describe("groupBySelector", () => {
    it("groups tokens by selector", () => {
      const tokens: RawCssToken[] = [
        {
          name: "brand-500",
          value: "oklch(0.640 0.120 235)",
          sourceFile: "tokens-base.css",
          selector: ":root",
          layer: "base",
          context: "default",
        },
        {
          name: "neutral-0",
          value: "oklch(0.166 0.010 253)",
          sourceFile: "tokens-base.css",
          selector: ":root",
          layer: "base",
          context: "default",
        },
        {
          name: "brand-500",
          value: "oklch(0.550 0.100 235)",
          sourceFile: "tokens-base.css",
          selector: '[data-theme="light"]',
          layer: "base",
          context: "light",
        },
      ];

      const groups = groupBySelector(tokens);

      expect(groups.size).toBe(2);
      expect(groups.get(":root")?.length).toBe(2);
      expect(groups.get('[data-theme="light"]')?.length).toBe(1);
    });

    it("returns empty map for empty array", () => {
      const groups = groupBySelector([]);
      expect(groups.size).toBe(0);
    });

    it("handles tokens with a single unique selector", () => {
      const tokens: RawCssToken[] = [
        {
          name: "brand-500",
          value: "oklch(0.640 0.120 235)",
          sourceFile: "tokens-base.css",
          selector: ":root",
          layer: "base",
          context: "default",
        },
      ];

      const groups = groupBySelector(tokens);
      expect(groups.size).toBe(1);
      expect(groups.get(":root")?.length).toBe(1);
    });
  });
});
