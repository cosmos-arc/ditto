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
} from "@/types/strategy";

type StrategyResponse = components["schemas"]["StrategyResponse"];
type StrategyVersionResponse = components["schemas"]["StrategyVersionResponse"];
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
	const model: { commissionRate?: number; slippageBps?: number; stampDuty?: number } = {};
	if (typeof value.commission_rate === "number") model.commissionRate = value.commission_rate;
	if (typeof value.slippage_bps === "number") model.slippageBps = value.slippage_bps;
	if (typeof value.stamp_duty === "number") model.stampDuty = value.stamp_duty;
	return Object.keys(model).length > 0 ? model : undefined;
}

function parseExecution(value: unknown): ExecutionSpec {
	if (!isRecord(value)) return { frequency: "", method: "" };
	return {
		frequency: asString(value.frequency),
		method: asString(value.method),
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

/**
 * 将 view-model spec 序列化回 legacy spec_json（snake_case）。
 *
 * 与 {@link parseSpecJson} 互逆，保证表单/流水线编辑后保存的 spec_json 形态与
 * 后端存储一致；`scorer`/`selector`/`constraints`/`params` 的字段名（method/params/type）
 * 本就是 spec 子结构的通用键，无需 case 转换。
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
			cost_model: spec.execution.costModel && {
				commission_rate: spec.execution.costModel.commissionRate,
				slippage_bps: spec.execution.costModel.slippageBps,
				stamp_duty: spec.execution.costModel.stampDuty,
			},
		},
		constraints: spec.constraints,
		params: spec.params,
	};
}
