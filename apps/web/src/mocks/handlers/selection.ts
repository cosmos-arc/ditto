import { HttpResponse, http } from "msw";
import type { AssembledSelectionRunResponse, AssembleSelectionRunBody } from "@/features/selection/api";
import {
	researchCaseFixture,
	selectionDiffFixture,
	selectionReceiptFixture,
	selectionRotationFixture,
	selectionRunFixtures,
} from "../fixtures/selection";

/**
 * 组装端点接受的已注册行情因子——快照自权威注册表（ALL_FACTOR_SPECS 按
 * 行情叶依赖闭包 + 纯时序表达式过滤，2026-10-02 经真实编译器枚举）。
 * 注册表演进时需同步刷新此快照。
 */
const ASSEMBLY_KNOWN_FACTORS = new Set([
	"amihud_illiquidity",
	"atr_14",
	"atr_20",
	"bollinger_lower",
	"bollinger_middle",
	"bollinger_upper",
	"cci_20",
	"choppiness_index",
	"cmra",
	"elder_ray_bull",
	"ema_10",
	"ema_13",
	"ema_14",
	"ema_20",
	"ema_5",
	"ema_60",
	"intraday_vol",
	"ma_10",
	"ma_14",
	"ma_20",
	"ma_5",
	"ma_60",
	"macd",
	"macd_hist",
	"macd_signal",
	"mfi_14",
	"momentum_12m",
	"momentum_1m",
	"momentum_3m",
	"momentum_accel",
	"overnight_vol",
	"prev_close",
	"raw_mf",
	"returns_1",
	"returns_10",
	"returns_20",
	"returns_5",
	"returns_60",
	"reversal_1m",
	"reversal_1w",
	"reversal_3d",
	"rsi_14",
	"rsi_6",
	"sequential_momentum",
	"tp",
	"tr",
	"umd_6m",
	"vol_ratio",
	"volatility_10",
	"volatility_120",
	"volatility_14",
	"volatility_20",
	"volatility_5",
	"volatility_60",
	"volatility_factor",
	"volume_ma_10",
	"volume_ma_14",
	"volume_ma_20",
	"volume_ma_5",
	"volume_ma_60",
	"volume_price_corr",
	"vwap_20d",
	"williams_r",
]);

/** 组装 v1 唯一接受的股票全市场池（镜像服务端 ASSEMBLY_UNIVERSE_SCOPE_UNSUPPORTED 语义）。 */
export const ASSEMBLY_STOCK_UNIVERSE_ID = "a-share-custom-202609";

export const ASSEMBLED_UNIVERSE_SNAPSHOT_ID = `universe:sha256:${"6".repeat(64)}`;

