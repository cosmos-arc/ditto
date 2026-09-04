import { ApiError } from "@/lib/api-client";
import { useStrategyEvents } from "../hooks/use-strategy-events";

interface StrategyGovernanceAuditProps {
	readonly strategyId: string;
	readonly currentPacketBundleHash?: string;
	readonly pageSize?: number;
}

function errorText(error: Error): string {
	return error instanceof ApiError
		? `${error.status} ${error.errorCode ?? "STRATEGY_EVENTS_ERROR"}: ${error.message}`
		: error.message;
}

export function StrategyGovernanceAudit({
	strategyId,
	currentPacketBundleHash,
	pageSize = 50,
}: StrategyGovernanceAuditProps) {
	const query = useStrategyEvents(strategyId, pageSize);
	const events = query.data?.pages.flat() ?? [];

	return (
		<section aria-label="Governance Audit" className="flex flex-col gap-2 border-t border-(--color-border-subtle) pt-3">
			<div className="flex flex-wrap items-center justify-between gap-2">
				<h2 className="text-sm font-semibold">Governance Audit</h2>
				{currentPacketBundleHash && (
					<code className="font-data text-xs break-all" title={currentPacketBundleHash}>
						current packet {currentPacketBundleHash}
					</code>
				)}
			</div>
			{currentPacketBundleHash && (
				<p className="text-xs text-(--color-foreground-tertiary)">
					Current packet hash is adjacent context only; the event row itself has no persisted bundle association.
				</p>
			)}
			{query.error && (
				<div className="flex flex-col gap-1 text-xs text-(--color-led-danger)">
					<p role="alert">{errorText(query.error)}</p>
					<button type="button" className="self-start underline" onClick={() => void query.refetch()}>
						重试治理事件
					</button>
				</div>
			)}
			<div className="divide-y divide-(--color-border-subtle)">
				{events.map((event) => (
					<article
						key={event.eventId}
						data-testid={`governance-event-${event.eventId}`}
						className="grid gap-1 py-2 text-xs sm:grid-cols-[9rem_1fr_auto]"
					>
						<div className="font-data">
							<p>{event.eventId}</p>
							<time dateTime={event.occurredAt}>{event.occurredAt}</time>
						</div>
						<div>
							<p>
								{event.eventType} · {event.kind} · target v{event.targetVersion}
							</p>
							<p className="text-(--color-foreground-tertiary)">{event.reason}</p>
						</div>
						<span>{event.actor}</span>
					</article>
				))}
			</div>
			{query.hasNextPage && (
				<button
					type="button"
					onClick={() => void query.fetchNextPage()}
					disabled={query.isFetchingNextPage}
					className="self-start underline text-xs"
				>
					加载更多治理事件
				</button>
			)}
		</section>
	);
}
