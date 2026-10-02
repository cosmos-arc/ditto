import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { type AdmissionView, toAdmissionView } from "../admission";
import {
	type AssembleSelectionRunBody,
	assembleSelectionRun,
	assessSelectionAdmission,
	type CreateSelectionRunBody,
	listUniverseOptions,
	resolveSelectionUniverse,
} from "../api";
import { toAssembledRunView } from "../assembled-run";
import { SelectionAdmission } from "./selection-admission";

const STORAGE_KEY = "ditto.selection-run-input.v1";

// 镜像服务端 math.isclose(total, 1.0, abs_tol=1e-12)：默认 rel_tol=1e-9 主导有效容差。
const WEIGHT_SUM_TOLERANCE = 1e-9;

function parseRunInput(value: string): CreateSelectionRunBody {
	const parsed: unknown = JSON.parse(value);
	if (typeof parsed !== "object" || parsed === null || !("selection_spec" in parsed)) {
		throw new Error("输入必须包含 selection_spec");
	}
	const spec = Reflect.get(parsed, "selection_spec");
	if (typeof spec !== "object" || spec === null || typeof Reflect.get(spec, "spec_id") !== "string") {
		throw new Error("selection_spec.spec_id 必须是字符串");
	}
	return parsed as CreateSelectionRunBody;
}

export function readSavedSelectionInput(): string {
	return localStorage.getItem(STORAGE_KEY) ?? "";
}

function shanghaiLocalInput(date: Date): string {
	const parts = new Intl.DateTimeFormat("en-CA", {
		timeZone: "Asia/Shanghai",
		year: "numeric",
		month: "2-digit",
		day: "2-digit",
		hour: "2-digit",
		minute: "2-digit",
		hourCycle: "h23",
	}).formatToParts(date);
	const value = (type: Intl.DateTimeFormatPartTypes): string => parts.find((part) => part.type === type)?.value ?? "00";
	return `${value("year")}-${value("month")}-${value("day")}T${value("hour")}:${value("minute")}`;
}

function shanghaiIso(localValue: string): string {
	const withSeconds = localValue.length === 16 ? `${localValue}:00` : localValue;
	return `${withSeconds}+08:00`;
}

function parseDecimal(value: string): number | null {
	const trimmed = value.trim();
	if (!trimmed) return null;
	const parsed = Number(trimmed);
	return Number.isFinite(parsed) ? parsed : null;
}

function parseInteger(value: string): number | null {
	const trimmed = value.trim();
	if (!/^-?\d+$/u.test(trimmed)) return null;
	const parsed = Number(trimmed);
	// 超出安全整数范围的值会被 JSON 往返舍入，破坏提交身份的精确性。
	return Number.isSafeInteger(parsed) ? parsed : null;
}

type FactorRow = {
	readonly name: string;
	readonly weight: string;
};

type StrategyForm = {
	readonly universeId: string;
	readonly asOf: string;
	readonly specId: string;
	readonly specVersion: string;
	readonly topK: string;
	readonly minAverageTurnover: string;
	readonly minListingDays: string;
	readonly factors: readonly FactorRow[];
	readonly excludeLimitUp: boolean;
	readonly excludeLimitDown: boolean;
	readonly seed: string;
	readonly lookbackDays: string;
	readonly knowledgeCutoff: string;
	readonly publicationCutoff: string;
};

const INITIAL_FACTORS: readonly FactorRow[] = [{ name: "momentum_1m", weight: "1" }];

function initialForm(): StrategyForm {
	return {
		universeId: "",
		asOf: shanghaiLocalInput(new Date()),
		specId: "stock-momentum-manual",
		specVersion: "1",
		topK: "5",
		minAverageTurnover: "20000000",
		minListingDays: "60",
		factors: INITIAL_FACTORS,
		excludeLimitUp: true,
		excludeLimitDown: true,
		seed: "0",
		lookbackDays: "400",
		knowledgeCutoff: "",
		publicationCutoff: "",
	};
}

