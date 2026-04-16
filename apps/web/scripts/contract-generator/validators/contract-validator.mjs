#!/usr/bin/env bun
/**
 * Contract Validator — 验证合同完整性的所有检查项
 *
 * 对应计划 §5.3 中的 10 项 BLOCK 级检查。
 * 每项检查返回 { pass, message, level }。
 *
 * Usage:
 *   import { validateContract } from "./validators/contract-validator.mjs";
 *   const result = await validateContract(contract, { contractsDir, prototypesDir });
 */

import { readFile, access } from "node:fs/promises";
import { resolve } from "node:path";
import Ajv from "ajv";

const ajv = new Ajv({ allErrors: true, strict: false })
  .addFormat("date", /^\d{4}-\d{2}-\d{2}$/);

/* ------------------------------------------------------------------ */
/*  Schema                                                             */
/* ------------------------------------------------------------------ */

let _schema = null;

async function loadSchema() {
  if (_schema) return _schema;
  const schemaPath = resolve(
    import.meta.dirname,
    "../schema/contract.schema.json",
  );
  const raw = await readFile(schemaPath, "utf-8");
  _schema = JSON.parse(raw);
  return _schema;
}

/* ------------------------------------------------------------------ */
/*  Check result type                                                  */
/* ------------------------------------------------------------------ */

/**
 * @typedef {"BLOCK" | "WARN" | "INFO"} CheckLevel
 * @typedef {{ pass: boolean; message: string; level: CheckLevel }} CheckResult
 */

/* ------------------------------------------------------------------ */
/*  Checks                                                             */
/* ------------------------------------------------------------------ */

/**
 * #1 JSON Schema 验证（ajv）
 */
async function checkSchema(contract) {
  const schema = await loadSchema();
  const validate = ajv.compile(schema);
  const valid = validate(contract);

  if (valid) {
    return { pass: true, message: "JSON Schema validation passed", level: "BLOCK" };
  }

  const errors = validate.errors.map((e) => `${e.instancePath} ${e.message}`);
  return {
    pass: false,
    message: `JSON Schema validation failed:\n${errors.join("\n")}`,
    level: "BLOCK",
  };
}

/**
 * #2 Prototype 文件存在且非空
 */
async function checkPrototypeExists(contract, ctx) {
  const prototypePath = resolve(ctx.root, contract.prototypeRef);
  try {
    const content = await readFile(prototypePath, "utf-8");
    if (content.trim().length === 0) {
      return {
        pass: false,
        message: `Prototype file is empty: ${contract.prototypeRef}`,
        level: "BLOCK",
      };
    }
    return {
      pass: true,
      message: `Prototype file exists: ${contract.prototypeRef}`,
      level: "BLOCK",
    };
  } catch {
    return {
      pass: false,
      message: `Prototype file not found: ${contract.prototypeRef}`,
      level: "BLOCK",
    };
  }
}

/**
 * #3 Blueprint section 可解析（检查 blueprintRefs 中的文件是否存在）
 */
async function checkBlueprintRefs(contract, ctx) {
  if (!contract.blueprintRefs || contract.blueprintRefs.length === 0) {
    return {
      pass: true,
      message: "No blueprint references defined (optional)", level: "INFO",
    };
  }

  const results = [];
  for (const ref of contract.blueprintRefs) {
    const blueprintPath = resolve(ctx.root, "docs/designs/specs", ref.split("#")[0]);
    try {
      await access(blueprintPath);
      results.push({ ref, exists: true });
    } catch {
      results.push({ ref, exists: false });
    }
  }

  const missing = results.filter((r) => !r.exists);
  if (missing.length > 0) {
    return {
      pass: false,
      message: `Blueprint refs not found: ${missing.map((r) => r.ref).join(", ")}`,
      level: "BLOCK",
    };
  }

  return {
    pass: true,
    message: `All ${results.length} blueprint refs found`,
    level: "BLOCK",
  };
}

