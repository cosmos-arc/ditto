import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import {
	type AssembleSelectionRunBody,
	assembleSelectionRun,
	listFactorCatalog,
	listUniverseOptions,
	type SelectionFactorCatalogEntry,
	selectionKeys,
} from "../api";
import { toAssembledRunView } from "../assembled-run";

// 镜像服务端 math.isclose(total, 1.0, abs_tol=1e-12)：默认 rel_tol=1e-9 主导有效容差。
const WEIGHT_SUM_TOLERANCE = 1e-9;

// 全市场池的缺失输入证券可达数千只：预览只展开前 N 只，其余汇总计数。
const MISSING_INSTRUMENT_PREVIEW_LIMIT = 20;

// 新建条件行的默认阈值：截面分数秩口径下即「排进截面前 20%」。
const DEFAULT_CONDITION_THRESHOLD = "0.8";

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

type ConditionRow = {
	readonly factorName: string;
	readonly operator: "gte" | "lte";
	readonly value: string;
};

type ConditionGroup = {
	readonly rows: readonly ConditionRow[];
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
	readonly groups: readonly ConditionGroup[];
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
		// 留空 = 服务端滚动到最近完整交易日（issue 583）。
		asOf: "",
		specId: "stock-momentum-manual",
		specVersion: "1",
		topK: "5",
		minAverageTurnover: "20000000",
		minListingDays: "60",
		factors: INITIAL_FACTORS,
		groups: [],
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
	for (const [groupIndex, group] of form.groups.entries()) {
		for (const [rowIndex, row] of group.rows.entries()) {
			const position = `条件组 ${groupIndex + 1} 行 ${rowIndex + 1}`;
			if (!row.factorName) errors.push(`${position} 需选择因子`);
			const value = parseDecimal(row.value);
			if (value === null || value < 0 || value > 1) errors.push(`${position} 阈值需在 0 到 1 之间（截面分数秩）`);
		}
	}
	const seed = parseInteger(form.seed);
	if (seed === null || seed < 0) errors.push("seed 需为 ≥0 的整数");
	const lookbackDays = parseInteger(form.lookbackDays);
	if (lookbackDays === null || lookbackDays < 60 || lookbackDays > 1500) errors.push("回看天数需为 60–1500 的整数");
	// 知识截止可以晚于决策时点（#583 live lane：决策定在最近完整交易日收盘，
	// 截止从发起时刻签发），早于决策时点同样交由服务端裁定；此处只校验
	// 披露截止与知识截止的相对关系。
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
		asset_kind: "stock",
		excluded_limit_states: [
			...(form.excludeLimitUp ? (["limit_up"] as const) : []),
			...(form.excludeLimitDown ? (["limit_down"] as const) : []),
		],
		factor_filter_groups: form.groups.map((group) => ({
			conditions: group.rows.map((row) => ({
				factor_name: row.factorName,
				operator: row.operator,
				value: parseDecimal(row.value) ?? 0,
			})),
		})),
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
	// 留空的 as_of 由服务端滚动到最近完整交易日（issue 583）。
	if (form.asOf.trim()) body.as_of = shanghaiIso(form.asOf.trim());
	if (form.knowledgeCutoff.trim()) body.knowledge_cutoff = shanghaiIso(form.knowledgeCutoff.trim());
	if (form.publicationCutoff.trim()) body.publication_cutoff = shanghaiIso(form.publicationCutoff.trim());
	return body;
}

const INPUT_CLASS =
	"rounded-(--radius-sm) border border-(--color-border-primary) bg-(--color-surface-1) px-2 py-1.5 text-xs text-(--color-foreground)";

function groupOptions(entries: readonly SelectionFactorCatalogEntry[]) {
	const groups = new Map<string, SelectionFactorCatalogEntry[]>();
	for (const entry of entries) {
		const bucket = groups.get(entry.group_label) ?? [];
		bucket.push(entry);
		groups.set(entry.group_label, bucket);
	}
	return [...groups.entries()].map(([label, items]) => ({ label, items }));
}

