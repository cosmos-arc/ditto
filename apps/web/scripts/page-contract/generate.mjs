#!/usr/bin/env bun
/**
 * Contract Generator — 读取 JSON 合同 → 产出 shell TS
 *
 * 输入：contracts/pages/*.contract.json
 * 产出：
 *   - src/features/shell/page-contracts.generated.ts
 *
 * Usage: bun run generate-contracts
 */

import { readdir, readFile, writeFile, mkdir } from "node:fs/promises";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { validateContractSchema } from "./validators/contract-validator.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const WORKSPACE_ROOT = resolve(__dirname, "../../../..");
const WEB_ROOT = resolve(WORKSPACE_ROOT, "apps/web");

const CONTRACTS_DIR = resolve(WEB_ROOT, "contracts/pages");
const OUTPUT_TS = resolve(WEB_ROOT, "src/features/shell/page-contracts.generated.ts");

/* ------------------------------------------------------------------ */
/*  1. Load contracts                                                  */
/* ------------------------------------------------------------------ */

async function loadContracts() {
  const files = await readdir(CONTRACTS_DIR);
  const jsonFiles = files.filter((f) => f.endsWith(".contract.json"));

  if (jsonFiles.length === 0) {
    console.warn("[generate] No .contract.json files found in", CONTRACTS_DIR);
    return [];
  }

  const contracts = [];
  for (const file of jsonFiles.sort()) {
    const raw = await readFile(resolve(CONTRACTS_DIR, file), "utf-8");
    const contract = JSON.parse(raw);
    const validation = await validateContractSchema(contract);
    if (!validation.pass) throw new Error(`${file}: ${validation.message}`);
    contracts.push(contract);
  }

  return contracts;
}

/* ------------------------------------------------------------------ */
/*  2. Generate TypeScript (.generated.ts)                             */
/* ------------------------------------------------------------------ */

