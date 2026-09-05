import type {
	FillLedgerAdjustment,
	FillLedgerConsistencyIssue,
	FillLedgerEntry,
	FillLedgerIdentityField,
	FillLedgerIssue,
	FillLedgerState,
	GetFillLedgerResponse,
	OrderSide,
} from "@/types";
import {
	type FetchFillsParams,
	type FillAdjustmentResponse,
	type FillResponse,
	fetchEffectiveFills,
	fetchFillAdjustments,
	fetchFills,
} from "./fills";

function mapDirection(direction: string): OrderSide {
	return direction.toLowerCase() === "sell" ? "SELL" : "BUY";
}

function mapAdjustment(adjustment: FillAdjustmentResponse): FillLedgerAdjustment {
	return {
		id: adjustment.adjustment_id,
		type: adjustment.adjustment_type,
		reason: adjustment.reason,
		createdAt: adjustment.created_at,
		replacementFillId: adjustment.replacement_fill_id ?? null,
	};
}

type FillLedgerResolution = {
	readonly state: FillLedgerState;
	readonly consistencyIssue?: FillLedgerConsistencyIssue | undefined;
};

function mapFillToLedgerEntry(
	fill: FillResponse,
	resolution: FillLedgerResolution,
	adjustment: FillAdjustmentResponse | undefined,
): FillLedgerEntry {
	return {
		id: fill.fill_id,
		intentId: fill.intent_id,
		tradeDate: fill.trade_date,
		instrument: `#${fill.instrument_id}`,
		direction: mapDirection(fill.direction),
		quantity: fill.quantity,
		fillPrice: fill.fill_price,
		fee: fill.fee,
		slippage: fill.slippage,
		notes: fill.notes,
		state: resolution.state,
		...(resolution.consistencyIssue === undefined ? {} : { consistencyIssue: resolution.consistencyIssue }),
		adjustment: adjustment ? mapAdjustment(adjustment) : null,
	};
}

function findIdentityMismatches(source: FillResponse, replacement: FillResponse): readonly FillLedgerIdentityField[] {
	const fields: FillLedgerIdentityField[] = [];
	if (source.intent_id !== replacement.intent_id) fields.push("intent_id");
	if (source.strategy_id !== replacement.strategy_id) fields.push("strategy_id");
	if (source.instrument_id !== replacement.instrument_id) fields.push("instrument_id");
	if (source.direction.toLowerCase() !== replacement.direction.toLowerCase()) fields.push("direction");
	return fields;
}

function createIssue(
	code: FillLedgerConsistencyIssue,
	fillId: string,
	options: {
		readonly relatedFillId?: string | null | undefined;
		readonly adjustmentId?: string | null | undefined;
		readonly mismatchedFields?: readonly FillLedgerIdentityField[];
	} = {},
): FillLedgerIssue {
	return {
		code,
		fillId,
		relatedFillId: options.relatedFillId ?? null,
		adjustmentId: options.adjustmentId ?? null,
		mismatchedFields: options.mismatchedFields ?? [],
	};
}

function addGraphEdge(graph: Map<string, Set<string>>, source: string, target: string) {
	const sourceEdges = graph.get(source) ?? new Set<string>();
	sourceEdges.add(target);
	graph.set(source, sourceEdges);
	const targetEdges = graph.get(target) ?? new Set<string>();
	targetEdges.add(source);
	graph.set(target, targetEdges);
}

function collectConnectedFillIds(
	graph: ReadonlyMap<string, ReadonlySet<string>>,
	seeds: readonly (string | null)[],
): ReadonlySet<string> {
	const visited = new Set<string>();
	const pending = seeds.filter((seed): seed is string => seed !== null);
	while (pending.length > 0) {
		const fillId = pending.pop();
		if (!fillId || visited.has(fillId)) continue;
		visited.add(fillId);
		for (const relatedFillId of graph.get(fillId) ?? []) {
			if (!visited.has(relatedFillId)) pending.push(relatedFillId);
		}
	}
	return visited;
}

function findReplacementCycles(
	adjustments: readonly FillAdjustmentResponse[],
	adjustmentsByFill: ReadonlyMap<string, FillAdjustmentResponse>,
): readonly (readonly string[])[] {
	const completed = new Set<string>();
	const cycles: string[][] = [];
	for (const seed of adjustments.map((adjustment) => adjustment.fill_id)) {
		if (completed.has(seed)) continue;
		const path: string[] = [];
		const pathIndex = new Map<string, number>();
		let current: string | undefined = seed;
		while (current && !completed.has(current)) {
			const cycleStart = pathIndex.get(current);
			if (cycleStart !== undefined) {
				cycles.push(path.slice(cycleStart));
				break;
			}
			pathIndex.set(current, path.length);
			path.push(current);
			const adjustment = adjustmentsByFill.get(current);
			current =
				adjustment?.adjustment_type === "replace" && adjustment.replacement_fill_id
					? adjustment.replacement_fill_id
					: undefined;
		}
		for (const fillId of path) completed.add(fillId);
	}
	return cycles;
}

