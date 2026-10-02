import type { AssembledSelectionRunResponse, AssembleSelectionRunBody } from "./api";

const UNIVERSE_SNAPSHOT_PATTERN = /^universe:sha256:[a-f0-9]{64}$/;

function sameFactorWeights(
	left: readonly { name: string; weight: number }[],
	right: readonly { name: string; weight: number }[],
): boolean {
	return (
		left.length === right.length &&
		[...left]
			.map((item) => `${item.name}:${item.weight}`)
			.sort()
			.join("\n") ===
			[...right]
				.map((item) => `${item.name}:${item.weight}`)
				.sort()
				.join("\n")
	);
}

function sameLimitStates(left: readonly string[], right: readonly string[]): boolean {
	return [...left].sort().join("\n") === [...right].sort().join("\n");
}

export function toAssembledRunView(value: AssembledSelectionRunResponse, submitted: AssembleSelectionRunBody) {
	const request = value.request;
	const spec = request?.selection_spec;
	const valid =
		typeof value.admission === "object" &&
		value.admission !== null &&
		typeof value.admission.allowed === "boolean" &&
		typeof request === "object" &&
		request !== null &&
		request.as_of === submitted.as_of &&
		request.seed === submitted.seed &&
		typeof spec === "object" &&
		spec !== null &&
		spec.asset_kind === "stock" &&
		spec.spec_id === submitted.spec_id &&
		spec.spec_version === submitted.spec_version &&
		spec.top_k === submitted.top_k &&
		spec.min_average_turnover === submitted.min_average_turnover &&
		spec.min_listing_days === submitted.min_listing_days &&
		sameFactorWeights(spec.factor_weights, submitted.factor_weights) &&
		sameLimitStates(spec.excluded_limit_states, submitted.excluded_limit_states) &&
		UNIVERSE_SNAPSHOT_PATTERN.test(request.universe_snapshot_id) &&
		request.universe_sources != null &&
		request.universe_sources.universe_id === submitted.universe_id &&
		request.universe_sources.asset_kind === "stock" &&
		Array.isArray(request.instruments) &&
		request.instruments.length > 0 &&
		request.instruments.every(
			(item) =>
				Number.isSafeInteger(item.instrument_id) &&
				item.instrument_id > 0 &&
				typeof item.instrument_name === "string" &&
				item.instrument_name.length > 0,
		);
	if (!valid) throw new Error("组装响应的策略回显或服务端事实与提交不一致");
	return { request, admission: value.admission };
}
export type AssembledRunView = ReturnType<typeof toAssembledRunView>;