/** Deterministic assembled facts echoing the submitted policy; mirrors the server's assemble endpoint. */
export function assembledSelectionRunResponse(body: AssembleSelectionRunBody): AssembledSelectionRunResponse {
	return {
		admission: {
			allowed: true,
			fields: [
				{
					allowed_uses: ["formal_research"],
					certification_report_id: "certification-mock",
					consumer_field: "instruments.average_turnover",
					covered_from: "2015-01-05",
					covered_to: body.as_of.slice(0, 10),
					dataset_id: "stock_daily",
					evidence_uri: "mock://evidence/amount",
					field: "amount",
					license_record_id: "license-mock",
					reason_codes: [],
					snapshot_id: "stock-daily:sha256:mock",
					time_precision: "day",
				},
			],
			purpose: "formal_research",
			rule_version: "field-admission-v2",
		},
		request: {
			as_of: body.as_of,
			data_fields: [
				{
					consumer_field: "universe_snapshot_id",
					dataset_id: "stock_basic",
					field: "list_status",
					snapshot_id: "stock-basic:sha256:mock",
				},
				{
					consumer_field: "membership_version",
					dataset_id: "stock_daily",
					field: "close",
					snapshot_id: "stock-daily:sha256:mock",
				},
				...["instruments.instrument_name", "instruments.is_st", "instruments.listing_days"].map((consumer_field) => ({
					consumer_field,
					dataset_id: "stock_basic",
					field: "name",
					snapshot_id: "stock-basic:sha256:mock",
				})),
				{
					consumer_field: "instruments.is_suspended",
					dataset_id: "stock_status",
					field: "is_suspended",
					snapshot_id: "stock-status:sha256:mock",
				},
				...body.factor_weights.flatMap((factor) =>
					["close", "instrument_id", "knowledge_date", "trade_date", "source_ticker"].map((field) => ({
						consumer_field: `instruments.factor_values.${factor.name}`,
						dataset_id: "stock_daily",
						field,
						snapshot_id: "stock-daily:sha256:mock",
					})),
				),
				{
					consumer_field: "instruments.average_turnover",
					dataset_id: "stock_daily",
					field: "amount",
					snapshot_id: "stock-daily:sha256:mock",
				},
				{
					consumer_field: "instruments.limit_state",
					dataset_id: "stock_daily",
					field: "close",
					snapshot_id: "stock-daily:sha256:mock",
				},
			],
			data_from: "2015-01-05",
			data_to: body.as_of.slice(0, 10),
			industries: [],
			instruments: [600519, 300750].map((instrument_id, index) => ({
				declared_missing_inputs: [],
				factor_values: body.factor_weights.map((factor) => ({
					name: factor.name,
					// 确定性单位分：两只标的在因子方向上对称（0.75/0.25 交替）。
					value: index === 0 ? 0.75 : 0.25,
				})),
				instrument_id,
				instrument_name: instrument_id === 600519 ? "贵州茅台" : "宁德时代",
				industry_id: null,
				average_turnover: index === 0 ? 3.1e7 : 2.4e7,
				is_st: false,
				is_suspended: false,
				listing_days: 9000,
				limit_state: "normal",
				tracking_error: null,
			})),
			knowledge_cutoff: body.knowledge_cutoff ?? body.as_of,
			market_context_feature_set_id: null,
			membership_version: "sw-l1:mock",
			publication_cutoff: body.publication_cutoff ?? body.as_of,
			rotation_algorithm_version: "industry-rotation-v1",
			rotation_missing_inputs: [],
			rotation_source_snapshot_ids: ["stock-daily:sha256:mock"],
			seed: body.seed,
			selection_source_snapshot_ids: ["stock-daily:sha256:mock", "stock-basic:sha256:mock", "stock-status:sha256:mock"],
			selection_spec: {
				asset_kind: "stock",
				excluded_limit_states: body.excluded_limit_states,
				factor_weights: body.factor_weights,
				min_average_turnover: body.min_average_turnover,
				min_listing_days: body.min_listing_days,
				spec_id: body.spec_id,
				spec_version: body.spec_version,
				top_k: body.top_k,
			},
			universe_snapshot_id: ASSEMBLED_UNIVERSE_SNAPSHOT_ID,
			universe_sources: {
				universe_id: body.universe_id,
				asset_kind: "stock",
				master_snapshot_ids: ["stock-basic:sha256:mock"],
				status_snapshot_ids: ["stock-status:sha256:mock"],
				membership_snapshot_ids: null,
				index_id: null,
			},
		},
	};
}

