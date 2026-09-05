import { StatusDot } from "@/components/status";
import { cn } from "@/lib/utils";

const SEVERITY_DOT_MAP = {
	critical: "critical" as const,
	warning: "degraded" as const,
	info: "info" as const,
};

interface AlertRowProps extends React.HTMLAttributes<HTMLElement> {
	readonly severity: "critical" | "warning" | "info";
	readonly title: string;
	readonly time?: string;
	readonly onClick?: () => void;
}

function AlertRow({ severity, title, time, onClick, className, ...props }: AlertRowProps) {
	const dotVariant = SEVERITY_DOT_MAP[severity];
	const content = (
		<>
			<StatusDot
				variant={dotVariant}
				className={severity === "critical" ? "animate-[dot-critical-pulse_2s_ease-in-out_infinite]" : undefined}
			/>

			<span className="min-w-0 flex-1 truncate text-[var(--font-size-12)] text-(--color-foreground-primary)">
				{title}
			</span>

			{time && (
				<span className="shrink-0 tabular-nums text-[var(--font-size-12)] text-(--color-foreground-tertiary)">
					{time}
				</span>
			)}
		</>
	);
	const rowClassName = cn(
		"flex w-full items-center gap-2 border-b border-(--color-border-subtle) last:border-b-0 py-[var(--density-cell-padding-y)] px-3 text-left transition-colors duration-120 hover:bg-(--color-surface-2)",
		onClick && "cursor-pointer",
		className,
	);

	if (onClick) {
		return (
			<button
				type="button"
				data-slot="alert-row"
				data-severity={severity}
				data-testid="alert-row"
				className={rowClassName}
				onClick={onClick}
				{...props}
			>
				{content}
			</button>
		);
	}

	return (
		<div data-slot="alert-row" data-severity={severity} data-testid="alert-row" className={rowClassName} {...props}>
			{content}
		</div>
	);
}

export type { AlertRowProps };
export { AlertRow };