/**
 * #4 每个 required slot 的 prototypeSelector 在 DOM 中存在
 *
 * 注意：此检查需要 Playwright 运行 prototype，在 --validate 命令中
 * 单独调用 validatePrototypeSelectors() 执行。
 * 这里只做格式检查：prototypeSelector 不为空。
 */
function checkPrototypeSelectorFormat(contract) {
  const requiredSlots = contract.slots.filter((s) => s.required);
  for (const slot of requiredSlots) {
    if (!slot.prototypeSelector || slot.prototypeSelector.trim().length === 0) {
      return {
        pass: false,
        message: `Slot "${slot.name}" missing prototypeSelector`,
        level: "BLOCK",
      };
    }
  }
  return {
    pass: true,
    message: `All ${requiredSlots.length} required slots have prototypeSelector`,
    level: "BLOCK",
  };
}

/**
 * #5 每个 required slot 的 reactSelector 格式合法
 */
function checkReactSelectorFormat(contract) {
  const requiredSlots = contract.slots.filter((s) => s.required);
  const dataSlotPattern = /^\[data-slot='[^']+'\]$/;
  const dataTestidPattern = /^\[data-testid='[^']+'\]$/;

  for (const slot of requiredSlots) {
    const sel = slot.reactSelector;
    if (!sel || sel.trim().length === 0) {
      return {
        pass: false,
        message: `Slot "${slot.name}" missing reactSelector`,
        level: "BLOCK",
      };
    }
    if (!dataSlotPattern.test(sel) && !dataTestidPattern.test(sel)) {
      return {
        pass: false,
        message: `Slot "${slot.name}" reactSelector has invalid format: "${sel}" (expected [data-slot='...'] or [data-testid='...'])`,
        level: "BLOCK",
      };
    }
  }
  return {
    pass: true,
    message: `All ${requiredSlots.length} required slots have valid reactSelector format`,
    level: "BLOCK",
  };
}

/**
 * #6 metrics.baseline 不为空
 */
function checkMetricsBaseline(contract) {
  if (!contract.metrics || !contract.metrics.baseline) {
    return {
      pass: false,
      message: "metrics.baseline is missing",
      level: "BLOCK",
    };
  }

  const entries = Object.entries(contract.metrics.baseline);
  if (entries.length === 0) {
    return {
      pass: false,
      message: "metrics.baseline is empty",
      level: "BLOCK",
    };
  }

  // Verify each baseline entry has required fields
  for (const [name, entry] of entries) {
    if (typeof entry.width !== "number" || typeof entry.height !== "number") {
      return {
        pass: false,
        message: `metrics.baseline["${name}"] missing width or height`,
        level: "BLOCK",
      };
    }
    if (!["content-driven", "fixed-width", "flex"].includes(entry.strategy)) {
      return {
        pass: false,
        message: `metrics.baseline["${name}"] has invalid strategy: "${entry.strategy}"`,
        level: "BLOCK",
      };
    }
  }

  return {
    pass: true,
    message: `metrics.baseline has ${entries.length} entries with valid structure`,
    level: "BLOCK",
  };
}

/**
 * #7 states.universal 包含 loading/empty/error/stale
 */
function checkUniversalStates(contract) {
  const required = ["loading", "empty", "error", "stale"];
  const universal = contract.states?.universal ?? [];

  const missing = required.filter((s) => !universal.includes(s));
  if (missing.length > 0) {
    return {
      pass: false,
      message: `states.universal missing: ${missing.join(", ")}`,
      level: "BLOCK",
    };
  }

  return {
    pass: true,
    message: "states.universal contains all 4 required states",
    level: "BLOCK",
  };
}

/**
 * #8 visualThresholds 中 0 容忍项实际值为 0
 */
