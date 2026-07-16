import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";
import { StatusDot } from "../status-dot";

/** Maps badge variant to StatusDot variant — 利用 8 种独立色最大化视觉区分 */
const DOT_VARIANT_MAP = {
	default: "healthy",
	healthy: "healthy",
	degraded: "degraded",
	warning: "warning",
	critical: "critical",
	live: "live",
	idle: "idle",
	error: "error",
	trade: "live",
	risk: "critical",
	research: "info",
	platform: "idle",
	data: "degraded",
	priority: "error",
	"regime-on": "healthy",
	"regime-off": "idle",
	"regime-mixed": "warning",
	active: "live",
	inactive: "idle",
} as const;

type BadgeVariant = keyof typeof DOT_VARIANT_MAP;

/** Maps badge variant to background color token */
const BG_COLOR_MAP: Record<BadgeVariant, string> = {
	default: "bg-(--color-status-led-healthy)/8",
	healthy: "bg-(--color-status-led-healthy)/8",
	degraded: "bg-(--color-status-led-degraded)/8",
	warning: "bg-(--color-status-led-warning)/8",
	critical: "bg-(--color-status-led-critical)/8",
	live: "bg-(--color-status-led-live)/8",
	idle: "bg-(--color-status-led-idle)/8",
	error: "bg-(--color-status-led-error)/8",
	trade: "bg-(--color-execution-filled)/8",
	risk: "bg-(--color-risk-warning)/8",
	research: "bg-(--color-agent-thinking)/8",
	platform: "bg-(--color-system-healthy)/8",
	data: "bg-(--color-quality-good)/8",
	priority: "bg-(--color-market-up)/8",
	"regime-on": "bg-(--color-system-healthy)/8",
	"regime-off": "bg-(--color-led-idle)/8",
	"regime-mixed": "bg-(--color-risk-warning)/8",
	active: "bg-(--color-led-active)/8",
	inactive: "bg-(--color-led-idle)/8",
};

const sizeClasses = {
	sm: "text-xs gap-1 px-2 py-px rounded-[10px] tracking-[0.2px]",
	md: "text-sm gap-1.5 px-2 py-0.5 rounded-[10px] tracking-[0.2px]",
} as const;

const statusBadgeVariants = cva(
	"inline-flex items-center font-medium",
	{
		variants: {
			size: sizeClasses,
		},
		defaultVariants: {
			size: "md",
		},
	},
);

interface StatusBadgeProps extends VariantProps<typeof statusBadgeVariants> {
	readonly variant?: BadgeVariant;
	readonly label: string;
	readonly className?: string;
}

function StatusBadge({
	variant = "default",
	size = "md",
	label,
	className,
}: StatusBadgeProps) {
	const dotVariant = DOT_VARIANT_MAP[variant];
	const bgClass = BG_COLOR_MAP[variant];

	return (
		<span
			data-slot="status-badge"
			data-variant={variant}
			data-size={size}
			className={cn(statusBadgeVariants({ size }), bgClass, className)}
		>
			<StatusDot variant={dotVariant} size={size} />
			{label}
		</span>
	);
}

export { StatusBadge, statusBadgeVariants };
export type { StatusBadgeProps, BadgeVariant };
