/**
 * Strategy DTO → view-model 翻译层。
 *
 * 唯一消费 generated snake_case DTO 的地方；组件只认 {@link "@/types/strategy"}
 * 中的 camelCase view-model。后端 spec_json 存的是 legacy `StrategySpec` asdict，
 * {@link parseSpecJson} 用 type guard 容错解析，缺失字段回退中性默认。
 */
import type { components } from "@/types/generated/api";
import type {
	ConstraintSpec,
	CostModelSpec,
	ExecutionSpec,
	NodeDescriptorView,
	ParamConstraintSpec,
	ParamDtype,
	ScorerSpec,
	SelectorSpec,
	SpecChange,
	SpecDiff,
	SpecValidation,
	StrategyDetail,
	StrategyLifecycleState,
	StrategyListItem,
	StrategyReviewOutcome,
	StrategySpec,
	StrategyVersion,
	StrategyVersionDetail,
} from "@/types/strategy";

type StrategyResponse = components["schemas"]["StrategyResponse"];
type StrategyVersionResponse = components["schemas"]["StrategyVersionResponse"];
type StrategyVersionDetailResponse = components["schemas"]["StrategyVersionDetailResponse"];
type StrategySpecValidationResponse = components["schemas"]["StrategySpecValidationResponse"];
type StrategyVersionDiffResponse = components["schemas"]["StrategyVersionDiffResponse"];
type SpecChangeResponse = components["schemas"]["SpecChangeResponse"];
type NodeDescriptorResponse = components["schemas"]["NodeDescriptorResponse"];

const LIFECYCLE_STATE_LUT: Record<string, StrategyLifecycleState> = {
	draft: "draft",
	review: "review",
	approved: "approved",
	published: "published",
	deprecated: "deprecated",
};

const REVIEW_OUTCOME_LUT: Record<string, StrategyReviewOutcome> = {
	pending: "pending",
	approved: "approved",
	rejected: "rejected",
};

function toLifecycleState(value: string): StrategyLifecycleState {
	return LIFECYCLE_STATE_LUT[value] ?? "unknown";
}

function toReviewOutcome(value: string): StrategyReviewOutcome {
	return REVIEW_OUTCOME_LUT[value] ?? "unknown";
}

function isRecord(value: unknown): value is Record<string, unknown> {
	return typeof value === "object" && value !== null;
}

function asString(value: unknown): string {
	return typeof value === "string" ? value : "";
}

function asParams(value: unknown): Readonly<Record<string, unknown>> {
	return isRecord(value) ? { ...value } : {};
}

