/**
 * R3 Strategy Studio view-models.
 *
 * 这些类型是 Strategy Studio 组件唯一消费的形态。mapper（`features/strategy/api/mappers.ts`）
 * 负责 generated snake_case DTO → 此处 camelCase view-model 的翻译，吸收后端契约漂移。
 *
 * 关键事实（设计依据）：
 * - 后端 `StrategyResponse.spec_json` 存储的是 legacy `StrategySpec` 的完整 `asdict()`
 *   （strategy_id/name/template/universe/asset_class/benchmark/scorer/selector/execution/
 *   constraints/params/signal_expressions/signal_weights/param_constraints/tags/
 *   required_datasets），不是 V2 canonical pipeline 形态。canonical payload
 *   （pipeline.nodes/sequence）由后端从 legacy 派生，仅供 hash/diff。前端编辑 legacy
 *   spec_json，validate 端点计算 canonical hash；本 view-model 只投影前端需要编辑的子集。
 * - `status` / `state` / `review_outcome` 在 generated schema 中是自由格式 string，
 *   枚举语义在 mapper 层用 LUT 派生（`lifecycleState` / `reviewOutcome`）。
 */

// === 状态派生（后端 status/state/review_outcome 是自由 string）===

/** 策略版本治理生命周期（从自由 string 派生，未知值收敛为 `unknown`）。 */
export type StrategyLifecycleState = "draft" | "review" | "approved" | "published" | "deprecated" | "unknown";

/** 审查结论（从自由 string 派生，未知值收敛为 `unknown`）。 */
export type StrategyReviewOutcome = "pending" | "approved" | "rejected" | "unknown";

// === legacy spec 结构（从 spec_json 解析）===

export type ScorerSpec = {
	readonly method: string;
	readonly params: Readonly<Record<string, unknown>>;
};

export type SelectorSpec = {
	readonly method: string;
	readonly params: Readonly<Record<string, unknown>>;
};

export type CostModelSpec = {
	readonly commissionRate?: number;
	readonly slippageBps?: number;
	readonly stampDuty?: number;
	readonly impactModel?: string;
};

export type ExecutionSpec = {
	readonly frequency: string;
	readonly method: string;
	/** 下单类型（后端 `default_order_type`，StrEnum 序列化为小写如 "market"），参与 canonical hash。 */
	readonly defaultOrderType: string;
	readonly costModel?: CostModelSpec;
};

export type ConstraintSpec = {
	readonly type: string;
	readonly params: Readonly<Record<string, unknown>>;
};

/** 参数约束支持的数据类型（与后端 `ParamConstraint.dtype` 对应）。 */
export type ParamDtype = "bool" | "int" | "float" | "str";

/**
 * 单个参数约束（legacy spec_json `param_constraints` 条目的结构化投影）。
 *
 * `min/max/step` 仅对数值型（int/float）有意义；`allowedValues` 用于枚举约束。
 * 所有可选字段缺失时不写入 view-model，mapper 容忍后端省略。
 */
export type ParamConstraintSpec = {
	readonly name: string;
	readonly dtype: ParamDtype;
	readonly minValue?: number;
	readonly maxValue?: number;
	readonly step?: number;
	readonly allowedValues: readonly string[];
};

/**
 * 策略定义（legacy spec_json 的结构化投影）。
 *
 * mapper 从 `Record<string, unknown>` 容错解析；缺失字段回退到中性默认，
 * 保证后端 spec 形态演进时前端不崩。
 */
export type StrategySpec = {
	readonly strategyId: string;
	readonly name: string;
	readonly template: string;
	readonly universe: string;
	readonly assetClass: string;
	readonly benchmark: string;
	readonly scorer: ScorerSpec;
	readonly selector: SelectorSpec;
	readonly execution: ExecutionSpec;
	readonly constraints: readonly ConstraintSpec[];
	readonly params: Readonly<Record<string, unknown>>;
	/**
	 * 信号表达式名列表（legacy `signal_expressions`）。
	 *
	 * 与 {@link signalWeights} 长度耦合——后端校验等长；编辑器必须成对增删/重排。
	 */
	readonly signalExpressions: readonly string[];
	/** 信号权重（legacy `signal_weights`），与 {@link signalExpressions} 一一对应。 */
	readonly signalWeights: readonly number[];
	/** 参数约束（legacy `param_constraints`），影响 canonical hash 的 parameter_schema。 */
	readonly paramConstraints: readonly ParamConstraintSpec[];
};

// === 策略列表 / 详情 ===

/** 策略列表项（`StrategyResponse` 顶层，不展开 spec）。 */
export type StrategyListItem = {
	readonly strategyId: string;
	readonly name: string;
	readonly version: number;
	readonly status: string;
	readonly lifecycleState: StrategyLifecycleState;
	readonly createdAt: string;
	readonly tags: readonly string[];
};

/** 策略详情（顶层 + spec 展开）。 */
export type StrategyDetail = StrategyListItem & {
	readonly spec: StrategySpec;
};

// === 版本（StrategyVersionResponse）===

export type StrategyVersion = {
	readonly strategyId: string;
	readonly version: number;
	readonly parentVersion: number | null;
	readonly specHash: string;
	readonly state: string;
	readonly lifecycleState: StrategyLifecycleState;
	readonly reviewOutcome: StrategyReviewOutcome;
	readonly createdAt: string;
};

// === validate 结果（StrategySpecValidationResponse）===

/** Pre-save candidate spec 校验结果（canonical hash + validity + change-detection）。 */
export type SpecValidation = {
	readonly strategyId: string;
	readonly version: number;
	readonly canonicalHash: string;
	readonly baseSpecHash: string;
	readonly changed: boolean;
	readonly valid: boolean;
	readonly errors: readonly string[];
};

// === diff 结果（StrategyVersionDiffResponse）===

/** 一处字段级 canonical spec 变更。 */
export type SpecChange = {
	readonly path: string;
	readonly op: string;
	readonly old: unknown;
	readonly new: unknown;
};

/** 版本 vs parent 的字段级 canonical spec diff。 */
export type SpecDiff = {
	readonly strategyId: string;
	readonly version: number;
	readonly parentVersion: number | null;
	readonly baseSpecHash: string;
	readonly targetSpecHash: string;
	readonly changed: boolean;
	readonly changes: readonly SpecChange[];
};

// === node descriptor（NodeDescriptorResponse）===

/**
 * 流水线节点描述符（只读调色板数据源）。
 *
 * `category` 取后端 `NodeCategory` 字符串值（UNIVERSE / FACTOR_SET / SCORER /
 * SELECTOR / ALLOCATOR / EXECUTION_ASSUMPTION / VALIDATION）。
 */
export type NodeDescriptorView = {
	readonly nodeType: string;
	readonly version: string;
	readonly category: string;
	readonly displayName: string;
	readonly implementationKey: string;
	readonly configSchema: Readonly<Record<string, string>>;
	readonly defaultConfig: Readonly<Record<string, unknown>>;
	readonly requiredDatasets: readonly string[];
	readonly capabilityTags: readonly string[];
	readonly deterministic: boolean;
};