function strategyErrors(form: StrategyForm): readonly string[] {
	const errors: string[] = [];
	if (!form.asOf.trim()) errors.push("请填写决策时点 as_of");
	if (!form.universeId.trim()) errors.push("请选择 universe 证券池");
	if (!form.specId.trim()) errors.push("请填写 spec_id");
	if (!form.specVersion.trim()) errors.push("请填写 spec_version");
	const topK = parseInteger(form.topK);
	if (topK === null || topK < 1) errors.push("top_k 需为 ≥1 的整数");
	const minAverageTurnover = parseDecimal(form.minAverageTurnover);
	if (minAverageTurnover === null || minAverageTurnover < 0) errors.push("最小均额需为 ≥0 的有限数值");
	const minListingDays = parseInteger(form.minListingDays);
	if (minListingDays === null || minListingDays < 1) errors.push("最小上市天数需为 ≥1 的整数");
	const names: string[] = [];
	let weightSum = 0;
	for (const [index, factor] of form.factors.entries()) {
		const name = factor.name.trim();
		if (!name) errors.push(`第 ${index + 1} 个因子名称不能为空`);
		else if (names.includes(name)) errors.push(`因子名称重复：${name}`);
		else names.push(name);
		const weight = parseDecimal(factor.weight);
		if (weight === null || weight < 0 || weight > 1) errors.push(`第 ${index + 1} 个因子权重需在 0 到 1 之间`);
		else weightSum += weight;
	}
	if (Math.abs(weightSum - 1) > WEIGHT_SUM_TOLERANCE) errors.push("因子权重之和需为 1");
	const seed = parseInteger(form.seed);
	if (seed === null || seed < 0) errors.push("seed 需为 ≥0 的整数");
	const lookbackDays = parseInteger(form.lookbackDays);
	if (lookbackDays === null || lookbackDays < 60 || lookbackDays > 1500) errors.push("回看天数需为 60–1500 的整数");
	if (form.asOf.trim() && form.knowledgeCutoff.trim()) {
		const asOf = Date.parse(shanghaiIso(form.asOf.trim()));
		const knowledge = Date.parse(shanghaiIso(form.knowledgeCutoff.trim()));
		if (Number.isFinite(asOf) && Number.isFinite(knowledge) && knowledge > asOf)
			errors.push("知识截止不能晚于决策时点");
	}
	if (form.knowledgeCutoff.trim() && form.publicationCutoff.trim()) {
		const knowledge = Date.parse(shanghaiIso(form.knowledgeCutoff.trim()));
		const publication = Date.parse(shanghaiIso(form.publicationCutoff.trim()));
		if (Number.isFinite(knowledge) && Number.isFinite(publication) && publication > knowledge)
			errors.push("披露截止不能晚于知识截止");
	}
	return [...new Set(errors)];
}

function strategyBody(form: StrategyForm): AssembleSelectionRunBody {
	const body: AssembleSelectionRunBody = {
		as_of: shanghaiIso(form.asOf.trim()),
		asset_kind: "stock",
		excluded_limit_states: [
			...(form.excludeLimitUp ? (["limit_up"] as const) : []),
			...(form.excludeLimitDown ? (["limit_down"] as const) : []),
		],
		factor_weights: form.factors.map((factor) => ({
			name: factor.name.trim(),
			weight: parseDecimal(factor.weight) ?? 0,
		})),
		lookback_days: parseInteger(form.lookbackDays) ?? 400,
		min_average_turnover: parseDecimal(form.minAverageTurnover) ?? 0,
		min_listing_days: parseInteger(form.minListingDays) ?? 60,
		seed: parseInteger(form.seed) ?? 0,
		spec_id: form.specId.trim(),
		spec_version: form.specVersion.trim(),
		top_k: parseInteger(form.topK) ?? 1,
		universe_id: form.universeId.trim(),
	};
	if (form.knowledgeCutoff.trim()) body.knowledge_cutoff = shanghaiIso(form.knowledgeCutoff.trim());
	if (form.publicationCutoff.trim()) body.publication_cutoff = shanghaiIso(form.publicationCutoff.trim());
	return body;
}

const INPUT_CLASS =
	"rounded-(--radius-sm) border border-(--color-border-primary) bg-(--color-surface-1) px-2 py-1.5 text-xs text-(--color-foreground)";

