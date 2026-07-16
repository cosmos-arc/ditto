import { cn } from "@/lib/utils";

const numberFormatter = new Intl.NumberFormat("en-US", {
	maximumFractionDigits: 2,
});

function formatNumeric(value: number): string {
	return numberFormatter.format(value);
}

interface NumericCellProps {
	readonly value: number;
	readonly className?: string;
}

function NumericCell({ value, className }: NumericCellProps) {
	return (
		<span
			data-slot="numeric-cell"
			data-testid="numeric-cell-root"
			className={cn(
				"inline-block text-right tabular-nums",
				"[font-family:var(--font-data)]",
				"[font-feature-settings:'tnum'_1]",
				className,
			)}
		>
			{formatNumeric(value)}
		</span>
	);
}

export type { NumericCellProps };
export { NumericCell };
