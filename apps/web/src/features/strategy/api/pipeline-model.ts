import type { ConstraintSpec, NodeDescriptorView, StrategySpec } from "@/types/strategy";

export const FIXED_PIPELINE_NODE_TYPES = [
	"legacy.universe",
	"legacy.factor_set",
	"legacy.scorer",
	"legacy.selector",
	"legacy.allocator",
	"legacy.execution_assumption",
	"legacy.validation",
] as const;

const FIXED_CATEGORY_BY_NODE_TYPE: Record<(typeof FIXED_PIPELINE_NODE_TYPES)[number], string> = {
	"legacy.universe": "UNIVERSE",
	"legacy.factor_set": "FACTOR_SET",
	"legacy.scorer": "SCORER",
	"legacy.selector": "SELECTOR",
	"legacy.allocator": "ALLOCATOR",
	"legacy.execution_assumption": "EXECUTION_ASSUMPTION",
	"legacy.validation": "VALIDATION",
};

const FIXED_CATEGORY_ORDER = [
	"UNIVERSE",
	"FACTOR_SET",
	"FILTER",
	"SCORER",
	"SELECTOR",
	"ALLOCATOR",
	"EXECUTION_ASSUMPTION",
	"VALIDATION",
] as const;

export type StrategyPipelineNode = {
	readonly key: string;
	readonly category: string;
	readonly descriptor: NodeDescriptorView | null;
	readonly identity: string;
	readonly displayName: string;
	readonly config: Readonly<Record<string, unknown>>;
	readonly fixed: boolean;
	readonly readOnly: boolean;
	readonly constraintIndex: number | null;
	readonly allowedPredecessor: string | null;
	readonly allowedSuccessor: string | null;
};

export function descriptorIdentity(descriptor: NodeDescriptorView): string {
	return `${descriptor.nodeType}@${descriptor.version}`;
}

export function findNodeDescriptor(
	descriptors: readonly NodeDescriptorView[],
	identityOrType: string,
): NodeDescriptorView | null {
	return (
		descriptors.find(
			(descriptor) => descriptorIdentity(descriptor) === identityOrType || descriptor.nodeType === identityOrType,
		) ?? null
	);
}

function fixedConfig(
	nodeType: (typeof FIXED_PIPELINE_NODE_TYPES)[number],
	spec: StrategySpec,
): Record<string, unknown> {
	switch (nodeType) {
		case "legacy.universe":
			return { asset_class: spec.assetClass, benchmark: spec.benchmark || null, universe: spec.universe };
		case "legacy.factor_set":
			return {
				params: spec.params,
				required_datasets: [],
				signal_expressions: spec.signalExpressions,
				signal_weights: spec.signalWeights,
				template: spec.template,
			};
		case "legacy.scorer":
			return { method: spec.scorer.method, params: spec.scorer.params };
		case "legacy.selector":
			return { method: spec.selector.method, params: spec.selector.params };
		case "legacy.allocator":
			return { constraints: spec.constraints.filter((constraint) => !constraint.type.includes("@")) };
		case "legacy.execution_assumption":
			return {
				cost_model: {
					commission_rate: spec.execution.costModel?.commissionRate,
					impact_model: spec.execution.costModel?.impactModel,
					slippage_bps: spec.execution.costModel?.slippageBps,
					stamp_duty: spec.execution.costModel?.stampDuty,
				},
				default_order_type: spec.execution.defaultOrderType,
				frequency: spec.execution.frequency,
				method: spec.execution.method,
			};
		case "legacy.validation":
			return { legacy_contract: "strategy_spec_v1" };
	}
}

function categoryNeighbor(category: string, offset: -1 | 1): string | null {
	const index = FIXED_CATEGORY_ORDER.indexOf(category as (typeof FIXED_CATEGORY_ORDER)[number]);
	if (index < 0) return null;
	return FIXED_CATEGORY_ORDER[index + offset] ?? null;
}

function makeFixedNode(
	nodeType: (typeof FIXED_PIPELINE_NODE_TYPES)[number],
	spec: StrategySpec,
	descriptors: readonly NodeDescriptorView[],
): StrategyPipelineNode {
	const descriptor = findNodeDescriptor(descriptors, nodeType);
	const category = descriptor?.category ?? FIXED_CATEGORY_BY_NODE_TYPE[nodeType];
	return {
		key: `fixed:${nodeType}`,
		category,
		descriptor,
		identity: descriptor ? descriptorIdentity(descriptor) : `${nodeType}@unknown`,
		displayName: descriptor?.displayName ?? nodeType,
		config: fixedConfig(nodeType, spec),
		fixed: true,
		readOnly: descriptor === null,
		constraintIndex: null,
		allowedPredecessor: categoryNeighbor(category, -1),
		allowedSuccessor: categoryNeighbor(category, 1),
	};
}

function isPipelineFilter(constraint: ConstraintSpec, descriptors: readonly NodeDescriptorView[]): boolean {
	const descriptor = findNodeDescriptor(descriptors, constraint.type);
	return descriptor?.category === "FILTER" || constraint.type.includes("@");
}