function checkZeroToleranceThresholds(contract) {
  const vt = contract.visualThresholds;
  if (!vt) {
    return {
      pass: false,
      message: "visualThresholds is missing",
      level: "BLOCK",
    };
  }

  const zeroToleranceKeys = ["consoleErrors", "pageErrors", "missingSelectors", "targetMismatch"];
  const violations = [];

  for (const key of zeroToleranceKeys) {
    if (vt[key] !== 0) {
      violations.push(`${key}=${vt[key]} (expected 0)`);
    }
  }

  if (violations.length > 0) {
    return {
      pass: false,
      message: `Zero-tolerance thresholds violated: ${violations.join(", ")}`,
      level: "BLOCK",
    };
  }

  return {
    pass: true,
    message: "All zero-tolerance thresholds are 0",
    level: "BLOCK",
  };
}

/**
 * #9 shellFamily 在枚举中
 */
function checkShellFamily(contract) {
  const validFamilies = [
    "command-center", "analytical", "catalog", "object-hub",
    "studio", "ops-console", "radar",
  ];

  if (!validFamilies.includes(contract.shellFamily)) {
    return {
      pass: false,
      message: `Invalid shellFamily: "${contract.shellFamily}"`,
      level: "BLOCK",
    };
  }

  return {
    pass: true,
    message: `shellFamily "${contract.shellFamily}" is valid`,
    level: "BLOCK",
  };
}

/**
 * #10 pagePattern 在枚举中
 */
function checkPagePattern(contract) {
  const validPatterns = [
    "global-command-center", "analytical-overview", "catalog-screener",
    "object-hub", "studio-builder", "queue-ops-console",
    "ledger-execution-console", "config-integration-console",
  ];

  if (!validPatterns.includes(contract.pagePattern)) {
    return {
      pass: false,
      message: `Invalid pagePattern: "${contract.pagePattern}"`,
      level: "BLOCK",
    };
  }

  return {
    pass: true,
    message: `pagePattern "${contract.pagePattern}" is valid`,
    level: "BLOCK",
  };
}

/* ------------------------------------------------------------------ */
/*  Main validation entry                                              */
/* ------------------------------------------------------------------ */

/**
 * 验证一份合同的所有检查项
 *
 * @param {object} contract — 合同 JSON 对象
 * @param {{ root: string }} ctx — 上下文（root = 项目根目录）
 * @returns {Promise<{ passed: boolean; checks: CheckResult[]; summary: string }>}
 */
export async function validateContract(contract, ctx) {
  const checks = [
    await checkSchema(contract),
    await checkPrototypeExists(contract, ctx),
    await checkBlueprintRefs(contract, ctx),
    checkPrototypeSelectorFormat(contract),
    checkReactSelectorFormat(contract),
    checkMetricsBaseline(contract),
    checkUniversalStates(contract),
    checkZeroToleranceThresholds(contract),
    checkShellFamily(contract),
    checkPagePattern(contract),
  ];

  const blockFails = checks.filter((c) => c.level === "BLOCK" && !c.pass);
  const passed = blockFails.length === 0;

  return {
    passed,
    checks,
    summary: passed
      ? `All ${checks.length} checks passed`
      : `${blockFails.length} BLOCK check(s) failed out of ${checks.length}`,
  };
}

/**
 * 验证所有合同文件
 *
 * @param {{ root: string; contractsDir: string }} ctx
 * @returns {Promise<{ results: Array<{ id: string; passed: boolean; checks: CheckResult[] }>; allPassed: boolean }>}
 */
export async function validateAllContracts(ctx) {
  const { readdir, readFile } = await import("node:fs/promises");
  const files = await readdir(ctx.contractsDir);
  const jsonFiles = files.filter((f) => f.endsWith(".contract.json")).sort();

  const results = [];
  for (const file of jsonFiles) {
    const raw = await readFile(resolve(ctx.contractsDir, file), "utf-8");
    const contract = JSON.parse(raw);
    const result = await validateContract(contract, ctx);
    results.push({ id: contract.id, ...result });
  }

  return {
    results,
    allPassed: results.every((r) => r.passed),
  };
}
