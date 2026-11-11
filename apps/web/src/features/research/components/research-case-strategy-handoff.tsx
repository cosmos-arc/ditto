import { useMutation } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { type FormEvent, type ReactElement, useRef, useState } from "react";
import { ApiError } from "@/api/errors";
import { Button } from "@/components/ui/button";
import type { ResearchCaseDetail } from "../api/research-cases";
import {
	type HandoffConversion,
	type HandoffGap,
	proposeStrategyTemplateDraft,
	type StrategyTemplateDraftProposal,
} from "../api/strategy-templates";

/** 模板选项的结构化形状：由 workflow 层从策略目录映射传入（features 不互相依赖）。 */
export type StrategyHandoffTemplateOption = {
	readonly templateId: string;
	readonly displayName: string;
	readonly description: string;
};

/** 策略创建槽位：由 workflow 层用正式策略创建 API 实现（research 不依赖 strategy）。 */
export type StrategyHandoffCreateTarget = {
	readonly strategyId: string;
	readonly name: string;
	readonly specJson: Readonly<Record<string, unknown>>;
	readonly tags: readonly string[];
};

export type StrategyHandoffCreateResult = {
	readonly strategyId: string;
	readonly version: number;
};

/** 模板目录的加载状态（由组合层从目录查询映射，空态不再与 pending/error 混淆）。 */
export type StrategyHandoffCatalogState =
	| { readonly state: "pending" }
	| { readonly state: "error"; readonly message: string; readonly retry: () => void }
	| { readonly state: "ready" };

export type ResearchCaseStrategyHandoffProps = {
	readonly caseDetail: ResearchCaseDetail;
	/** 按用例资产类别筛过的模板选项（由组合层提供）。 */
	readonly templates: readonly StrategyHandoffTemplateOption[];
	/** 目录查询状态；ready 时 templates 为空才是真正的「无适用模板」。 */
	readonly catalogState: StrategyHandoffCatalogState;
	readonly createStrategy: (
		target: StrategyHandoffCreateTarget,
		idempotencyKey: string,
	) => Promise<StrategyHandoffCreateResult>;
};

const FIELD_CLASS =
	"h-8 rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-1) px-2.5 text-sm text-(--color-foreground)";

function shortIdentity(value: string): string {
	return value.split(":sha256:").at(-1)?.slice(0, 12) ?? value;
}

function errorMessage(error: unknown): string {
	if (error instanceof ApiError) {
		return `${error.status} ${error.errorCode ?? "STRATEGY_HANDOFF_ERROR"}: ${error.message}`;
	}
	return error instanceof Error ? error.message : String(error);
}

function ConversionList({ items }: { readonly items: readonly HandoffConversion[] }) {
	return (
		<dl className="space-y-1.5" aria-label="已转换内容">
			{items.map((item) => (
				<div key={item.source} className="grid grid-cols-[7rem_minmax(0,1fr)] gap-x-2 text-xs">
					<dt className="text-(--color-foreground-tertiary)">{item.source}</dt>
					<dd className="text-(--color-foreground-secondary)">{item.detail}</dd>
				</div>
			))}
		</dl>
	);
}

function GapList({ items }: { readonly items: readonly HandoffGap[] }) {
	return (
		<ul className="space-y-2" aria-label="不可直接转换的条件">
			{items.map((item) => (
				<li
					key={item.source}
					className="rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-2) p-2"
				>
					<p className="text-xs font-medium text-(--color-foreground)">
						{item.source}
						{item.detail ? (
							<span className="ml-2 font-mono text-[11px] text-(--color-foreground-tertiary)">{item.detail}</span>
						) : null}
					</p>
					<p className="mt-1 text-[11px] leading-4 text-(--color-foreground-tertiary)">{item.explanation}</p>
				</li>
			))}
		</ul>
	);
}

function ProposalPanel({
	proposal,
	assetKindLabel,
}: {
	readonly proposal: StrategyTemplateDraftProposal;
	readonly assetKindLabel: string;
}) {
	const lineage = proposal.lineage as Record<string, unknown>;
	const asOf = typeof lineage["as_of"] === "string" ? lineage["as_of"].slice(0, 10) : "—";
	const runId = typeof lineage["selection_run_id"] === "string" ? lineage["selection_run_id"] : "";
	return (
		<div className="space-y-3" data-info-unit="strategy-handoff-proposal">
			<p className="text-xs text-(--color-foreground-secondary)" data-info-unit="strategy-handoff-universe">
				适用池：<span className="font-mono">{String(proposal.spec_json["universe"] ?? "")}</span>（{assetKindLabel}
				）· 因子与权重、入选数量已进入模板草稿。
			</p>
			<ConversionList items={[...proposal.converted]} />
			{proposal.unconverted.length > 0 ? (
				<div className="space-y-2">
					<p className="text-xs font-medium text-(--color-risk-warning-fg)">
						以下来源条件不能直接转换，不会自动套用到模板：
					</p>
					<GapList items={[...proposal.unconverted]} />
				</div>
			) : null}
			<p className="font-mono text-[11px] text-(--color-foreground-tertiary)" data-info-unit="strategy-handoff-lineage">
				来源运行 {shortIdentity(runId)} · 决策日 {asOf}
			</p>
		</div>
	);
}

