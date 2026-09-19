import { describe, expect, test } from "vitest";
import { CHART_FALLBACK_COLORS } from "../src/lib/oklch.ts";
import { extractTokensFromCss, readAllTokenFiles, resolveColor } from "./token-utils.mjs";

/**
 * 守护 src/lib/oklch.ts 的图表回退色与 design-tokens :root 的解析终值同步：
 * token 调整而未同步回退表时，本测试失败。
 */

function buildTokenMap() {
  let allCss = "";
  for (const { css } of readAllTokenFiles()) {
    allCss += `${css.match(/:root\s*\{([^}]*)\}/su)?.[1] ?? ""}\n`;
  }
  const tokens = extractTokensFromCss(allCss);
  // 与 audit-wcag-contrast 相同的静态处理：atmosphere 默认抵消运行时偏移
  tokens["surface-app-atmosphere"] = "var(--neutral-0)";
  return new Map(Object.entries(tokens));
}

/** 顶层逗号拆分 var() 名与 fallback（允许 fallback 内嵌 var()）。 */
function parseVarReference(value) {
  const trimmed = value.trim();
  if (!trimmed.startsWith("var(") || !trimmed.endsWith(")")) return null;
  const inner = trimmed.slice(4, -1);
  let depth = 0;
  for (let index = 0; index < inner.length; index += 1) {
    const char = inner[index];
    if (char === "(") depth += 1;
    else if (char === ")") depth -= 1;
    else if (char === "," && depth === 0) {
      return { name: inner.slice(0, index).trim(), fallback: inner.slice(index + 1).trim() };
    }
  }
  return { name: inner.trim(), fallback: null };
}

function resolveRaw(value, tokens, depth = 0) {
  if (depth > 12) return null;
  const reference = parseVarReference(value);
  if (reference) {
    const next =
      tokens.get(reference.name) ?? tokens.get(reference.name.replace(/^--/u, "")) ?? reference.fallback;
    return next ? resolveRaw(next, tokens, depth + 1) : null;
  }
  return value;
}

function toEngineColor(raw, tokens) {
  const literal = resolveRaw(raw, tokens);
  expect(literal, `token value must resolve to a color literal: ${raw}`).not.toBeNull();
  const resolved = resolveColor(literal ?? "", tokens);
  expect(resolved, `token literal must parse as oklch: ${literal}`).not.toBeNull();
  const [r = 0, g = 0, b = 0] = resolved?.rgb ?? [];
  const hex = (channel) =>
    Math.round(channel * 255)
      .toString(16)
      .padStart(2, "0");
  if ((resolved?.alpha ?? 1) < 1) {
    return `rgba(${Math.round(r * 255)}, ${Math.round(g * 255)}, ${Math.round(b * 255)}, ${resolved?.alpha})`;
  }
  return `#${hex(r)}${hex(g)}${hex(b)}`;
}

describe("chart fallback colors stay in sync with design tokens", () => {
  test("every fallback equals the resolved dark :root token value", () => {
    const tokens = buildTokenMap();
    for (const [cssVar, fallback] of Object.entries(CHART_FALLBACK_COLORS)) {
      // cssVar 形如 "var(--chart-bg)"；extractTokensFromCss 的键不带 -- 前缀
      const name = cssVar.slice("var(--".length, -1);
      const raw = tokens.get(name);
      expect(raw, `${name} must be declared in design tokens`).toBeDefined();
      expect(fallback).toBe(toEngineColor(raw ?? "", tokens));
    }
  });
});