function buildLedger(
	rawFills: readonly FillResponse[],
	effectiveFills: readonly FillResponse[],
	adjustments: readonly FillAdjustmentResponse[],
	checkOrphanAdjustments: boolean,
): GetFillLedgerResponse {
	const rawById = new Map(rawFills.map((fill) => [fill.fill_id, fill]));
	const effectiveById = new Map(effectiveFills.map((fill) => [fill.fill_id, fill]));
	const relevantAdjustments = checkOrphanAdjustments
		? adjustments
		: adjustments.filter((adjustment) => rawById.has(adjustment.fill_id));
	const adjustmentsByFill = new Map(relevantAdjustments.map((adjustment) => [adjustment.fill_id, adjustment]));
	const replacementTargets = new Set(
		relevantAdjustments.flatMap((adjustment) =>
			adjustment.adjustment_type === "replace" && adjustment.replacement_fill_id
				? [adjustment.replacement_fill_id]
				: [],
		),
	);
	const correctionGraph = new Map<string, Set<string>>();
	for (const adjustment of relevantAdjustments) {
		if (adjustment.adjustment_type === "replace" && adjustment.replacement_fill_id) {
			addGraphEdge(correctionGraph, adjustment.fill_id, adjustment.replacement_fill_id);
		}
	}

	const issues: FillLedgerIssue[] = [];
	for (const fill of rawFills) {
		const adjustment = adjustmentsByFill.get(fill.fill_id);
		const isEffective = effectiveById.has(fill.fill_id);
		if (isEffective && adjustment) {
			issues.push(
				createIssue("effective_with_adjustment", fill.fill_id, {
					adjustmentId: adjustment.adjustment_id,
					relatedFillId: adjustment.replacement_fill_id,
				}),
			);
		}

		if (adjustment?.adjustment_type === "replace") {
			const replacementFillId = adjustment.replacement_fill_id ?? null;
			const replacement = replacementFillId ? rawById.get(replacementFillId) : undefined;
			if (!replacementFillId) {
				issues.push(
					createIssue("replacement_missing_raw", fill.fill_id, {
						adjustmentId: adjustment.adjustment_id,
					}),
				);
				continue;
			}
			if (!replacement) {
				if (checkOrphanAdjustments) {
					issues.push(
						createIssue("replacement_missing_raw", fill.fill_id, {
							adjustmentId: adjustment.adjustment_id,
							relatedFillId: replacementFillId,
						}),
					);
				}
				continue;
			}

			const mismatchedFields = findIdentityMismatches(fill, replacement);
			if (mismatchedFields.length > 0) {
				issues.push(
					createIssue("replacement_identity_mismatch", fill.fill_id, {
						adjustmentId: adjustment.adjustment_id,
						relatedFillId: replacementFillId,
						mismatchedFields,
					}),
				);
			}

			if (!effectiveById.has(replacementFillId) && !adjustmentsByFill.has(replacementFillId)) {
				issues.push(
					createIssue("replacement_not_resolved", fill.fill_id, {
						adjustmentId: adjustment.adjustment_id,
						relatedFillId: replacementFillId,
					}),
				);
			}
		}

		if (!isEffective && !adjustment && !replacementTargets.has(fill.fill_id)) {
			issues.push(createIssue("missing_effective_and_adjustment", fill.fill_id));
		}
	}

	for (const cycle of findReplacementCycles(relevantAdjustments, adjustmentsByFill)) {
		const fillId = cycle[0];
		if (!fillId) continue;
		issues.push(
			createIssue("replacement_cycle", fillId, {
				adjustmentId: adjustmentsByFill.get(fillId)?.adjustment_id,
				relatedFillId: cycle[1] ?? fillId,
			}),
		);
	}

	if (checkOrphanAdjustments) {
		for (const adjustment of relevantAdjustments) {
			if (rawById.has(adjustment.fill_id)) continue;
			issues.push(
				createIssue("orphan_adjustment", adjustment.fill_id, {
					adjustmentId: adjustment.adjustment_id,
					relatedFillId: adjustment.replacement_fill_id,
				}),
			);
		}
	}

	for (const effectiveFill of effectiveFills) {
		if (!rawById.has(effectiveFill.fill_id)) {
			issues.push(createIssue("ghost_effective", effectiveFill.fill_id));
		}
	}

	const issueByFill = new Map<string, FillLedgerConsistencyIssue>();
	for (const issue of issues) {
		const connectedFillIds = collectConnectedFillIds(correctionGraph, [issue.fillId, issue.relatedFillId]);
		for (const fillId of connectedFillIds) {
			if ((rawById.has(fillId) || effectiveById.has(fillId)) && !issueByFill.has(fillId)) {
				issueByFill.set(fillId, issue.code);
			}
		}
	}

	const fills = rawFills.map((fill) => {
		const consistencyIssue = issueByFill.get(fill.fill_id);
		const adjustment = adjustmentsByFill.get(fill.fill_id);
		let state: FillLedgerState;
		if (consistencyIssue) state = "unresolved";
		else if (effectiveById.has(fill.fill_id)) state = "effective";
		else state = adjustment?.adjustment_type === "replace" ? "replaced" : "voided";
		return mapFillToLedgerEntry(fill, { state, consistencyIssue }, adjustment);
	});

	for (const effectiveFill of effectiveFills) {
		if (!rawById.has(effectiveFill.fill_id)) {
			fills.push(
				mapFillToLedgerEntry(
					effectiveFill,
					{ state: "unresolved", consistencyIssue: "ghost_effective" },
					adjustmentsByFill.get(effectiveFill.fill_id),
				),
			);
		}
	}

	return { fills, issues };
}

export async function fetchFillLedger(params: FetchFillsParams = {}): Promise<GetFillLedgerResponse> {
	const [rawFills, effectiveFills, adjustments] = await Promise.all([
		fetchFills(params),
		fetchEffectiveFills(params),
		fetchFillAdjustments({ strategyId: params.strategyId }),
	]);
	return buildLedger(rawFills, effectiveFills, adjustments, !params.startDate && !params.endDate);
}