export function SelectionRunInput({
	busy,
	onRun,
	onSaved,
}: {
	readonly busy: boolean;
	readonly onRun: (input: CreateSelectionRunBody) => void;
	readonly onSaved: (input: CreateSelectionRunBody) => void;
}) {
	const [form, setForm] = useState<StrategyForm>(initialForm);
	const [asOfEdited, setAsOfEdited] = useState(false);
	const universes = useQuery({ queryKey: ["selection", "universe-options"], queryFn: listUniverseOptions });
	useEffect(() => {
		const options = universes.data;
		if (!options) return;
		if (
			options.length === 0
				? form.universeId !== ""
				: !form.universeId || !options.some((option) => option.universeId === form.universeId)
		) {
			setForm((current) => ({ ...current, universeId: options[0]?.universeId ?? "" }));
		}
	}, [universes.data, form.universeId]);
	const [advancedValue, setAdvancedValue] = useState(readSavedSelectionInput);
	const [message, setMessage] = useState<string | null>(null);
	const [instrument, setInstrument] = useState("");

	const errors = strategyErrors(form);
	const body = errors.length === 0 ? strategyBody(form) : null;

	const assemble = useMutation({
		mutationFn: async (payload: AssembleSelectionRunBody) => {
			const view = toAssembledRunView(await assembleSelectionRun(payload), payload);
			return { ...view, admissionView: toAdmissionView(view.admission) satisfies AdmissionView };
		},
	});
	const sameAttempt = Boolean(
		body && assemble.variables && JSON.stringify(assemble.variables) === JSON.stringify(body),
	);
	const assembled = sameAttempt ? assemble.data : undefined;

	const inspection = useMutation({
		mutationFn: async ({ raw, instrument }: { raw: string; instrument: string }) =>
			toAdmissionView(await assessSelectionAdmission(parseRunInput(raw), instrument ? Number(instrument) : undefined)),
	});
	const universe = useMutation({
		mutationFn: (raw: string) => resolveSelectionUniverse(parseRunInput(raw)),
	});
	const historical = universe.variables === advancedValue ? universe.data : undefined;
	const currentInspection =
		inspection.variables?.raw === advancedValue && inspection.variables.instrument === instrument;
	let instruments: CreateSelectionRunBody["instruments"] = [];
	try {
		const input = parseRunInput(advancedValue);
		if (Array.isArray(input.instruments))
			instruments = input.instruments.filter(
				(item) => item && typeof item.instrument_id === "number" && typeof item.instrument_name === "string",
			);
	} catch {
		/* Incomplete drafts are validated on explicit action. */
	}
	const admission = currentInspection ? inspection.data : undefined;

	function updateForm(patch: Partial<StrategyForm>): void {
		setForm((current) => ({ ...current, ...patch }));
	}

	function updateFactor(index: number, patch: Partial<FactorRow>): void {
		setForm((current) => ({
			...current,
			factors: current.factors.map((factor, position) => (position === index ? { ...factor, ...patch } : factor)),
		}));
	}

	function validated(): CreateSelectionRunBody | null {
		try {
			const input = parseRunInput(advancedValue);
			setMessage(null);
			return input;
		} catch (error) {
			setMessage(error instanceof Error ? error.message : "运行输入不是有效 JSON");
			return null;
		}
	}

	function save(): void {
		const input = validated();
		if (!input) return;
		localStorage.setItem(STORAGE_KEY, JSON.stringify(input, null, 2));
		setAdvancedValue(JSON.stringify(input, null, 2));
		setMessage("已保存精确输入草案到本机");
		onSaved(input);
	}

	return (
		<section className="border-b border-(--color-border-subtle) bg-(--color-surface-strip)">
			<div className="grid gap-3 px-4 py-3">
				<p className="max-w-3xl text-xs leading-5 text-(--color-foreground-tertiary)">
					按策略字段新建运行：服务端负责组装历史证券池与数据区间等全部 PIT 事实，先组装预览准入，再创建运行。
				</p>
				<div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
					<div className="grid gap-1 text-xs">
						{universes.isError ? (
							<span className="flex items-center gap-2">
								<span role="alert">证券池列表加载失败</span>
								<Button type="button" variant="outline" size="sm" onClick={() => void universes.refetch()}>
									重试
								</Button>
							</span>
						) : (
							<label className="grid gap-1">
								universe 证券池（组装 v1 仅支持全市场股票池）
								<select
									aria-label="universe 证券池"
									className={INPUT_CLASS}
									value={form.universeId}
									onChange={(event) => updateForm({ universeId: event.currentTarget.value })}
								>
									<option value="">{universes.isLoading ? "加载证券池…" : "请选择"}</option>
									{(universes.data ?? []).map((option) => (
										<option key={option.universeId} value={option.universeId}>
											{option.name}（{option.universeId}）
										</option>
									))}
								</select>
							</label>
						)}
					</div>
					<label className="grid gap-1 text-xs">
						决策时点 as_of（上海时区）
						<input
							aria-label="决策时点 as_of"
							className={INPUT_CLASS}
							type="datetime-local"
							value={form.asOf}
							onChange={(event) => {
								setAsOfEdited(true);
								updateForm({ asOf: event.currentTarget.value });
							}}
						/>
					</label>
					<label className="grid gap-1 text-xs">
						spec_id
						<input
							aria-label="spec_id"
							className={INPUT_CLASS}
							value={form.specId}
							onChange={(event) => updateForm({ specId: event.currentTarget.value })}
						/>
					</label>
					<label className="grid gap-1 text-xs">
						spec_version
						<input
							aria-label="spec_version"
							className={INPUT_CLASS}
							value={form.specVersion}
							onChange={(event) => updateForm({ specVersion: event.currentTarget.value })}
						/>
					</label>
					<label className="grid gap-1 text-xs">
						top_k（入选数量）
						<input
							aria-label="top_k"
							className={INPUT_CLASS}
							type="number"
							min={1}
							step={1}
							value={form.topK}
							onChange={(event) => updateForm({ topK: event.currentTarget.value })}
						/>
					</label>
					<label className="grid gap-1 text-xs">
						最小日均成交额
						<input
							aria-label="最小日均成交额"
							className={INPUT_CLASS}
							type="number"
							min={0}
							value={form.minAverageTurnover}
							onChange={(event) => updateForm({ minAverageTurnover: event.currentTarget.value })}
						/>
					</label>
					<label className="grid gap-1 text-xs">
						最小上市天数
						<input
							aria-label="最小上市天数"
							className={INPUT_CLASS}
							type="number"
							min={1}
							step={1}
							value={form.minListingDays}
							onChange={(event) => updateForm({ minListingDays: event.currentTarget.value })}
						/>
					</label>
					<label className="grid gap-1 text-xs">
						seed
						<input
							aria-label="seed"
							className={INPUT_CLASS}
							type="number"
							min={0}
							step={1}
							value={form.seed}
							onChange={(event) => updateForm({ seed: event.currentTarget.value })}
						/>
					</label>
					<label className="grid gap-1 text-xs">
						回看天数（60–1500）
						<input
							aria-label="回看天数"
							className={INPUT_CLASS}
							type="number"
							min={60}
							max={1500}
							step={1}
							value={form.lookbackDays}
							onChange={(event) => updateForm({ lookbackDays: event.currentTarget.value })}
						/>
					</label>
					<label className="grid gap-1 text-xs">
						知识截止（可选）
						<input
							aria-label="知识截止（可选）"
							className={INPUT_CLASS}
							type="datetime-local"
							value={form.knowledgeCutoff}
							onChange={(event) => updateForm({ knowledgeCutoff: event.currentTarget.value })}
						/>
					</label>
					<label className="grid gap-1 text-xs">
						披露截止（可选）
						<input
							aria-label="披露截止（可选）"
							className={INPUT_CLASS}
							type="datetime-local"
							value={form.publicationCutoff}
							onChange={(event) => updateForm({ publicationCutoff: event.currentTarget.value })}
						/>
					</label>
				</div>
				<fieldset className="space-y-1 text-xs">
					<legend className="text-(--color-foreground-tertiary)">因子权重（权重之和需为 1）</legend>
					{form.factors.map((factor, index) => (
						// biome-ignore lint/suspicious/noArrayIndexKey: 行随编辑整体受控，索引即行身份
						<div key={index} className="flex items-center gap-2">
							<input
								aria-label={`因子 ${index + 1} 名称`}
								className={`${INPUT_CLASS} w-40`}
								placeholder="因子名称，如 momentum_1m"
								value={factor.name}
								onChange={(event) => updateFactor(index, { name: event.currentTarget.value })}
							/>
							<input
								aria-label={`因子 ${index + 1} 权重`}
								className={`${INPUT_CLASS} w-24`}
								type="number"
								min={0}
								max={1}
								step={0.1}
								value={factor.weight}
								onChange={(event) => updateFactor(index, { weight: event.currentTarget.value })}
							/>
							<Button
								type="button"
								variant="outline"
								size="sm"
								disabled={form.factors.length === 1}
								onClick={() =>
									setForm((current) => ({
										...current,
										factors: current.factors.filter((_, position) => position !== index),
									}))
								}
							>
								删除因子
							</Button>
						</div>
					))}
					<Button
						type="button"
						variant="outline"
						size="sm"
						onClick={() =>
							setForm((current) => ({ ...current, factors: [...current.factors, { name: "", weight: "" }] }))
						}
					>
						添加因子
					</Button>
				</fieldset>
				<fieldset className="space-y-1 text-xs">
					<legend className="text-(--color-foreground-tertiary)">排除涨跌停状态</legend>
					<label className="flex items-center gap-2">
						<input
							type="checkbox"
							aria-label="排除涨停"
							checked={form.excludeLimitUp}
							onChange={(event) => updateForm({ excludeLimitUp: event.currentTarget.checked })}
						/>
						limit_up
					</label>
					<label className="flex items-center gap-2">
						<input
							type="checkbox"
							aria-label="排除跌停"
							checked={form.excludeLimitDown}
							onChange={(event) => updateForm({ excludeLimitDown: event.currentTarget.checked })}
						/>
						limit_down
					</label>
				</fieldset>
				{errors.length > 0 && (
					<ul role="alert" className="grid gap-1 text-xs text-(--color-risk-critical-fg)">
						{errors.map((error) => (
							<li key={error}>{error}</li>
						))}
					</ul>
				)}
				<div className="flex flex-wrap items-center gap-2">
					<Button
						type="button"
						disabled={assemble.isPending || errors.length > 0}
						onClick={() => {
							if (!body) return;
							// 未手动改过的实时默认值在提交时刻刷新：留置页面数分钟后
							// 的旧时点会被服务端偏差窗判为回溯。
							const asOf = asOfEdited ? form.asOf : shanghaiLocalInput(new Date());
							const nextForm = { ...form, asOf };
							if (!asOfEdited) setForm(nextForm);
							assemble.mutate(strategyBody(nextForm));
						}}
					>
						{assemble.isPending ? "组装中…" : "组装并预览"}
					</Button>
					<Button
						type="button"
						disabled={busy || errors.length > 0 || !assembled || !assembled.admissionView.allowed}
						onClick={() => {
							if (assembled) onRun(assembled.request);
						}}
					>
						{busy ? "运行中…" : "创建运行"}
					</Button>
					{!assembled && sameAttempt && assemble.isPending && (
						<span role="status" className="text-xs text-(--color-foreground-tertiary)">
							正在组装服务端事实…
						</span>
					)}
				</div>
				{sameAttempt && assemble.isError && (
					<p role="alert" className="text-xs text-(--color-risk-critical-fg)">
						{assemble.error.message}
					</p>
				)}
				{assembled && (
					<section
						aria-label="组装摘要"
						className="grid gap-1 rounded-(--radius-md) border border-(--color-border-subtle) p-3 text-xs"
					>
						<p role="status">已按策略组装服务端事实（重新组装前不会反映新的字段修改）。</p>
						<p className="break-all">
							universe 快照：<span className="font-mono">{assembled.request.universe_snapshot_id}</span>
						</p>
						<p>
							数据区间：{assembled.request.data_from ?? "未知"} → {assembled.request.data_to ?? "未知"}
						</p>
						<p>输入证券：{assembled.request.instruments.length} 只</p>
					</section>
				)}
				{assembled && (
					<SelectionAdmission
						key={JSON.stringify(assemble.variables)}
						value={assembled.admissionView}
						scope="组装结果"
					/>
				)}
			</div>
			<details className="border-t border-(--color-border-subtle)">
				<summary className="cursor-pointer px-4 py-2 text-xs font-medium text-(--color-foreground-secondary)">
					高级模式 · 导入完整输入包
				</summary>
				<div className="grid gap-3 px-4 pb-4">
					<p className="max-w-3xl text-xs leading-5 text-(--color-foreground-tertiary)">
						输入包需绑定字段来源、数据区间及历史证券池快照。观察池须保留退市与不可投资证券；服务端会核对完整名单、许可、认证和时点。
					</p>
					<textarea
						aria-label="Selection 输入 JSON"
						className="min-h-40 w-full rounded-(--radius-md) border border-(--color-border-primary) bg-(--color-surface-1) p-3 font-mono text-xs text-(--color-foreground)"
						placeholder='{"as_of":"...","selection_spec":{"spec_id":"..."}}'
						spellCheck={false}
						value={advancedValue}
						onChange={(event) => {
							setAdvancedValue(event.currentTarget.value);
							setInstrument("");
						}}
					/>
					<label className="grid gap-1 text-xs">
						选择证券查看字段资格
						<select
							aria-label="选择证券"
							value={instrument}
							onChange={(event) => setInstrument(event.currentTarget.value)}
							className="rounded-(--radius-md) border border-(--color-border-primary) bg-(--color-surface-1) p-2"
						>
							<option value="">全部输入证券</option>
							{instruments.map((item) => (
								<option key={item.instrument_id} value={item.instrument_id}>
									{item.instrument_name} · {item.instrument_id}
								</option>
							))}
						</select>
					</label>
					{instrument && <p className="text-xs">当前仅检查所选证券的数据资格；执行时服务端仍校验输入包的全部证券。</p>}
					<div className="flex items-center gap-2">
						<Button
							type="button"
							variant="outline"
							disabled={inspection.isPending || !advancedValue.trim()}
							onClick={() => {
								if (validated()) inspection.mutate({ raw: advancedValue, instrument });
							}}
						>
							{inspection.isPending ? "检查中…" : "检查字段准入"}
						</Button>
						<Button
							type="button"
							variant="outline"
							disabled={universe.isPending || !advancedValue.trim()}
							onClick={() => universe.mutate(advancedValue)}
						>
							{universe.isPending ? "读取中…" : "查看历史证券池"}
						</Button>
						<Button type="button" variant="outline" onClick={save}>
							校验并保存输入
						</Button>
						<Button
							type="button"
							disabled={busy || advancedValue.trim().length === 0 || (!instrument && admission?.allowed === false)}
							onClick={() => {
								const input = validated();
								if (input) onRun(input);
							}}
						>
							{busy ? "运行中…" : "执行 SelectionRun"}
						</Button>
						{message && (
							<span role="status" className="text-xs text-(--color-foreground-tertiary)">
								{message}
							</span>
						)}
					</div>
					{currentInspection && inspection.isError && <p role="alert">{inspection.error.message}</p>}
					{universe.variables === advancedValue && universe.isError && <p role="alert">{universe.error.message}</p>}
					{historical && (
						<section aria-label="历史证券池" className="space-y-2 text-xs">
							<p>
								历史观察池 · {historical.asOf} · {historical.members.length} 只证券
							</p>
							<p className="break-all">快照：{historical.snapshotId}</p>
							<p>
								知识截止：{historical.knowledgeCutoff} · 披露截止：{historical.publicationCutoff}
							</p>
							{historical.members.length === 0 ? (
								<p>该时点没有可见证券。</p>
							) : (
								<ul className="max-h-48 overflow-auto">
									{historical.members.map((member) => (
										<li key={member.instrumentId}>
											{member.instrumentId} · {member.investable ? "可投资" : "不可投资"} · {member.reasons}
										</li>
									))}
								</ul>
							)}
						</section>
					)}
					{admission && (
						<SelectionAdmission
							key={`${advancedValue}:${instrument}`}
							value={admission}
							scope={instrument ? "所选证券" : "全部输入证券"}
						/>
					)}
				</div>
			</details>
		</section>
	);
}