/** 从 legacy working spec 构造受固定语法约束的有序视图，不计算 canonical hash。 */
export function buildStrategyPipeline(
	spec: StrategySpec,
	descriptors: readonly NodeDescriptorView[],
): readonly StrategyPipelineNode[] {
	const fixed = new Map(
		FIXED_PIPELINE_NODE_TYPES.map((nodeType) => {
			const node = makeFixedNode(nodeType, spec, descriptors);
			return [nodeType, node] as const;
		}),
	);
	const filters = spec.constraints.flatMap((constraint, index): StrategyPipelineNode[] => {
		if (!isPipelineFilter(constraint, descriptors)) return [];
		const descriptor = findNodeDescriptor(descriptors, constraint.type);
		return [
			{
				key: `filter:${index}`,
				category: descriptor?.category ?? "UNKNOWN",
				descriptor,
				identity: descriptor ? descriptorIdentity(descriptor) : constraint.type,
				displayName: descriptor?.displayName ?? constraint.type,
				config: constraint.params,
				fixed: false,
				readOnly: descriptor === null || descriptor.category !== "FILTER",
				constraintIndex: index,
				allowedPredecessor: "FACTOR_SET",
				allowedSuccessor: "SCORER",
			},
		];
	});
	return [
		fixed.get("legacy.universe"),
		fixed.get("legacy.factor_set"),
		...filters,
		fixed.get("legacy.scorer"),
		fixed.get("legacy.selector"),
		fixed.get("legacy.allocator"),
		fixed.get("legacy.execution_assumption"),
		fixed.get("legacy.validation"),
	].filter((node): node is StrategyPipelineNode => node !== undefined);
}

export function addDescriptorNode(spec: StrategySpec, descriptor: NodeDescriptorView): StrategySpec {
	if (descriptor.category !== "FILTER") return spec;
	return {
		...spec,
		constraints: [
			...spec.constraints,
			{ type: descriptorIdentity(descriptor), params: { ...descriptor.defaultConfig } },
		],
	};
}

export function removePipelineNode(spec: StrategySpec, node: StrategyPipelineNode): StrategySpec {
	if (node.fixed || node.readOnly || node.constraintIndex === null) return spec;
	return { ...spec, constraints: spec.constraints.filter((_, index) => index !== node.constraintIndex) };
}

export function movePipelineNode(
	spec: StrategySpec,
	node: StrategyPipelineNode,
	direction: -1 | 1,
	descriptors: readonly NodeDescriptorView[],
): StrategySpec {
	if (node.fixed || node.readOnly || node.constraintIndex === null) return spec;
	const filterIndexes = spec.constraints
		.map((constraint, index) => (isPipelineFilter(constraint, descriptors) ? index : null))
		.filter((index): index is number => index !== null);
	const currentPosition = filterIndexes.indexOf(node.constraintIndex);
	const targetIndex = filterIndexes[currentPosition + direction];
	if (targetIndex === undefined) return spec;
	const constraints = [...spec.constraints];
	const current = constraints[node.constraintIndex];
	const target = constraints[targetIndex];
	if (!current || !target) return spec;
	constraints[node.constraintIndex] = target;
	constraints[targetIndex] = current;
	return { ...spec, constraints };
}

export function updatePipelineNodeConfig(
	spec: StrategySpec,
	node: StrategyPipelineNode,
	key: string,
	value: unknown,
): StrategySpec {
	if (node.readOnly) return spec;
	if (node.constraintIndex !== null) {
		return {
			...spec,
			constraints: spec.constraints.map((constraint, index) =>
				index === node.constraintIndex ? { ...constraint, params: { ...constraint.params, [key]: value } } : constraint,
			),
		};
	}
	switch (node.descriptor?.nodeType) {
		case "legacy.universe":
			if (key === "universe") return { ...spec, universe: String(value) };
			if (key === "asset_class") return { ...spec, assetClass: String(value) };
			if (key === "benchmark") return { ...spec, benchmark: value === null ? "" : String(value) };
			return spec;
		case "legacy.factor_set":
			if (key === "template") return { ...spec, template: String(value) };
			if (key === "params" && typeof value === "object" && value !== null)
				return { ...spec, params: value as Readonly<Record<string, unknown>> };
			if (key === "signal_expressions" && Array.isArray(value))
				return { ...spec, signalExpressions: value.filter((item): item is string => typeof item === "string") };
			if (key === "signal_weights" && Array.isArray(value))
				return { ...spec, signalWeights: value.filter((item): item is number => typeof item === "number") };
			return spec;
		case "legacy.scorer":
			return key === "method"
				? { ...spec, scorer: { ...spec.scorer, method: String(value) } }
				: key === "params" && typeof value === "object" && value !== null
					? { ...spec, scorer: { ...spec.scorer, params: value as Readonly<Record<string, unknown>> } }
					: spec;
		case "legacy.selector":
			return key === "method"
				? { ...spec, selector: { ...spec.selector, method: String(value) } }
				: key === "params" && typeof value === "object" && value !== null
					? { ...spec, selector: { ...spec.selector, params: value as Readonly<Record<string, unknown>> } }
					: spec;
		case "legacy.execution_assumption":
			if (key === "frequency") return { ...spec, execution: { ...spec.execution, frequency: String(value) } };
			if (key === "method") return { ...spec, execution: { ...spec.execution, method: String(value) } };
			if (key === "default_order_type")
				return { ...spec, execution: { ...spec.execution, defaultOrderType: String(value) } };
			return spec;
		default:
			return spec;
	}
}
