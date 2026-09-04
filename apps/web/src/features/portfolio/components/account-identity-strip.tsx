type AccountIdentityKind = "model" | "paper" | "manual";

const KIND_COPY: Record<
	AccountIdentityKind,
	{ readonly label: string; readonly boundary: string; readonly tone: string }
> = {
	model: {
		label: "MODEL 目标组合",
		boundary: "版本化目标，不接受成交或现金流水",
		tone: "border-(--color-accent-primary) text-(--color-accent-primary)",
	},
	paper: {
		label: "PAPER 模拟账户",
		boundary: "由 Ditto 模拟撮合，不连接券商下单",
		tone: "border-(--color-risk-warning-fg) text-(--color-risk-warning-fg)",
	},
	manual: {
		label: "MANUAL 手工实际账户",
		boundary: "只记录用户确认的实际账户事实",
		tone: "border-(--color-status-healthy-fg) text-(--color-status-healthy-fg)",
	},
};

export function AccountIdentityStrip({
	kind,
	accountId,
	accountName,
}: {
	readonly kind: AccountIdentityKind;
	readonly accountId?: string;
	readonly accountName?: string;
}) {
	const copy = KIND_COPY[kind];
	return (
		<section
			aria-label="组合身份"
			data-account-kind={kind}
			className="flex min-h-12 flex-wrap items-center gap-x-3 gap-y-1 border-b border-(--color-border-subtle) bg-(--color-surface-strip) px-4 py-2"
		>
			<span className={`rounded-full border px-2 py-0.5 font-data text-xs font-semibold tracking-wide ${copy.tone}`}>
				{copy.label}
			</span>
			{accountId && <span className="font-data text-xs text-(--color-foreground)">{accountId}</span>}
			{accountName && <span className="text-xs text-(--color-foreground-secondary)">{accountName}</span>}
			<span className="text-xs text-(--color-foreground-tertiary)">{copy.boundary}</span>
		</section>
	);
}
