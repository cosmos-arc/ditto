interface PlaceholderProps {
	readonly label: string;
}

/**
 * Placeholder -- temporary slot filler for shell layout prototyping.
 * Displays a label with "占位" suffix, centered in a muted style.
 * Will be replaced by real components as features are implemented.
 */
export function Placeholder({ label }: PlaceholderProps) {
	return (
		<div className="flex items-center justify-center p-4 text-sm text-(--color-foreground-tertiary)">
			{label} — 占位
		</div>
	);
}