function asStringArray(value: unknown): readonly string[] {
	return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function asNumberArray(value: unknown): readonly number[] {
	return Array.isArray(value) ? value.filter((item): item is number => typeof item === "number") : [];
}

const PARAM_DTYPES: readonly ParamDtype[] = ["bool", "int", "float", "str"];

function isParamDtype(value: unknown): value is ParamDtype {
	return typeof value === "string" && (PARAM_DTYPES as readonly string[]).includes(value);
}

function asOptionalNumber(value: unknown): number | undefined {
	return typeof value === "number" ? value : undefined;
}

/**
 * 从 legacy `param_constraints` 条目解析结构化约束。
 *
 * 容错策略：非 record 或缺有效 `dtype` 的条目直接丢弃（dtype 是渲染判别式，缺失无法
 * 意义化展示）；`name` 缺失回退空串；`min/max/step` 非数值则忽略；`allowed_values`
 * 非字符串数组则回退空数组。
 */
function parseParamConstraints(value: unknown): readonly ParamConstraintSpec[] {
	if (!Array.isArray(value)) return [];
	return value.flatMap((item: unknown): ParamConstraintSpec[] => {
		if (!isRecord(item) || !isParamDtype(item.dtype)) return [];
		const constraint: { name: string; dtype: ParamDtype; allowedValues: readonly string[] } & {
			minValue?: number;
			maxValue?: number;
			step?: number;
		} = { name: asString(item.name), dtype: item.dtype, allowedValues: asStringArray(item.allowed_values) };
		const minValue = asOptionalNumber(item.min_value);
		const maxValue = asOptionalNumber(item.max_value);
		const step = asOptionalNumber(item.step);
		if (minValue !== undefined) constraint.minValue = minValue;
		if (maxValue !== undefined) constraint.maxValue = maxValue;
		if (step !== undefined) constraint.step = step;
		return [constraint];
	});
}

function parseScorer(value: unknown): ScorerSpec {
	if (!isRecord(value)) return { method: "", params: {} };
	return { method: asString(value.method), params: asParams(value.params) };
}

function parseSelector(value: unknown): SelectorSpec {
	if (!isRecord(value)) return { method: "", params: {} };
	return { method: asString(value.method), params: asParams(value.params) };
}

function parseCostModel(value: unknown): CostModelSpec | undefined {
	if (!isRecord(value)) return undefined;
	const model: { commissionRate?: number; slippageBps?: number; stampDuty?: number; impactModel?: string } = {};
	if (typeof value.commission_rate === "number") model.commissionRate = value.commission_rate;
	if (typeof value.slippage_bps === "number") model.slippageBps = value.slippage_bps;
	if (typeof value.stamp_duty === "number") model.stampDuty = value.stamp_duty;
	if (typeof value.impact_model === "string") model.impactModel = value.impact_model;
	return Object.keys(model).length > 0 ? model : undefined;
}

function parseExecution(value: unknown): ExecutionSpec {
	if (!isRecord(value)) return { frequency: "", method: "", defaultOrderType: "market" };
	return {
		frequency: asString(value.frequency),
		method: asString(value.method),
		defaultOrderType: asString(value.default_order_type) || "market",
		costModel: parseCostModel(value.cost_model),
	};
}

function parseConstraints(value: unknown): readonly ConstraintSpec[] {
	if (!Array.isArray(value)) return [];
	return value.flatMap((item: unknown): ConstraintSpec[] => {
		if (!isRecord(item)) return [];
		return [{ type: asString(item.type), params: asParams(item.params) }];
	});
}

/** 从 legacy spec_json（`Record<string, unknown>`）容错解析结构化 spec。 */
export function parseSpecJson(
	specJson: unknown,
	fallback: { readonly strategyId: string; readonly name: string },
): StrategySpec {
	const spec = isRecord(specJson) ? specJson : {};
	return {
		strategyId: asString(spec.strategy_id) || fallback.strategyId,
		name: asString(spec.name) || fallback.name,
		template: asString(spec.template),
		universe: asString(spec.universe),
		assetClass: asString(spec.asset_class),
		benchmark: asString(spec.benchmark),
		scorer: parseScorer(spec.scorer),
		selector: parseSelector(spec.selector),
		execution: parseExecution(spec.execution),
		constraints: parseConstraints(spec.constraints),
		params: asParams(spec.params),
		signalExpressions: asStringArray(spec.signal_expressions),
		signalWeights: asNumberArray(spec.signal_weights),
		paramConstraints: parseParamConstraints(spec.param_constraints),
	};
}

export function mapStrategyListItem(dto: StrategyResponse): StrategyListItem {
	return {
		strategyId: dto.strategy_id,
		name: dto.name,
		version: dto.version,
		status: dto.status,
		lifecycleState: toLifecycleState(dto.status),
		createdAt: dto.created_at,
		tags: dto.tags,
	};
}

export function mapStrategyDetail(dto: StrategyResponse): StrategyDetail {
	return {
		...mapStrategyListItem(dto),
		spec: parseSpecJson(dto.spec_json, { strategyId: dto.strategy_id, name: dto.name }),
	};
}

export function mapStrategyVersion(dto: StrategyVersionResponse): StrategyVersion {
	return {
		strategyId: dto.strategy_id,
		version: dto.version,
		parentVersion: dto.parent_version,
		specHash: dto.spec_hash,
		state: dto.state,
		lifecycleState: toLifecycleState(dto.state),
		reviewOutcome: toReviewOutcome(dto.review_outcome),
		createdAt: dto.created_at,
	};
}

export function mapStrategyVersionDetail(dto: StrategyVersionDetailResponse): StrategyVersionDetail {
	return {
		strategyId: dto.strategy_id,
		version: dto.version,
		parentVersion: dto.parent_version,
		specHash: dto.spec_hash,
		state: dto.state,
		lifecycleState: toLifecycleState(dto.state),
		reviewOutcome: toReviewOutcome(dto.review_outcome),
		createdAt: dto.created_at,
		canonicalSpec: { ...dto.canonical_spec },
	};
}

export function mapSpecValidation(dto: StrategySpecValidationResponse): SpecValidation {
	return {
		strategyId: dto.strategy_id,
		version: dto.version,
		canonicalHash: dto.canonical_hash,
		baseSpecHash: dto.base_spec_hash,
		changed: dto.changed,
		valid: dto.valid,
		errors: dto.errors ?? [],
	};
}

function mapSpecChange(dto: SpecChangeResponse): SpecChange {
	return { path: dto.path, op: dto.op, old: dto.old ?? null, new: dto.new ?? null };
}

export function mapSpecDiff(dto: StrategyVersionDiffResponse): SpecDiff {
	return {
		strategyId: dto.strategy_id,
		version: dto.version,
		parentVersion: dto.parent_version,
		baseSpecHash: dto.base_spec_hash,
		targetSpecHash: dto.target_spec_hash,
		changed: dto.changed,
		changes: (dto.changes ?? []).map(mapSpecChange),
	};
}

export function mapNodeDescriptor(dto: NodeDescriptorResponse): NodeDescriptorView {
	return {
		nodeType: dto.node_type,
		version: dto.version,
		category: dto.category,
		displayName: dto.display_name,
		implementationKey: dto.implementation_key,
		configSchema: { ...dto.config_schema },
		defaultConfig: { ...dto.default_config },
		requiredDatasets: dto.required_datasets,
		capabilityTags: dto.capability_tags,
		deterministic: dto.deterministic,
	};
}

/** 将单个参数约束 view-model 序列化回 legacy snake_case 形态（与 parse 互逆）。 */
function serializeParamConstraint(constraint: ParamConstraintSpec): Record<string, unknown> {
	const out: { name: string; dtype: ParamDtype; allowed_values: readonly string[] } & {
		min_value?: number;
		max_value?: number;
		step?: number;
	} = { name: constraint.name, dtype: constraint.dtype, allowed_values: constraint.allowedValues };
	if (constraint.minValue !== undefined) out.min_value = constraint.minValue;
	if (constraint.maxValue !== undefined) out.max_value = constraint.maxValue;
	if (constraint.step !== undefined) out.step = constraint.step;
	return out;
}

/**
 * 将 view-model spec 序列化回 legacy spec_json（snake_case）。
 *
 * 与 {@link parseSpecJson} 互逆，保证表单/流水线编辑后保存的 spec_json 形态与
 * 后端存储一致；`scorer`/`selector`/`constraints`/`params` 的字段名（method/params/type）
 * 本就是 spec 子结构的通用键，无需 case 转换。`signal_*` 原生 snake，`param_constraints`
 * 子键（min_value/max_value/allowed_values）需 camel→snake 还原。
 */
export function serializeStrategySpec(spec: StrategySpec): Record<string, unknown> {
	return {
		strategy_id: spec.strategyId,
		name: spec.name,
		template: spec.template,
		universe: spec.universe,
		asset_class: spec.assetClass,
		benchmark: spec.benchmark,
		scorer: spec.scorer,
		selector: spec.selector,
		execution: {
			frequency: spec.execution.frequency,
			method: spec.execution.method,
			default_order_type: spec.execution.defaultOrderType,
			cost_model: spec.execution.costModel && {
				commission_rate: spec.execution.costModel.commissionRate,
				slippage_bps: spec.execution.costModel.slippageBps,
				stamp_duty: spec.execution.costModel.stampDuty,
				impact_model: spec.execution.costModel.impactModel,
			},
		},
		constraints: spec.constraints,
		params: spec.params,
		signal_expressions: spec.signalExpressions,
		signal_weights: spec.signalWeights,
		param_constraints: spec.paramConstraints.map(serializeParamConstraint),
	};
}