function factorMeta(
	entries: readonly SelectionFactorCatalogEntry[],
	factorName: string,
): SelectionFactorCatalogEntry | undefined {
	return entries.find((entry) => entry.factor_id === factorName);
}

function FactorMetaLine({ entry }: { readonly entry: SelectionFactorCatalogEntry | undefined }) {
	if (!entry) return null;
	return (
		<p className="text-[11px] leading-4 text-(--color-foreground-tertiary)">
			{entry.description} · 回看 {entry.lookback_trading_days} 个交易日 · 依赖 {entry.dependencies.join("、")}
		</p>
	);
}

function FactorSelect({
	ariaLabel,
	entries,
	value,
	onChange,
}: {
	readonly ariaLabel: string;
	readonly entries: readonly SelectionFactorCatalogEntry[];
	readonly value: string;
	readonly onChange: (factorName: string) => void;
}) {
	return (
		<select
			aria-label={ariaLabel}
			className={INPUT_CLASS}
			value={value}
			onChange={(event) => onChange(event.currentTarget.value)}
		>
			{groupOptions(entries).map((group) => (
				<optgroup key={group.label} label={group.label}>
					{group.items.map((item) => (
						<option key={item.factor_id} value={item.factor_id}>
							{item.factor_id}
						</option>
					))}
				</optgroup>
			))}
		</select>
	);
}

