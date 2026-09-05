// ─────────────────────────────────────────────
// Tests for composite-builder.ts
// Builds structured DTCG tokens from parsed composite values.
// ─────────────────────────────────────────────

import { describe, it, expect } from "vitest";
import { isComposite, buildCompositeValue } from "./composite-builder";
import type { ParsedValue } from "./types";

function asRecord(value: unknown): Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new TypeError("Expected a structured DTCG value");
  }
  return value as Record<string, unknown>;
}

describe("composite-builder", () => {
  // ── isComposite ────────────────────────────

  describe("isComposite", () => {
    it("returns true for composite-shadow", () => {
      const pv: ParsedValue = { type: "composite-shadow", value: "0 8px 24px oklch(0 0 0 / 0.4)" };
      expect(isComposite(pv)).toBe(true);
    });

    it("returns true for composite-border", () => {
      const pv: ParsedValue = { type: "composite-border", value: "1px solid var(--border-subtle)" };
      expect(isComposite(pv)).toBe(true);
    });

    it("returns true for composite-transition", () => {
      const pv: ParsedValue = { type: "composite-transition", value: "var(--a) var(--b)" };
      expect(isComposite(pv)).toBe(true);
    });

    it("returns true for composite-shorthand", () => {
      const pv: ParsedValue = { type: "composite-shorthand", value: "var(--space-10) var(--space-12)" };
      expect(isComposite(pv)).toBe(true);
    });

    it("returns false for color", () => {
      const pv: ParsedValue = { type: "color", oklch: "oklch(0.640 0.120 235)" };
      expect(isComposite(pv)).toBe(false);
    });

    it("returns false for reference", () => {
      const pv: ParsedValue = { type: "reference", variableName: "brand-500" };
      expect(isComposite(pv)).toBe(false);
    });

    it("returns false for dimension", () => {
      const pv: ParsedValue = { type: "dimension", value: "0.5rem" };
      expect(isComposite(pv)).toBe(false);
    });

    it("returns false for transparent", () => {
      const pv: ParsedValue = { type: "transparent" };
      expect(isComposite(pv)).toBe(false);
    });
  });

  // ── buildCompositeValue ────────────────────

  describe("buildCompositeValue", () => {
    const emptyRefMap = new Map<string, string>();

    // ─ Shadow ─

    it("builds shadow token from oklch color", () => {
      const pv: ParsedValue = {
        type: "composite-shadow",
        value: "0 8px 24px oklch(0 0 0 / 0.4)",
      };
      const token = buildCompositeValue("interaction-dragging-shadow", pv, emptyRefMap);
      expect(token).not.toBeNull();
      expect(token!.$type).toBe("shadow");
    });

    it("shadow token has structured $value with offsetX, offsetY, blur, color", () => {
      const pv: ParsedValue = {
        type: "composite-shadow",
        value: "0 8px 24px oklch(0 0 0 / 0.4)",
      };
      const token = buildCompositeValue("interaction-dragging-shadow", pv, emptyRefMap);
      const val = asRecord(token!.$value);
      expect(val).toHaveProperty("offsetX");
      expect(val).toHaveProperty("offsetY");
      expect(val).toHaveProperty("blur");
      expect(val).toHaveProperty("color");
    });

    it("shadow offsetX is dimension with value 0 and unit px", () => {
      const pv: ParsedValue = {
        type: "composite-shadow",
        value: "0 8px 24px oklch(0 0 0 / 0.4)",
      };
      const token = buildCompositeValue("interaction-dragging-shadow", pv, emptyRefMap);
      const val = asRecord(token!.$value);
      const offsetX = val["offsetX"] as Record<string, unknown>;
      expect(offsetX["value"]).toBe("0");
      expect(offsetX["type"]).toBe("dimension");
      expect(offsetX["unit"]).toBe("px");
    });

    it("shadow offsetY is dimension with value 8 and unit px", () => {
      const pv: ParsedValue = {
        type: "composite-shadow",
        value: "0 8px 24px oklch(0 0 0 / 0.4)",
      };
      const token = buildCompositeValue("interaction-dragging-shadow", pv, emptyRefMap);
      const val = asRecord(token!.$value);
      const offsetY = val["offsetY"] as Record<string, unknown>;
      expect(offsetY["value"]).toBe("8");
      expect(offsetY["unit"]).toBe("px");
    });

    it("shadow blur is dimension with value 24 and unit px", () => {
      const pv: ParsedValue = {
        type: "composite-shadow",
        value: "0 8px 24px oklch(0 0 0 / 0.4)",
      };
      const token = buildCompositeValue("interaction-dragging-shadow", pv, emptyRefMap);
      const val = asRecord(token!.$value);
      const blur = val["blur"] as Record<string, unknown>;
      expect(blur["value"]).toBe("24");
      expect(blur["unit"]).toBe("px");
    });

    it("shadow color is a hex string (converted from oklch)", () => {
      const pv: ParsedValue = {
        type: "composite-shadow",
        value: "0 8px 24px oklch(0 0 0 / 0.4)",
      };
      const token = buildCompositeValue("interaction-dragging-shadow", pv, emptyRefMap);
      const val = asRecord(token!.$value);
      expect(val["color"]).toMatch(/^#[0-9a-f]{8}$/);
    });

    it("shadow with less than 4 parts returns other type", () => {
      const pv: ParsedValue = {
        type: "composite-shadow",
        value: "0 8px",
      };
      const token = buildCompositeValue("invalid-shadow", pv, emptyRefMap);
      expect(token).not.toBeNull();
      expect(token!.$type).toBe("other");
    });

    it("shadow stores compositeType in extensions", () => {
      const pv: ParsedValue = {
        type: "composite-shadow",
        value: "0 8px 24px oklch(0 0 0 / 0.4)",
      };
      const token = buildCompositeValue("interaction-dragging-shadow", pv, emptyRefMap);
      const ext = token!.$extensions?.["com.ditto-app"];
      expect(ext?.compositeType).toBe("shadow");
    });

    // ─ Border ─

    it("builds border token with var() color reference", () => {
      const pv: ParsedValue = {
        type: "composite-border",
        value: "1px solid var(--border-subtle)",
      };
      const refMap = new Map<string, string>([
        ["border-subtle", "{semantic.border.subtle}"],
      ]);
      const token = buildCompositeValue("card-border", pv, refMap);
      expect(token).not.toBeNull();
      expect(token!.$type).toBe("border");
    });

    it("border token has structured $value with color, style, width", () => {
      const pv: ParsedValue = {
        type: "composite-border",
        value: "1px solid var(--border-subtle)",
      };
      const refMap = new Map<string, string>([
        ["border-subtle", "{semantic.border.subtle}"],
      ]);
      const token = buildCompositeValue("card-border", pv, refMap);
      const val = asRecord(token!.$value);
      expect(val["color"]).toBe("{semantic.border.subtle}");
      expect(val["style"]).toBe("solid");
      expect(val["width"]).toBe("1px");
    });

    it("border with oklch color converts to hex", () => {
      const pv: ParsedValue = {
        type: "composite-border",
        value: "1px solid oklch(0.255 0.006 253)",
      };
      const token = buildCompositeValue("panel-border", pv, emptyRefMap);
      const val = asRecord(token!.$value);
      expect(val["color"]).toMatch(/^#[0-9a-f]{6}$/);
    });

    it("border with transparent color preserves transparent", () => {
      const pv: ParsedValue = {
        type: "composite-border",
        value: "1px solid transparent",
      };
      const token = buildCompositeValue("border-transparent", pv, emptyRefMap);
      const val = asRecord(token!.$value);
      expect(val["color"]).toBe("transparent");
    });

    it("border with unresolved var() keeps raw var() string", () => {
      const pv: ParsedValue = {
        type: "composite-border",
        value: "1px solid var(--border-subtle)",
      };
      const token = buildCompositeValue("card-border", pv, emptyRefMap);
      const val = asRecord(token!.$value);
      expect(val["color"]).toBe("var(--border-subtle)");
    });

    it("border with less than 3 parts returns other type", () => {
      const pv: ParsedValue = {
        type: "composite-border",
        value: "1px solid",
      };
      const token = buildCompositeValue("invalid-border", pv, emptyRefMap);
      expect(token).not.toBeNull();
      expect(token!.$type).toBe("other");
    });

    it("border stores compositeType in extensions", () => {
      const pv: ParsedValue = {
        type: "composite-border",
        value: "1px solid var(--border-subtle)",
      };
      const refMap = new Map<string, string>([
        ["border-subtle", "{semantic.border.subtle}"],
      ]);
      const token = buildCompositeValue("card-border", pv, refMap);
      const ext = token!.$extensions?.["com.ditto-app"];
      expect(ext?.compositeType).toBe("border");
    });

    // ─ Shorthand ─

    it("builds shorthand token as other type", () => {
      const pv: ParsedValue = {
        type: "composite-shorthand",
        value: "var(--space-10) var(--space-12)",
      };
      const token = buildCompositeValue("card-padding", pv, emptyRefMap);
      expect(token).not.toBeNull();
      expect(token!.$type).toBe("other");
      expect(token!.$value).toBe("var(--space-10) var(--space-12)");
    });

    it("shorthand stores compositeType in extensions", () => {
      const pv: ParsedValue = {
        type: "composite-shorthand",
        value: "var(--space-10) var(--space-12)",
      };
      const token = buildCompositeValue("card-padding", pv, emptyRefMap);
      const ext = token!.$extensions?.["com.ditto-app"];
      expect(ext?.compositeType).toBe("shorthand");
    });

    // ─ Non-composite returns null ─

    it("returns null for color type", () => {
      const pv: ParsedValue = { type: "color", oklch: "oklch(0.640 0.120 235)" };
      expect(buildCompositeValue("brand-500", pv, emptyRefMap)).toBeNull();
    });

    it("returns null for reference type", () => {
      const pv: ParsedValue = { type: "reference", variableName: "brand-500" };
      expect(buildCompositeValue("text-link", pv, emptyRefMap)).toBeNull();
    });

    it("returns null for dimension type", () => {
      const pv: ParsedValue = { type: "dimension", value: "0.5rem" };
      expect(buildCompositeValue("space-8", pv, emptyRefMap)).toBeNull();
    });
  });
});
