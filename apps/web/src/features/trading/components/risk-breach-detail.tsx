interface BreachDetailContentProps {
	readonly breachId: string;
}

function BreachDetailContent({ breachId }: BreachDetailContentProps) {
	return (
		<div className="flex flex-col gap-4">
			<div className="flex items-center justify-between">
				<span className="font-data text-xs text-(--color-foreground-muted)">ID: {breachId}</span>
			</div>
			<p className="text-xs text-(--color-foreground-muted)">
				详细告警信息待接入 API
			</p>
		</div>
	);
}

export { BreachDetailContent };
