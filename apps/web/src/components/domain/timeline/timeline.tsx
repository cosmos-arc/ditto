import { cn } from "@/lib/utils";
import { StatusDot } from "@/components/status";

/* ── Types ── */

interface TimelineItem {
	readonly id: string;
	readonly marker?: "dot" | "event" | "completed" | "failed";
	readonly title: string;
	readonly description?: string;
	readonly time: string;
	readonly status?: "resolved" | "monitoring" | "triggered";
	readonly severity?: "ok" | "warn" | "critical";
}

interface TimelineProps extends React.HTMLAttributes<HTMLDivElement> {
	readonly items: readonly TimelineItem[];
	readonly variant?: "default" | "activity";
}

/* ── Severity → StatusDot mapping ── */

const SEVERITY_DOT_MAP: Record<string, "healthy" | "degraded" | "critical"> = {
	ok: "healthy",
	warn: "degraded",
	critical: "critical",
};

/* ── Status label mapping ── */

const STATUS_LABELS: Record<string, string> = {
	resolved: "已解决",
	monitoring: "监控中",
	triggered: "触发",
};

const STATUS_DOT_MAP: Record<string, "healthy" | "live" | "critical"> = {
	resolved: "healthy",
	monitoring: "live",
	triggered: "critical",
};

/* ── Component ── */

function Timeline({
	items,
	variant = "default",
	className,
	...props
}: TimelineProps) {
	return (
		<div
			data-slot="timeline"
			data-variant={variant}
			className={cn("flex flex-col", className)}
			{...props}
		>
			{items.map((item) => (
				<div
					key={item.id}
					data-slot="timeline-item"
					className="flex gap-2 py-2 px-3 border-b border-(--color-border-subtle) last:border-b-0"
				>
					{/* Time + severity dot */}
					<div className="flex items-center gap-1 min-w-[50px] shrink-0">
						{item.severity && (
							<StatusDot
								variant={SEVERITY_DOT_MAP[item.severity]}
								size="sm"
							/>
						)}
						<span className="font-data text-sm text-(--color-foreground-tertiary) tabular-nums">
							{item.time}
						</span>
					</div>

					{/* Body */}
					<div className="flex flex-col gap-0.5 min-w-0">
						<span className="text-sm text-(--color-foreground-secondary) leading-snug">
							{item.title}
						</span>
						{item.description && (
							<span className="text-xs text-(--color-foreground-tertiary)">
								{item.description}
							</span>
						)}
					</div>

					{/* Status badge */}
					{item.status && (
						<div className="flex items-center gap-1 shrink-0 ml-auto">
							<StatusDot
								variant={STATUS_DOT_MAP[item.status]}
								size="sm"
							/>
							<span className="text-xs text-(--color-foreground-tertiary)">
								{STATUS_LABELS[item.status]}
							</span>
						</div>
					)}
				</div>
			))}
		</div>
	);
}

export { Timeline };
export type { TimelineProps, TimelineItem };
