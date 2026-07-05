import { StatusBadge } from "@/components/status";

interface PrototypeOnlyEmptyProps {
	readonly domain: string;
}

export function PrototypeOnlyEmpty({ domain }: PrototypeOnlyEmptyProps) {
	return (
		<div
			data-info-level="l1"
			data-info-unit="prototype-only-empty"
			className="flex h-full min-h-[320px] items-center justify-center p-(--density-panel-padding)"
		>
			<div className="flex max-w-xl flex-col gap-3">
				<StatusBadge label="prototype only" variant="idle" size="sm" />
				<div className="flex flex-col gap-1">
					<p className="text-base font-medium text-(--color-foreground-primary)">
						{domain} 仍处于 prototype/MSW 评审态
					</p>
					<p className="text-sm text-(--color-foreground-tertiary)">
						prototype only，请切 VITE_USE_MOCK=true 查看原型数据。
					</p>
				</div>
			</div>
		</div>
	);
}
