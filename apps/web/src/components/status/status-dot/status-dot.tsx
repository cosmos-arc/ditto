import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const sizeClasses = {
	sm: "w-[6px] h-[6px]",
	md: "w-[8px] h-[8px]",
	lg: "w-[10px] h-[10px]",
} as const;

const variantClasses = {
	healthy: "bg-(--color-status-led-healthy)",
	degraded: "bg-(--color-status-led-degraded)",
	warning: "bg-(--color-status-led-warning)",
	critical: "bg-(--color-status-led-critical)",
	live: "bg-(--color-status-led-live)",
	idle: "bg-(--color-status-led-idle)",
	error: "bg-(--color-status-led-error)",
	info: "bg-(--color-status-led-info)",
} as const;

const statusDotVariants = cva("inline-block shrink-0 rounded-full", {
	variants: {
		size: sizeClasses,
		variant: variantClasses,
	},
	defaultVariants: {
		size: "md",
		variant: "healthy",
	},
});

interface StatusDotProps
	extends VariantProps<typeof statusDotVariants> {
	readonly pulse?: boolean;
	readonly className?: string;
}

function StatusDot({
	size = "md",
	variant = "healthy",
	pulse = false,
	className,
}: StatusDotProps) {
	const isLivePulse = variant === "live" && pulse;

	return (
		<span
			data-slot="status-dot"
			data-variant={variant}
			data-size={size}
			className={cn(
				statusDotVariants({ size, variant }),
				isLivePulse && "animate-[dot-pulse_2s_ease-in-out_infinite]",
				className,
			)}
		/>
	);
}

export { StatusDot, statusDotVariants };
