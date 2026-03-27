import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";
import type { FactorStatus } from "../types";

const statusBadgeVariants = cva(
	"inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-bold",
	{
		variants: {
			status: {
				stable: "border-green-500/20 bg-green-500/10 text-green-500",
				optimal: "border-green-500/20 bg-green-500/10 text-green-500",
				decay: "border-amber-500/20 bg-amber-500/10 text-amber-500",
				failed: "border-red-500/20 bg-red-500/10 text-red-500",
			},
		},
		defaultVariants: {
			status: "stable",
		},
	},
);

interface StatusBadgeProps extends VariantProps<typeof statusBadgeVariants> {
	readonly label: string;
}

export function StatusBadge({ status, label }: StatusBadgeProps) {
	return (
		<span className={cn(statusBadgeVariants({ status }))}>{label}</span>
	);
}

export function getFactorStatusColor(status: FactorStatus): string {
	switch (status) {
		case "optimal":
		case "stable":
			return "text-green-500";
		case "decay":
			return "text-amber-500";
		case "failed":
			return "text-red-500";
	}
}

export function getIcColor(ic: number): string {
	if (ic > 0.02) return "text-green-500";
	if (ic > 0) return "text-amber-500";
	return "text-red-500";
}