/** 研究用例 → 三类研究模板 → 策略版本草稿（无 Agent 的传统研究交接）。 */
export function ResearchCaseStrategyHandoff({
	caseDetail,
	templates,
	catalogState,
	createStrategy,
}: ResearchCaseStrategyHandoffProps): ReactElement {
	const assetKindLabel = caseDetail.asset_kind === "stock" ? "股票" : "ETF";
	const [templateId, setTemplateId] = useState<string | null>(null);
	const [strategyId, setStrategyId] = useState("");
	const [name, setName] = useState("");
	// 用户已编辑过的字段不再被新提案的默认值覆盖（切换模板保留已改输入）。
	const strategyIdEdited = useRef(false);
	const nameEdited = useRef(false);
	const proposal = useMutation({
		mutationFn: (selected: string) =>
			proposeStrategyTemplateDraft(caseDetail.selection_run_id, selected, caseDetail.case_id),
		onSuccess: (data) => {
			if (!strategyIdEdited.current) {
				setStrategyId(typeof data.spec_json["strategy_id"] === "string" ? data.spec_json["strategy_id"] : "");
			}
			if (!nameEdited.current) {
				setName(typeof data.spec_json["name"] === "string" ? data.spec_json["name"] : "");
			}
		},
	});
	const current = templateId !== null && proposal.variables === templateId ? (proposal.data ?? null) : null;
	// 幂等键对同一提交目标复用：失败重试走幂等重放而不是撞 strategy_id
	// （与 Strategy Studio saveAttemptRef 同模式）。
	const createAttemptRef = useRef<{ readonly fingerprint: string; readonly key: string } | null>(null);
	const create = useMutation({
		mutationFn: (target: StrategyHandoffCreateTarget) => {
			const fingerprint = JSON.stringify([target.strategyId, target.name, target.specJson, target.tags]);
			const previous = createAttemptRef.current;
			// 键长上限 128（服务端合同）：全量提交指纹放不进键，靠 ref 比对。
			const key =
				previous?.fingerprint === fingerprint ? previous.key : `strategy-handoff:${globalThis.crypto.randomUUID()}`;
			createAttemptRef.current = { fingerprint, key };
			return createStrategy(target, key);
		},
	});
	const created = create.data;
	// 冲突判定用后端结构化错误码（同名已存在/版本冲突/幂等键复用），
	// 不依赖错误消息关键词（历史缺陷：消息不含 conflict 时得到 400 死胡同）。
	const conflict =
		create.error instanceof ApiError &&
		(create.error.status === 409 ||
			create.error.errorCode === "STRATEGY_ALREADY_EXISTS" ||
			create.error.errorCode === "STRATEGY_VERSION_ALREADY_EXISTS" ||
			create.error.errorCode === "STRATEGY_REVISION_CONFLICT" ||
			create.error.errorCode === "IDEMPOTENCY_KEY_REUSED");

	function selectTemplate(next: string): void {
		setTemplateId(next);
		proposal.mutate(next);
	}

	function submit(event: FormEvent<HTMLFormElement>): void {
		event.preventDefault();
		if (!current || !templateId || created) return;
		const tags = Array.isArray(current.spec_json["tags"])
			? (current.spec_json["tags"] as readonly unknown[]).map((tag) => String(tag))
			: [];
		create.mutate({
			strategyId,
			name,
			specJson: { ...current.spec_json, strategy_id: strategyId, name },
			tags,
		});
	}

	return (
		<section
			aria-label="形成策略版本"
			data-info-level="l2"
			data-info-unit="research-case-strategy-handoff"
			className="border border-(--color-border-subtle) bg-(--color-surface-panel-base) px-4 py-3"
		>
			<div className="mb-2 flex items-center justify-between">
				<h3 className="text-sm font-semibold">形成策略版本</h3>
				<span className="text-[11px] text-(--color-foreground-tertiary)">{assetKindLabel}研究模板</span>
			</div>
			{catalogState.state === "pending" ? (
				<p className="text-xs text-(--color-foreground-tertiary)" role="status">
					正在读取研究模板…
				</p>
			) : catalogState.state === "error" ? (
				<div className="text-xs" role="alert">
					<p className="text-(--color-led-danger)">模板目录读取失败：{catalogState.message}</p>
					<button type="button" className="underline" onClick={catalogState.retry}>
						重试模板目录
					</button>
				</div>
			) : templates.length === 0 ? (
				<p className="text-xs text-(--color-foreground-tertiary)">当前目录没有适用于该用例资产类别的研究模板。</p>
			) : (
				<fieldset className="space-y-2" data-info-unit="strategy-handoff-templates">
					<legend className="sr-only">选择研究模板</legend>
					{templates.map((entry) => (
						<label
							key={entry.templateId}
							className={`flex cursor-pointer items-start gap-2 rounded-(--radius-sm) border p-2 text-xs transition-colors ${
								templateId === entry.templateId
									? "border-(--color-border-strong) bg-(--color-interaction-selected-bg)"
									: "border-(--color-border-subtle) hover:bg-(--color-interaction-hover-subtle-bg)"
							}`}
						>
							<input
								type="radio"
								name="strategy-template"
								className="mt-0.5"
								checked={templateId === entry.templateId}
								onChange={() => selectTemplate(entry.templateId)}
							/>
							<span>
								<span className="font-medium text-(--color-foreground)">{entry.displayName}</span>
								<span className="ml-2 font-mono text-[11px] text-(--color-foreground-tertiary)">
									{entry.templateId}
								</span>
								<span className="mt-0.5 block text-[11px] leading-4 text-(--color-foreground-tertiary)">
									{entry.description}
								</span>
							</span>
						</label>
					))}
				</fieldset>
			)}
			{proposal.isPending ? (
				<p className="mt-3 text-xs text-(--color-foreground-tertiary)" role="status">
					正在按固定运行生成模板草稿…
				</p>
			) : null}
			{proposal.isError ? (
				<div className="mt-3 text-xs" role="alert" data-info-unit="strategy-handoff-error">
					<p className="text-(--color-led-danger)">{errorMessage(proposal.error)}</p>
					{proposal.error instanceof ApiError && proposal.error.errorCode === "selection_policy_snapshot_missing" ? (
						<p className="mt-1 text-(--color-foreground-tertiary)">
							该运行的筛选条件快照未保存（旧数据）。回到该运行的筛选工作面重新运行一次，再从这里交接。
						</p>
					) : null}
					<a
						className="mt-2 inline-block text-(--color-accent) hover:underline"
						href={`/markets/screener?run=${encodeURIComponent(caseDetail.selection_run_id)}`}
					>
						回到该运行的筛选工作面
					</a>
				</div>
			) : null}
			{current ? (
				<form className="mt-3 space-y-3" onSubmit={submit} data-info-unit="strategy-handoff-form">
					<ProposalPanel proposal={current} assetKindLabel={assetKindLabel} />
					{created ? (
						<div className="space-y-2" role="status" data-info-unit="strategy-handoff-created">
							<p className="text-xs text-(--color-led-success)">
								已创建策略草稿 {created.strategyId} · v{created.version}，后续保存、审查与发布走版本治理。
							</p>
							<div className="flex flex-wrap gap-2">
								<Button asChild size="sm">
									<Link to="/research/strategies/$id" params={{ id: created.strategyId }}>
										查看策略版本
									</Link>
								</Button>
								<Button asChild size="sm" variant="outline">
									<Link to="/research/strategies/$id/studio" params={{ id: created.strategyId }}>
										打开 Strategy Studio
									</Link>
								</Button>
							</div>
						</div>
					) : (
						<>
							<label className="flex flex-col gap-1 text-xs text-(--color-foreground-secondary)">
								新策略 ID
								<input
									aria-label="新策略 ID"
									className={FIELD_CLASS}
									pattern="[a-z0-9][a-z0-9_-]*"
									required
									value={strategyId}
									onChange={(event) => {
										strategyIdEdited.current = true;
										setStrategyId(event.currentTarget.value);
									}}
								/>
							</label>
							<label className="flex flex-col gap-1 text-xs text-(--color-foreground-secondary)">
								策略名称
								<input
									aria-label="策略名称"
									className={FIELD_CLASS}
									required
									value={name}
									onChange={(event) => {
										nameEdited.current = true;
										setName(event.currentTarget.value);
									}}
								/>
							</label>
							{create.isError ? (
								<div role="alert" className="space-y-1 text-xs">
									<p className="text-(--color-led-danger)">{errorMessage(create.error)}</p>
									{conflict ? (
										<Link
											className="text-(--color-accent) hover:underline"
											to="/research/strategies/$id"
											params={{ id: strategyId }}
										>
											查看已存在策略 {strategyId}
										</Link>
									) : null}
								</div>
							) : null}
							<Button type="submit" size="sm" disabled={create.isPending || !strategyId.trim() || !name.trim()}>
								{create.isPending ? "创建中…" : "创建策略草稿"}
							</Button>
						</>
					)}
				</form>
			) : null}
		</section>
	);
}
