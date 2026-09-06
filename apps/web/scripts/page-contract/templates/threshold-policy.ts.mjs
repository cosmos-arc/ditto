/**
 * Threshold Policy — 根据页面特征计算默认验证阈值
 *
 * Shell slot 严阈值（3%），content subSlot 宽阈值（5-8%）。
 */

/**
 * Shell slot 的默认 L2 验证阈值
 */
export const SHELL_SLOT_DEFAULT_THRESHOLD = {
  x: 4,
  y: 4,
  widthRatio: 0.03,
  heightRatio: 0.05,
};

/**
 * SubSlot 的默认 L2 验证阈值（更宽松）
 */
export const SUBSLOT_DEFAULT_THRESHOLD = {
  widthRatio: 0.05,
  heightRatio: 0.05,
};

/**
 * 根据 infoLevel 返回默认阈值
 */
export function getDefaultThreshold(infoLevel) {
  switch (infoLevel) {
    case "l0":
      return null; // l0 只检查存在性，不需要布局阈值
    case "l1":
      return null; // l1 只检查 token 合规，不需要布局阈值
    case "l2":
    case "l2.5":
      return { ...SHELL_SLOT_DEFAULT_THRESHOLD };
    case "l3":
      return { ...SHELL_SLOT_DEFAULT_THRESHOLD, pixelDiffRatio: 0.02 };
    default:
      return { ...SHELL_SLOT_DEFAULT_THRESHOLD };
  }
}

/**
 * 页面级 visualThresholds 默认值
 */
export const DEFAULT_VISUAL_THRESHOLDS = {
  consoleErrors: 0,
  pageErrors: 0,
  missingSelectors: 0,
  targetMismatch: 0,
  pixelDiffRatio: 0.02,
};