export function SelectionRunInput({
	busy,
	onRun,
}: {
	readonly busy: boolean;
	readonly onRun: (input: AssembleSelectionRunBody) => void;
}) {
	const [form, setForm] = useState<StrategyForm>(initialForm);
	const universes = useQuery({ queryKey: ["selection", "universe-options"], queryFn: listUniverseOptions });
	const catalog = useQuery({ queryKey: selectionKeys.factorCatalog, queryFn: listFactorCatalog, staleTime: 300_000 });
	const entries = useMemo(() => catalog.data ?? [], [catalog.data]);
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

	const errors = strategyErrors(form);
	const catalogReady = catalog.isSuccess && entries.length > 0;

	const assemble = useMutation({
		mutationFn: async (payload: AssembleSelectionRunBody) =>
			toAssembledRunView(await assembleSelectionRun(payload), payload),
	});
	const sameAttempt = Boolean(
		errors.length === 0 &&
			assemble.variables &&
			JSON.stringify(assemble.variables) === JSON.stringify(strategyBody(form)),
	);
	const assembled = sameAttempt ? assemble.data : undefined;
	const missingInstruments =
		assembled?.request.instruments.filter((item) => item.declared_missing_inputs.length > 0) ?? [];
	const rotationMissingInputs = assembled?.request.rotation_missing_inputs ?? [];

	function updateForm(patch: Partial<StrategyForm>): void {
		setForm((current) => ({ ...current, ...patch }));
	}

	function updateFactor(index: number, patch: Partial<FactorRow>): void {
		setForm((current) => ({
			...current,
			factors: current.factors.map((factor, position) => (position === index ? { ...factor, ...patch } : factor)),
		}));
	}

	function updateGroupRow(groupIndex: number, rowIndex: number, patch: Partial<ConditionRow>): void {
		setForm((current) => ({
			...current,
			groups: current.groups.map((group, position) =>
				position === groupIndex
					? {
							...group,
							rows: group.rows.map((row, spot) => (spot === rowIndex ? { ...row, ...patch } : row)),
						}
					: group,
			),
		}));
	}

	function submitForm(): StrategyForm {
		// 留空的 as_of 由服务端滚动到最近完整交易日（issue 583），提交时刻无需刷新。
		return form;
	}

	return (
		<section className="border-b border-(--color-border-subtle) bg-(--color-surface-strip)">
			<div className="grid gap-3 px-4 py-3">
				<p className="max-w-3xl text-xs leading-5 text-(--color-foreground-tertiary)">
					以字段、算子、值构建筛选条件并组合合格因子权重：服务端负责组装历史证券池与数据区间等全部 PIT
					事实，可先组装预览；数据不完整时服务端会拒绝创建。
				</p>
				<p className="max-w-3xl text-[11px] leading-4 text-(--color-foreground-tertiary)">
					因子值口径：截面分数秩
					(0,1]，秩越高截面排名越靠前；因子值缺失的标的按缺证据排除（missing_data），不会静默参与排名。
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
						决策时点 as_of（上海时区，留空=最近完整交易日）
						<input
							aria-label="决策时点 as_of"
							className={INPUT_CLASS}
							type="datetime-local"
							value={form.asOf}
							onChange={(event) => updateForm({ asOf: event.currentTarget.value })}
						/>
					</label>
					<label className="grid gap-1 text-xs">
						筛选条件命名 spec_id（保存为可重跑 SelectionSpec 的身份）
						<input
							aria-label="spec_id"
							className={INPUT_CLASS}
							value={form.specId}
							onChange={(event) => updateForm({ specId: event.currentTarget.value })}
						/>
					</label>
					<label className="grid gap-1 text-xs">
						spec_version（同一命名下调整条件请递增版本）
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
							aria-label="top_k（入选数量）"
							className={INPUT_CLASS}
							type="number"
							min={1}
							step={1}
							value={form.topK}
							onChange={(event) => updateForm({ topK: event.currentTarget.value })}
						/>
					</label>
					<label className="grid gap-1 text-xs">
						最小日均成交额（元）
						<input
							aria-label="最小日均成交额（元）"
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
				<fieldset className="space-y-2 text-xs">
					<legend className="text-(--color-foreground-secondary)">筛选条件（组间需全部满足 · 组内任一满足）</legend>
					{catalog.isError && (
						<p role="alert" className="flex items-center gap-2 text-(--color-risk-critical-fg)">
							因子目录加载失败
							<Button type="button" variant="outline" size="sm" onClick={() => void catalog.refetch()}>
								重试
							</Button>
						</p>
					)}
					{catalog.isLoading && <p role="status">加载因子目录…</p>}
					{catalogReady && form.groups.length === 0 && (
						<p className="text-(--color-foreground-tertiary)">尚未添加条件；仅用硬过滤与因子权重排名。</p>
					)}
					{form.groups.map((group, groupIndex) => (
						<div
							// biome-ignore lint/suspicious/noArrayIndexKey: 行随编辑整体受控，索引即行身份
							key={groupIndex}
							className="grid gap-2 rounded-(--radius-md) border border-(--color-border-subtle) bg-(--color-surface-1) p-3"
						>
							<div className="flex items-center justify-between">
								<span className="font-medium text-(--color-foreground-secondary)">条件组 {groupIndex + 1}</span>
								<Button
									type="button"
									variant="outline"
									size="sm"
									onClick={() =>
										setForm((current) => ({
											...current,
											groups: current.groups.filter((_, position) => position !== groupIndex),
										}))
									}
								>
									删除条件组 {groupIndex + 1}
								</Button>
							</div>
							{group.rows.map((row, rowIndex) => (
								// biome-ignore lint/suspicious/noArrayIndexKey: 行随编辑整体受控，索引即行身份
								<div key={rowIndex} className="grid gap-1">
									<div className="flex flex-wrap items-center gap-2">
										{rowIndex > 0 && (
											<span className="text-[11px] font-medium text-(--color-foreground-tertiary)">或</span>
										)}
										<FactorSelect
											ariaLabel={`条件组 ${groupIndex + 1} 因子 ${rowIndex + 1}`}
											entries={entries}
											value={row.factorName}
											onChange={(factorName) => updateGroupRow(groupIndex, rowIndex, { factorName })}
										/>
										<select
											aria-label={`条件组 ${groupIndex + 1} 算子 ${rowIndex + 1}`}
											className={INPUT_CLASS}
											value={row.operator}
											onChange={(event) =>
												updateGroupRow(groupIndex, rowIndex, {
													operator: event.currentTarget.value as "gte" | "lte",
												})
											}
										>
											<option value="gte">≥ 秩</option>
											<option value="lte">≤ 秩</option>
										</select>
										<input
											aria-label={`条件组 ${groupIndex + 1} 阈值 ${rowIndex + 1}`}
											className={`${INPUT_CLASS} w-24`}
											type="number"
											min={0}
											max={1}
											step={0.05}
											value={row.value}
											onChange={(event) => updateGroupRow(groupIndex, rowIndex, { value: event.currentTarget.value })}
										/>
										<Button
											type="button"
											variant="outline"
											size="sm"
											disabled={group.rows.length === 1}
											onClick={() =>
												setForm((current) => ({
													...current,
													groups: current.groups.map((g, position) =>
														position === groupIndex ? { ...g, rows: g.rows.filter((_, spot) => spot !== rowIndex) } : g,
													),
												}))
											}
										>
											删除条件
										</Button>
									</div>
									<FactorMetaLine entry={factorMeta(entries, row.factorName)} />
								</div>
							))}
							<Button
								type="button"
								variant="outline"
								size="sm"
								onClick={() =>
									setForm((current) => ({
										...current,
										groups: current.groups.map((g, position) =>
											position === groupIndex
												? {
														...g,
														rows: [
															...g.rows,
															{
																factorName: entries[0]?.factor_id ?? "",
																operator: "gte" as const,
																value: DEFAULT_CONDITION_THRESHOLD,
															},
														],
													}
												: g,
										),
									}))
								}
							>
								添加条件
							</Button>
						</div>
					))}
					{catalogReady && (
						<Button
							type="button"
							variant="outline"
							size="sm"
							onClick={() =>
								setForm((current) => ({
									...current,
									groups: [
										...current.groups,
										{
											rows: [
												{
													factorName: entries[0]?.factor_id ?? "",
													operator: "gte" as const,
													value: DEFAULT_CONDITION_THRESHOLD,
												},
											],
										},
									],
								}))
							}
						>
							添加条件组
						</Button>
					)}
				</fieldset>
				<fieldset className="space-y-1 text-xs">
					<legend className="text-(--color-foreground-secondary)">因子权重（合格因子，权重之和需为 1）</legend>
					{catalogReady
						? form.factors.map((factor, index) => (
								// biome-ignore lint/suspicious/noArrayIndexKey: 行随编辑整体受控，索引即行身份
								<div key={index} className="grid gap-1">
									<div className="flex items-center gap-2">
										<FactorSelect
											ariaLabel={`因子 ${index + 1}`}
											entries={entries}
											value={factor.name}
											onChange={(name) => updateFactor(index, { name })}
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
									<FactorMetaLine entry={factorMeta(entries, factor.name)} />
								</div>
							))
						: null}
					{catalogReady && (
						<Button
							type="button"
							variant="outline"
							size="sm"
							onClick={() =>
								setForm((current) => ({
									...current,
									factors: [...current.factors, { name: entries[0]?.factor_id ?? "", weight: "" }],
								}))
							}
						>
							添加因子
						</Button>
					)}
					{catalog.isError && <p className="text-(--color-foreground-tertiary)">因子权重编辑需先恢复因子目录。</p>}
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
						disabled={assemble.isPending || errors.length > 0 || !catalogReady}
						onClick={() => assemble.mutate(strategyBody(submitForm()))}
					>
						{assemble.isPending ? "组装中…" : "组装并预览"}
					</Button>
					<Button
						type="button"
						disabled={busy || errors.length > 0 || !catalogReady}
						onClick={() => onRun(strategyBody(submitForm()))}
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
						{rotationMissingInputs.length > 0 && (
							<p role="alert">行业轮动缺失输入：{rotationMissingInputs.join("、")}</p>
						)}
						{missingInstruments.slice(0, MISSING_INSTRUMENT_PREVIEW_LIMIT).map((item) => (
							<p role="alert" key={item.instrument_id}>
								{item.instrument_name}（{item.instrument_id}）缺失输入：
								{item.declared_missing_inputs.join("、")}
							</p>
						))}
						{missingInstruments.length > MISSING_INSTRUMENT_PREVIEW_LIMIT && (
							<p>另有 {missingInstruments.length - MISSING_INSTRUMENT_PREVIEW_LIMIT} 只证券存在缺失输入。</p>
						)}
						{rotationMissingInputs.length === 0 && missingInstruments.length === 0 && <p>无缺失输入。</p>}
					</section>
				)}
			</div>
		</section>
	);
}
