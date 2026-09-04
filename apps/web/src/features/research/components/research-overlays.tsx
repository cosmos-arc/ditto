import { Link } from "@tanstack/react-router";
import {
	Sheet,
	SheetClose,
	SheetContent,
	SheetDescription,
	SheetFooter,
	SheetHeader,
	SheetTitle,
} from "@/components/ui/sheet";
import type { ExperimentListItem } from "@/types";
import type { ReviewQueueEntry } from "@/types/review";

export type ResearchOverlayId = "new-backtest" | "new-strategy" | "new-experiment" | "run-detail" | "review-action";

type OverlayCopy = {
	readonly title: string;
	readonly description: string;
	readonly linkLabel: string;
	readonly route: "/research/backtests" | "/research/strategies" | "/research/experiments/new";
};

const CREATE_OVERLAYS: Readonly<Record<"new-backtest" | "new-strategy" | "new-experiment", OverlayCopy>> = {
	"new-backtest": {
		title: "新建回测",
		description: "从已持久化策略版本进入回测工作台；运行参数和数据范围将在下一步确认。",
		linkLabel: "进入回测工作台",
		route: "/research/backtests",
	},
	"new-strategy": {
		title: "新建策略",
		description: "先从策略目录选择基线或进入 Studio；此处不会静默创建草稿。",
		linkLabel: "进入策略目录",
		route: "/research/strategies",
	},
	"new-experiment": {
		title: "新建实验",
		description: "进入实验配置并完成只读 preflight，确认计划 hash 后才会正式排队。",
		linkLabel: "进入实验配置",
		route: "/research/experiments/new",
	},
};

function CreateOverlay({ id }: { readonly id: keyof typeof CREATE_OVERLAYS }) {
	const copy = CREATE_OVERLAYS[id];
	return (
		<>
			<SheetHeader>
				<SheetTitle>{copy.title}</SheetTitle>
				<SheetDescription id={`research-${id}-description`}>{copy.description}</SheetDescription>
			</SheetHeader>
			<div className="rounded-(--radius-md) border border-(--color-border-subtle) bg-(--color-surface-panel-base) p-3 text-xs text-(--color-foreground-secondary)">
				所有研究输入继续使用明确的 snapshot、时间窗口和持久化对象身份；页面不会代替后端补默认值。
			</div>
			<SheetFooter className="mt-auto">
				<Link
					to={copy.route}
					className="rounded-(--radius-sm) bg-(--brand-accent) px-3 py-2 text-center text-xs font-medium text-(--brand-accent-fg)"
				>
					{copy.linkLabel}
				</Link>
			</SheetFooter>
		</>
	);
}

export function ResearchOverlays({
	active,
	onClose,
	experiment,
	review,
}: {
	readonly active: ResearchOverlayId | null;
	readonly onClose: () => void;
	readonly experiment: ExperimentListItem | null;
	readonly review: ReviewQueueEntry | null;
}) {
	const title =
		active && active in CREATE_OVERLAYS
			? CREATE_OVERLAYS[active as keyof typeof CREATE_OVERLAYS].title
			: active === "run-detail"
				? "运行详情"
				: "审查操作";

	return (
		<Sheet open={active !== null} onOpenChange={(open) => !open && onClose()}>
			<SheetContent
				showClose={false}
				aria-describedby={`research-${active ?? "closed"}-description`}
				className="gap-4 p-5"
			>
				<SheetClose aria-label={`关闭${title}`} />
				{active && active in CREATE_OVERLAYS ? (
					<CreateOverlay id={active as keyof typeof CREATE_OVERLAYS} />
				) : active === "run-detail" ? (
					<>
						<SheetHeader>
							<SheetTitle>运行详情</SheetTitle>
							<SheetDescription id="research-run-detail-description">持久化实验的当前服务端状态。</SheetDescription>
						</SheetHeader>
						{experiment && (
							<div className="space-y-2 rounded-(--radius-md) border border-(--color-border-subtle) p-3 text-sm">
								<p className="font-data font-medium">{experiment.experimentId}</p>
								<p className="text-(--color-foreground-secondary)">
									{experiment.status} · {experiment.stage}
								</p>
								<p className="font-data text-xs text-(--color-foreground-tertiary)">revision {experiment.revision}</p>
							</div>
						)}
						<SheetFooter className="mt-auto">
							{experiment && (
								<Link
									to="/research/experiments/$id"
									params={{ id: experiment.experimentId }}
									className="rounded-(--radius-sm) bg-(--brand-accent) px-3 py-2 text-center text-xs font-medium text-(--brand-accent-fg)"
								>
									打开完整实验
								</Link>
							)}
						</SheetFooter>
					</>
				) : (
					<>
						<SheetHeader>
							<SheetTitle>审查操作</SheetTitle>
							<SheetDescription id="research-review-action-description">
								先核对完整 review packet、hard gates 与证据 hash，再进入治理动作。
							</SheetDescription>
						</SheetHeader>
						{review && (
							<div className="space-y-2 rounded-(--radius-md) border border-(--color-border-subtle) p-3 text-sm">
								<p className="font-data font-medium">
									{review.strategyId} · v{review.version}
								</p>
								<p className="text-(--color-foreground-secondary)">
									{review.state} · {review.reviewOutcome}
								</p>
								<p className="truncate font-data text-xs text-(--color-foreground-tertiary)">{review.specHash}</p>
							</div>
						)}
						<SheetFooter className="mt-auto">
							{review?.experimentId && (
								<Link
									to="/research/reviews/$id"
									params={{ id: review.experimentId }}
									search={{ strategyId: review.strategyId, version: review.version }}
									className="rounded-(--radius-sm) bg-(--brand-accent) px-3 py-2 text-center text-xs font-medium text-(--brand-accent-fg)"
								>
									打开审查详情
								</Link>
							)}
						</SheetFooter>
					</>
				)}
			</SheetContent>
		</Sheet>
	);
}