export const selectionHandlers = [
	http.post("/api/v1/selections/admission", () =>
		HttpResponse.json({
			data: {
				allowed: false,
				purpose: "formal_research",
				rule_version: "field-admission-v2",
				fields: [
					{
						dataset_id: "stock_daily",
						field: "amount",
						snapshot_id: "synthetic-snapshot",
						consumer_field: "instruments.average_turnover",
						allowed_uses: [],
						reason_codes: ["FIELD_EVIDENCE_MISSING"],
						license_record_id: null,
						certification_report_id: null,
						covered_from: null,
						covered_to: null,
						time_precision: "unknown",
						evidence_uri: null,
					},
				],
			},
		}),
	),
	http.get("/api/v1/selections/runs", ({ request }) => {
		const specId = new URL(request.url).searchParams.get("spec_id");
		return HttpResponse.json({ data: selectionRunFixtures.filter((run) => run.spec_id === specId) });
	}),
	http.get("/api/v1/selections/runs/:before/compare/:after", () => HttpResponse.json({ data: selectionDiffFixture })),
	http.get("/api/v1/selections/runs/:runId", ({ params }) => {
		const run = selectionRunFixtures.find((item) => item.run_id === params["runId"]);
		return run ? HttpResponse.json({ data: run }) : HttpResponse.json({ detail: "not found" }, { status: 404 });
	}),
	http.get("/api/v1/selections/industry-rotations/:snapshotId", ({ params }) =>
		params["snapshotId"] === selectionRotationFixture.snapshot_id
			? HttpResponse.json({ data: selectionRotationFixture })
			: HttpResponse.json({ detail: "not found" }, { status: 404 }),
	),
	http.post("/api/v1/selections/runs", () => HttpResponse.json({ data: selectionReceiptFixture }, { status: 201 })),
	http.post("/api/v1/selections/runs:assembled", async ({ request }) => {
		const body = (await request.json()) as AssembleSelectionRunBody;
		const names = body.factor_weights.map((factor) => factor.name);
		const weightSum = body.factor_weights.reduce((sum, factor) => sum + factor.weight, 0);
		if (new Set(names).size !== names.length || Math.abs(weightSum - 1) > 1e-9)
			return HttpResponse.json({ detail: "因子权重不得重复且权重之和必须为 1" }, { status: 422 });
		if (body.factor_weights.some((factor) => !ASSEMBLY_KNOWN_FACTORS.has(factor.name)))
			return HttpResponse.json({ detail: "未注册因子或该因子表达式暂不被组装支持" }, { status: 422 });
		if (body.universe_id !== ASSEMBLY_STOCK_UNIVERSE_ID)
			return HttpResponse.json(
				{ detail: "组装 v1 仅支持全市场股票池；窄池/非股票池需 membership 快照链" },
				{ status: 422 },
			);
		return HttpResponse.json({ data: assembledSelectionRunResponse(body) });
	}),
	http.post("/api/v1/selections/runs/:runId/research-cases", async ({ params, request }) => {
		const run = selectionRunFixtures.find((item) => item.run_id === params["runId"]);
		if (!run) return HttpResponse.json({ detail: "not found" }, { status: 404 });
		const body = (await request.json()) as { objective: string; candidate_instrument_ids: number[] };
		const payload = {
			as_of: run.as_of,
			asset_kind: run.asset_kind,
			candidate_instrument_ids: body.candidate_instrument_ids,
			industry_rotation_snapshot_id: run.industry_rotation_snapshot_id,
			knowledge_cutoff: run.knowledge_cutoff,
			missing_inputs: run.missing_inputs,
			objective: body.objective,
			publication_cutoff: run.publication_cutoff,
			selection_input_hash: run.input_hash,
			selection_run_hash: run.run_id.split(":sha256:")[1] ?? "",
			selection_run_id: run.run_id,
			selection_spec_hash: run.spec_hash,
			selection_status: run.status,
			source_snapshot_ids: run.source_snapshot_ids,
			universe_snapshot_id: run.universe_snapshot_id,
		};
		return HttpResponse.json(
			{
				data: {
					...researchCaseFixture,
					...payload,
					case_id: `research-case:sha256:${mockCaseHash(payload)}`,
					content_hash: mockCaseHash(payload),
					schema_version: 1,
				},
			},
			{ status: 201 },
		);
	}),
];

function mockCaseHash(payload: unknown): string {
	const text = JSON.stringify(payload);
	let first = 0x811c9dc5;
	let second = 0x01000193;
	for (let index = 0; index < text.length; index++) {
		first = Math.imul(first ^ text.charCodeAt(index), 0x01000193) >>> 0;
		second = Math.imul(second + text.charCodeAt(index) * (index + 1), 0x85ebca6b) >>> 0;
	}
	return (first.toString(16).padStart(8, "0") + second.toString(16).padStart(8, "0")).repeat(4);
}
