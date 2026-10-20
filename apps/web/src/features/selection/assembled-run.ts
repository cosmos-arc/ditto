import type { AssembledSelectionRunResponse, AssembleSelectionRunBody } from "./api";

const UNIVERSE_SNAPSHOT_PATTERN = /^universe:sha256:[a-f0-9]{64}$/;

function sameFactorWeights(
	left: readonly { name: string; weight: number }[],
	right: readonly { name: string; weight: number }[],
): boolean {
	// 权重数组是有序的规范载荷：重排会得到不同的 spec/input 哈希，必须按位比较。
	return (
		left.length === right.length &&
		left.every((item, index) => item.name === right[index]?.name && item.weight === right[index]?.weight)
	);
}

function sameLimitStates(left: readonly string[], right: readonly string[]): boolean {
	return [...left].sort().join("\n") === [...right].sort().join("\n");
}

/** 返回区间必须可解析、有序、不晚于决策时点。 */
function windowWellFormed(
	dataFrom: string | null | undefined,
	dataTo: string | null | undefined,
	anchorMs: number,
): boolean {
	if (dataFrom == null || dataTo == null) return false;
	const from = Date.parse(dataFrom);
	const to = Date.parse(dataTo);
	return Number.isFinite(from) && Number.isFinite(to) && Number.isFinite(anchorMs) && from <= to && to <= anchorMs;
}

/** 已声明的截止时刻必须可解析且不晚于声明边界（服务端只会更早）。 */
function declaredInstantBound(
	returned: string | null | undefined,
	declared: string | null | undefined,
): boolean {
	if (returned == null) return false;
	const parsed = Date.parse(returned);
	if (!Number.isFinite(parsed)) return false;
	if (declared == null) return true;
	return parsed <= Date.parse(declared);
}

export function toAssembledRunView(value: AssembledSelectionRunResponse, submitted: AssembleSelectionRunBody) {
	const request = value.request;
	const spec = request?.selection_spec;
	// as_of 留空时由服务端滚动到最近完整交易日（#583）：以回显的决策时点为锚。
	const asOfEchoOk =
		submitted.as_of != null ? request.as_of === submitted.as_of : Number.isFinite(Date.parse(request.as_of));
	const anchorMs = Date.parse(submitted.as_of ?? request.as_of);
	const valid =
		typeof request === "object" &&
		request !== null &&
		asOfEchoOk &&
		request.seed === submitted.seed &&
		windowWellFormed(request.data_from, request.data_to, anchorMs) &&
		declaredInstantBound(request.knowledge_cutoff, submitted.knowledge_cutoff) &&
		declaredInstantBound(request.publication_cutoff, submitted.publication_cutoff) &&
		(request.publication_cutoff != null &&
			request.knowledge_cutoff != null &&
			Date.parse(request.publication_cutoff) <= Date.parse(request.knowledge_cutoff)) &&
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
		) &&
		new Set(request.instruments.map((item) => item.instrument_id)).size === request.instruments.length;
	if (!valid) throw new Error("组装响应的策略回显或服务端事实与提交不一致（含回看窗口边界）");
	return { request };
}
export type AssembledRunView = ReturnType<typeof toAssembledRunView>;
