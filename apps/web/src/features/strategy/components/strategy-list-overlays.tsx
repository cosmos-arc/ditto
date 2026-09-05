import { Link } from "@tanstack/react-router";
import { type FormEvent, useRef } from "react";
import { ApiError } from "@/api";
import { Button } from "@/components/ui/button";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import type { StrategyDetail, StrategyListItem, StrategySpec } from "@/types/strategy";
import { useCreateStrategy } from "../hooks";

export type StrategyListOverlay = "create" | "clone" | "delete";

interface StrategyListOverlaysProps {
	readonly detail: StrategyDetail | undefined;
	readonly detailLoading: boolean;
	readonly onClose: () => void;
	readonly open: StrategyListOverlay | null;
	readonly selected: StrategyListItem | null;
}

const FIELD_CLASS =
	"h-8 rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-1) px-2.5 text-sm text-(--color-foreground)";

function commandKey(): string {
	const randomId = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`;
	return `strategy-create:${randomId}`;
}

function blankSpec({
	assetClass,
	name,
	strategyId,
	template,
	universe,
}: {
	readonly assetClass: string;
	readonly name: string;
	readonly strategyId: string;
	readonly template: string;
	readonly universe: string;
}): StrategySpec {
	return {
		strategyId,
		name,
		template,
		universe,
		assetClass,
		benchmark: "",
		scorer: { method: "rank", params: {} },
		selector: { method: "top_k", params: { k: 5 } },
		execution: { frequency: "M", method: "calendar", defaultOrderType: "market" },
		constraints: [],
		params: {},
		signalExpressions: [],
		signalWeights: [],
		paramConstraints: [],
	};
}

function errorMessage(error: Error | null): string | null {
	if (!error) return null;
	if (error instanceof ApiError)
		return `${error.status} ${error.errorCode ?? "STRATEGY_CREATE_ERROR"}: ${error.message}`;
	return error.message;
}

function StrategyDraftSheet({
	detail,
	detailLoading,
	mode,
	onClose,
	selected,
}: {
	readonly detail: StrategyDetail | undefined;
	readonly detailLoading: boolean;
	readonly mode: "create" | "clone" | null;
	readonly onClose: () => void;
	readonly selected: StrategyListItem | null;
}) {
	const create = useCreateStrategy();
	const attempt = useRef<{ readonly payload: string; readonly key: string } | null>(null);
	const clone = mode === "clone";
	const source = clone ? detail : undefined;
	const created = create.data;
	const mutationError = errorMessage(create.error);

	function close() {
		create.reset();
		attempt.current = null;
		onClose();
	}

	function submit(event: FormEvent<HTMLFormElement>) {
		event.preventDefault();
		if (clone && !source) return;
		const data = new FormData(event.currentTarget);
		const strategyId = String(data.get("strategyId") ?? "").trim();
		const name = String(data.get("name") ?? "").trim();
		const template = String(data.get("template") ?? "").trim();
		const universe = String(data.get("universe") ?? "").trim();
		const assetClass = String(data.get("assetClass") ?? "").trim();
		const tags = String(data.get("tags") ?? "")
			.split(",")
			.map((tag) => tag.trim())
			.filter(Boolean);
		const spec = source
			? { ...source.spec, strategyId, name, universe: universe || source.spec.universe }
			: blankSpec({ assetClass, name, strategyId, template, universe });
		const payload = JSON.stringify({ name, spec, strategyId, tags });
		const previous = attempt.current;
		const idempotencyKey = previous?.payload === payload ? previous.key : commandKey();
		attempt.current = { payload, key: idempotencyKey };
		create.mutate({ idempotencyKey, name, spec, strategyId, tags });
	}

	return (
		<Sheet open={mode !== null} onOpenChange={(isOpen) => !isOpen && close()}>
			<SheetContent side="right" aria-label={clone ? "克隆策略" : "新建策略"} className="p-0">
				<SheetHeader className="border-b border-(--color-border-subtle) px-5 py-4 pr-14">
					<SheetTitle>{clone ? "克隆策略" : "新建策略"}</SheetTitle>
					<SheetDescription>
						{clone ? "从服务端策略定义创建一个独立 draft。" : "创建最小可编辑 draft，随后在 Studio 完善并验证。"}
					</SheetDescription>
				</SheetHeader>
				{created ? (
					<div className="flex flex-1 flex-col gap-4 p-5">
						<div className="rounded-(--radius-md) border border-(--color-led-success) bg-(--color-led-success-bg) p-4 text-sm text-(--color-led-success)">
							已创建草稿 {created.strategyId}
						</div>
						<p className="text-sm text-(--color-foreground-secondary)">
							版本 v{created.version} · 后续保存仍需校验与治理。
						</p>
						<Button asChild className="mt-auto w-full">
							<Link to="/research/strategies/$id/studio" params={{ id: created.strategyId }}>
								打开 Strategy Studio
							</Link>
						</Button>
					</div>
				) : (
					<form
						key={`${mode}:${selected?.strategyId ?? "new"}`}
						onSubmit={submit}
						className="flex flex-1 flex-col gap-4 overflow-y-auto p-5"
					>
						{clone && (
							<div className="rounded-(--radius-md) border border-(--color-border-subtle) bg-(--color-surface-2) p-3 text-xs text-(--color-foreground-secondary)">
								源策略：<span className="font-data text-(--color-foreground)">{selected?.strategyId}</span>
							</div>
						)}
						<label className="flex flex-col gap-1 text-xs text-(--color-foreground-secondary)">
							新策略 ID
							<input
								aria-label="新策略 ID"
								name="strategyId"
								required
								pattern="[a-z0-9][a-z0-9_-]*"
								defaultValue={clone ? `${selected?.strategyId ?? "strategy"}_copy` : ""}
								className={FIELD_CLASS}
							/>
						</label>
						<label className="flex flex-col gap-1 text-xs text-(--color-foreground-secondary)">
							策略名称
							<input
								aria-label="策略名称"
								name="name"
								required
								defaultValue={clone ? `${selected?.name ?? "策略"} 副本` : ""}
								className={FIELD_CLASS}
							/>
						</label>
						<label className="flex flex-col gap-1 text-xs text-(--color-foreground-secondary)">
							策略模板
							<input
								aria-label="策略模板"
								name="template"
								required
								defaultValue={source?.spec.template ?? "custom"}
								className={FIELD_CLASS}
							/>
						</label>
						<label className="flex flex-col gap-1 text-xs text-(--color-foreground-secondary)">
							Universe
							<input
								aria-label="Universe"
								name="universe"
								required
								defaultValue={source?.spec.universe ?? ""}
								className={FIELD_CLASS}
							/>
						</label>
						<label className="flex flex-col gap-1 text-xs text-(--color-foreground-secondary)">
							资产类型
							<select
								aria-label="资产类型"
								name="assetClass"
								defaultValue={source?.spec.assetClass || "etf"}
								className={FIELD_CLASS}
							>
								<option value="etf">ETF</option>
								<option value="stock">个股</option>
							</select>
						</label>
						<label className="flex flex-col gap-1 text-xs text-(--color-foreground-secondary)">
							标签（逗号分隔）
							<input
								aria-label="策略标签"
								name="tags"
								defaultValue={selected?.tags.join(", ") ?? ""}
								className={FIELD_CLASS}
							/>
						</label>
						{clone && detailLoading && (
							<p className="text-xs text-(--color-foreground-tertiary)">正在读取源策略定义…</p>
						)}
						{mutationError && (
							<p role="alert" className="text-xs text-(--color-led-danger)">
								{mutationError}
							</p>
						)}
						<Button type="submit" disabled={create.isPending || (clone && !source)} className="mt-auto w-full">
							{create.isPending ? "创建中…" : "创建草稿"}
						</Button>
					</form>
				)}
			</SheetContent>
		</Sheet>
	);
}

export function StrategyListOverlays({ detail, detailLoading, onClose, open, selected }: StrategyListOverlaysProps) {
	return (
		<>
			<StrategyDraftSheet
				mode={open === "create" || open === "clone" ? open : null}
				selected={selected}
				detail={detail}
				detailLoading={detailLoading}
				onClose={onClose}
			/>
			<Dialog open={open === "delete"} onOpenChange={(isOpen) => !isOpen && onClose()}>
				<DialogContent role="alertdialog" aria-label="删除策略">
					<DialogHeader>
						<DialogTitle>删除策略</DialogTitle>
						<DialogDescription>策略定义采用 append-only 版本治理，不提供直接 DELETE。</DialogDescription>
					</DialogHeader>
					<div className="rounded-(--radius-md) border border-(--color-led-warning) bg-(--color-led-warning-bg) p-3 text-sm text-(--color-foreground-secondary)">
						请在详情页审查依赖与 active pointer，再按治理流程弃用目标版本。
					</div>
					<DialogFooter>
						<Button asChild>
							<Link to="/research/strategies/$id" params={{ id: selected?.strategyId ?? "" }}>
								前往版本治理
							</Link>
						</Button>
					</DialogFooter>
				</DialogContent>
			</Dialog>
		</>
	);
}