function generateTS(contracts) {
  const lines = [
    "// AUTO-GENERATED — do not edit manually",
    "// Run: bun run generate-contracts",
    "",
    "/* ------------------------------------------------------------------ */",
    "/*  Constants                                                          */",
    "/* ------------------------------------------------------------------ */",
    "",
  ];

  // Page Patterns enum
  const patterns = [...new Set(contracts.map((c) => c.pagePattern))];
  lines.push("export const PAGE_PATTERNS = [");
  for (const p of patterns) {
    lines.push(`  "${p}",`);
  }
  lines.push("] as const;");
  lines.push("");

  // Shell Families enum
  const families = [...new Set(contracts.map((c) => c.shellFamily))];
  lines.push("export const SHELL_FAMILIES = [");
  for (const f of families) {
    lines.push(`  "${f}",`);
  }
  lines.push("] as const;");
  lines.push("");

  // Prototype Sources
  const sources = [...new Set(contracts.map((c) => "prototype-backed"))];
  lines.push("export const PROTOTYPE_SOURCES = [");
  for (const s of sources) {
    lines.push(`  "${s}",`);
  }
  lines.push("] as const;");
  lines.push("");

  // Shell Slot Map — derived from contract slots
  const slotMap = {};
  for (const c of contracts) {
    if (!slotMap[c.shellFamily]) {
      slotMap[c.shellFamily] = new Set();
    }
    for (const slot of c.slots) {
      slotMap[c.shellFamily].add(slot.name);
    }
  }
  lines.push("export const SHELL_SLOT_MAP: Record<ShellFamily, string[]> = {");
  for (const [family, slots] of Object.entries(slotMap)) {
    lines.push(`  "${family}": [${[...slots].map((s) => `"${s}"`).join(", ")}],`);
  }
  lines.push("};");
  lines.push("");

  // Types
  lines.push("/* ------------------------------------------------------------------ */");
  lines.push("/*  Types                                                              */");
  lines.push("/* ------------------------------------------------------------------ */");
  lines.push("");
  lines.push("export type PagePattern = (typeof PAGE_PATTERNS)[number];");
  lines.push("export type ShellFamily = (typeof SHELL_FAMILIES)[number];");
  lines.push("export type PrototypeSource = (typeof PROTOTYPE_SOURCES)[number];");
  lines.push("");
  lines.push("export type PageLandingRouteStatus = \"missing\" | \"scaffolded\" | \"implemented\";");
  lines.push("export type PageLandingContractStatus = \"missing\" | \"draft\" | \"generated\" | \"verified\";");
  lines.push("export type PageLandingOverlayStatus = \"none\" | \"gallery-only\" | \"triggerable\" | \"implemented\";");
  lines.push("export type PageOverlayKind = \"drawer\" | \"sheet\" | \"modal\" | \"alert-dialog\" | \"toast\" | \"inline\";");
  lines.push("export type PageOverlayCloseBehavior = \"escape\" | \"outside-click\" | \"primary-action\";");
  lines.push("");
  lines.push("export interface PageLandingStatus {");
  lines.push("  reactRouteStatus: PageLandingRouteStatus;");
  lines.push("  featureModule: string;");
  lines.push("  contractStatus: PageLandingContractStatus;");
  lines.push("  overlayStatus: PageLandingOverlayStatus;");
  lines.push("  prototypeVerified: boolean;");
  lines.push("  reactParityVerified: boolean;");
  lines.push("  reactTestRefs?: string[];");
  lines.push("  reactComponentRefs?: string[];");
  lines.push("}");
  lines.push("");
  lines.push("export interface PageOverlayContract {");
  lines.push("  id: string;");
  lines.push("  kind: PageOverlayKind;");
  lines.push("  blocking: boolean;");
  lines.push("  requiredInDefaultFlow: boolean;");
  lines.push("  trigger: { slot: string; action: string };");
  lines.push("  prototypeSelector: string;");
  lines.push("  reactComponent: string;");
  lines.push("  closeBehavior: PageOverlayCloseBehavior[];");
  lines.push("}");
  lines.push("");

  // PageContract interface
  lines.push("export interface PageContract {");
  lines.push("  route: string;");
  lines.push("  pagePattern: PagePattern;");
  lines.push("  shellFamily: ShellFamily;");
  lines.push("  prototypeSource: PrototypeSource;");
  lines.push("  prototypeRef?: string;");
  lines.push("  requiredSlots: string[];");
  lines.push("  requiredStates: string[];");
  lines.push("  hasStatusBar?: boolean;");
  lines.push("  sidebarCollapsible?: boolean;");
  lines.push("  a11yRoles?: Record<string, string>;");
  lines.push("  responsiveBehavior?: Record<string, string>;");
  lines.push("  landing?: PageLandingStatus;");
  lines.push("  overlays?: PageOverlayContract[];");
  lines.push("}");
  lines.push("");

  // Page contracts array
  lines.push("/* ------------------------------------------------------------------ */");
  lines.push("/*  Page Contracts                                                     */");
  lines.push("/* ------------------------------------------------------------------ */");
  lines.push("");
  lines.push("export const PAGE_CONTRACTS: readonly PageContract[] = [");

  for (const c of contracts) {
    const requiredSlots = c.slots.map((s) => s.name);
    const requiredStates = [
      ...(c.states?.universal ?? []),
      ...(c.states?.pageSpecific ?? []),
    ];

    lines.push("  {");
    lines.push(`    route: "${c.route}",`);
    lines.push(`    pagePattern: "${c.pagePattern}",`);
    lines.push(`    shellFamily: "${c.shellFamily}",`);
    lines.push(`    prototypeSource: "prototype-backed",`);
    lines.push(`    prototypeRef: "${c.prototypeRef}",`);
    lines.push(`    requiredSlots: [${requiredSlots.map((s) => `"${s}"`).join(", ")}],`);
    lines.push(`    requiredStates: [${requiredStates.map((s) => `"${s}"`).join(", ")}],`);
    if (c.flags?.hasStatusBar) {
      lines.push("    hasStatusBar: true,");
    }
    if (c.flags?.sidebarCollapsible) {
      lines.push("    sidebarCollapsible: true,");
    }
    if (c.landing) {
      pushJsonProperty(lines, "landing", c.landing);
    }
    if (c.overlays) {
      pushJsonProperty(lines, "overlays", c.overlays);
    }

    // a11y roles from slots
    const a11yRoles = {};
    for (const slot of c.slots) {
      if (slot.a11yRole) a11yRoles[slot.name] = slot.a11yRole;
    }
    const a11yEntries = Object.entries(a11yRoles);
    if (a11yEntries.length > 0) {
      lines.push("    a11yRoles: {");
      for (const [name, role] of a11yEntries) {
        lines.push(`      "${name}": "${role}",`);
      }
      lines.push("    },");
    }

    // responsive behavior from slots
    const respBehaviors = {};
    for (const slot of c.slots) {
      if (slot.responsiveBehavior?.compact) respBehaviors[slot.name] = slot.responsiveBehavior.compact;
    }
    const respEntries = Object.entries(respBehaviors);
    if (respEntries.length > 0) {
      lines.push("    responsiveBehavior: {");
      for (const [name, behavior] of respEntries) {
        lines.push(`      "${name}": "${behavior}",`);
      }
      lines.push("    },");
    }

    lines.push("  },");
  }

  lines.push("] as const satisfies readonly PageContract[];");
  lines.push("");

  return lines.join("\n");
}

function pushJsonProperty(lines, propertyName, value) {
  const literalLines = JSON.stringify(value, null, 2).split("\n");
  lines.push(`    ${propertyName}: ${literalLines[0]}`);
  for (const line of literalLines.slice(1)) {
    lines.push(`    ${line}`);
  }
  lines[lines.length - 1] = `${lines.at(-1)},`;
}

async function main() {
  console.log("[generate] Loading contracts from", CONTRACTS_DIR);
  const contracts = await loadContracts();

  if (contracts.length === 0) {
    console.log("[generate] No contracts to generate. Exiting.");
    process.exit(0);
  }

  console.log(`[generate] Found ${contracts.length} contract(s)`);

  // Validate all inputs and finish serialization before replacing the shell output.
  const tsContent = generateTS(contracts);
  await mkdir(dirname(OUTPUT_TS), { recursive: true });
  await writeFile(OUTPUT_TS, tsContent, "utf-8");
  console.log("[generate] Wrote", OUTPUT_TS);

  console.log("[generate] Done.");
}

main().catch((err) => {
  console.error("[generate] Fatal:", err);
  process.exit(1);
});
