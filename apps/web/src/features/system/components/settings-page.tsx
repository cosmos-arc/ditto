import type { UseQueryResult } from "@tanstack/react-query";
import { useState } from "react";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { PageActionBar } from "@/components/domain/page-action-overlay";
import { StatusBadge } from "@/components/status";
import { Button } from "@/components/ui/button";
import { OpsConsoleLayout, Panel, PanelBody, PanelHeader } from "@/features/shell";
import type { SystemCatalogAsset } from "../api/system-overview";
import type { SystemAgentCapability, SystemRuntimeStatus } from "../api/system-settings";
import { useSystemSettings } from "../hooks/use-system-settings";
import { type SystemSettingsOverlayId, SystemSettingsOverlays, systemSettingsActions } from "./system-overlays";

function formatTimestamp(value: string | undefined): string {
	if (!value) return "not reported";
	const date = new Date(value);
	return Number.isNaN(date.getTime())
		? value
		: new Intl.DateTimeFormat("zh-CN", {
				month: "2-digit",
				day: "2-digit",
				hour: "2-digit",
				minute: "2-digit",
				hour12: false,
			}).format(date);
}

function message(error: Error | null): string {
	return error?.message ?? "unknown error";
}

function FactRow({
	label,
	mono = false,
	value,
}: {
	readonly label: string;
	readonly mono?: boolean;
	readonly value: string;
}) {
	return (
		<div className="grid grid-cols-[minmax(7rem,0.7fr)_minmax(0,1.3fr)] gap-4 border-t border-(--color-border-subtle) px-3 py-2.5 first:border-0">
			<span className="text-xs text-(--color-foreground-tertiary)">{label}</span>
			<span className={`${mono ? "font-data" : ""} truncate text-right text-xs text-(--color-foreground)`}>
				{value}
			</span>
		</div>
	);
}

function QueryBody<T>({
	children,
	query,
}: {
	readonly children: (data: T) => React.ReactNode;
	readonly query: UseQueryResult<T, Error>;
}) {
	if (query.isLoading) {
		return (
			<PanelBody className="p-3" role="status" aria-label="正在读取服务器配置">
				<LoadingSkeleton variant="panel" rows={4} />
			</PanelBody>
		);
	}
	if (query.isError) {
		return (
			<PanelBody className="p-4">
				<p role="alert" className="text-xs text-(--color-risk-critical-fg)">
					{message(query.error)}
				</p>
				<Button className="mt-3" type="button" variant="outline" size="xs" onClick={() => void query.refetch()}>
					重试
				</Button>
			</PanelBody>
		);
	}
	return <PanelBody>{query.data ? children(query.data) : null}</PanelBody>;
}

function RuntimePanel({ query }: { readonly query: UseQueryResult<SystemRuntimeStatus, Error> }) {
	return (
		<Panel data-info-level="l1" data-info-unit="runtime-identity">
			<PanelHeader
				title="Runtime identity"
				subtitle="GET /api/v1/status"
				actions={
					<StatusBadge
						label={query.data?.status ?? (query.isError ? "unavailable" : "loading")}
						variant={query.data?.status === "running" ? "healthy" : query.isError ? "critical" : "idle"}
						size="sm"
					/>
				}
			/>
			<QueryBody query={query}>
				{(runtime) => (
					<>
						<FactRow label="Version" value={runtime.version} mono />
						<FactRow label="Environment" value={runtime.environment} mono />
						<FactRow label="Log level" value={runtime.observability.level} mono />
						<FactRow label="Structured logs" value={runtime.observability.structured ? "enabled" : "disabled"} />
						<div className="border-t border-(--color-border-subtle) px-3 py-3">
							<p className="mb-2 text-xs text-(--color-foreground-tertiary)">Advertised runtime features</p>
							<div className="flex flex-wrap gap-1.5">
								{runtime.features.map((feature) => (
									<StatusBadge
										key={feature.name}
										label={feature.name}
										variant={feature.enabled ? "healthy" : "idle"}
										size="sm"
									/>
								))}
							</div>
						</div>
					</>
				)}
			</QueryBody>
		</Panel>
	);
}

function CatalogPanel({ query }: { readonly query: UseQueryResult<readonly SystemCatalogAsset[], Error> }) {
	return (
		<Panel data-info-level="l1" data-info-unit="catalog-inventory">
			<PanelHeader
				title="Data catalog"
				subtitle="GET /api/v1/ingestion/catalog/assets"
				actions={<StatusBadge label={`${query.data?.length ?? 0} assets`} variant="idle" size="sm" />}
			/>
			<QueryBody query={query}>
				{(assets) => {
					if (assets.length === 0) {
						return (
							<p role="status" className="p-4 text-sm text-(--color-foreground-secondary)">
								Catalog 未报告任何资产；页面保持空态，不推断数据源连接状态。
							</p>
						);
					}
					const namespaces = [...new Set(assets.map((asset) => asset.namespace))].sort();
					const sources = [...new Set(assets.map((asset) => asset.source))].sort();
					const freshest = assets
						.map((asset) => asset.freshnessAt)
						.sort()
						.at(-1);
					return (
						<>
							<FactRow label="Inventory" value={`${assets.length} catalog assets`} />
							<FactRow label="Namespaces" value={namespaces.join(", ")} mono />
							<FactRow label="Reported sources" value={sources.join(", ")} mono />
							<FactRow label="Latest freshness" value={formatTimestamp(freshest)} mono />
							<div className="border-t border-(--color-border-subtle) px-3 py-3">
								<p className="mb-2 text-xs text-(--color-foreground-tertiary)">Dataset identities</p>
								<div className="flex flex-wrap gap-1.5">
									{assets.slice(0, 8).map((asset) => (
										<code
											key={`${asset.namespace}-${asset.datasetId}`}
											className="rounded-(--radius-sm) bg-(--color-surface-strip) px-2 py-1 font-data text-xs"
										>
											{asset.datasetId}
										</code>
									))}
								</div>
							</div>
						</>
					);
				}}
			</QueryBody>
		</Panel>
	);
}

function AgentPanel({ query }: { readonly query: UseQueryResult<SystemAgentCapability, Error> }) {
	return (
		<Panel data-info-level="l1" data-info-unit="agent-capability">
			<PanelHeader
				title="Agent capability"
				subtitle="GET /api/v1/agent/capabilities"
				actions={
					<StatusBadge
						label={query.data?.runtimeState ?? (query.isError ? "unavailable" : "loading")}
						variant={query.data?.runtimeState === "available" ? "healthy" : query.isError ? "critical" : "warning"}
						size="sm"
					/>
				}
			/>
			<QueryBody query={query}>
				{(agent) => (
					<>
						<FactRow label="Enabled" value={agent.enabled ? "enabled" : "disabled"} />
						<FactRow label="Provider" value={agent.provider ?? "not reported"} mono />
						<FactRow label="Default profile" value={agent.defaultProfile ?? "not reported"} mono />
						<FactRow label="Available profiles" value={agent.availableProfiles.join(", ") || "none reported"} mono />
						<FactRow label="Checked at" value={formatTimestamp(agent.checkedAt)} mono />
						{agent.degradationReason && (
							<p
								role="alert"
								className="border-t border-(--color-border-subtle) px-3 py-3 text-xs text-(--color-risk-warning-fg)"
							>
								{agent.degradationReason}
							</p>
						)}
					</>
				)}
			</QueryBody>
		</Panel>
	);
}

export function SystemSettingsPage() {
	const settings = useSystemSettings();
	const [activeOverlay, setActiveOverlay] = useState<SystemSettingsOverlayId | null>(null);
	const queries = [settings.runtime, settings.assets, settings.agent];
	const isLoading = queries.some((query) => query.isLoading);
	const isRefreshing = queries.some((query) => query.isFetching && query.data !== undefined);
	const unavailableCount = queries.filter((query) => query.isError).length;

	function refresh(): void {
		for (const query of queries) void query.refetch();
	}

	return (
		<>
			<OpsConsoleLayout
				className="[&_[data-slot='detail']]:border-l [&_[data-slot='detail']]:border-(--color-border-subtle) [&_[data-slot='detail']]:bg-(--color-surface-1) [&_[data-slot='health']]:border-b [&_[data-slot='health']]:border-(--color-border-subtle) [&_[data-slot='health']]:bg-(--color-surface-strip)"
				health={
					<div
						className="grid h-[35px] grid-cols-2 divide-x divide-(--color-border-subtle) px-2 sm:grid-cols-4"
						role="status"
						aria-label="平台运行配置摘要"
					>
						{[
							["Runtime", settings.runtime.data?.status ?? (settings.runtime.isError ? "unavailable" : "loading")],
							["Environment", settings.runtime.data?.environment ?? "not reported"],
							["Catalog", settings.assets.data ? `${settings.assets.data.length} assets` : "loading"],
							["Agent", settings.agent.data?.runtimeState ?? (settings.agent.isError ? "unavailable" : "loading")],
						].map(([label, value]) => (
							<div key={label} className="flex min-w-0 items-baseline justify-between gap-2 px-4">
								<span className="text-xs text-(--color-foreground-tertiary)">{label}</span>
								<strong className="truncate font-data text-sm text-(--color-foreground)">{value}</strong>
							</div>
						))}
					</div>
				}
				main={
					<main className="flex h-full min-h-0 flex-col" aria-label="平台设置运行视图">
						<div className="flex min-h-12 flex-wrap items-center gap-3 border-b border-(--color-border-subtle) bg-(--color-surface-strip) px-4 py-2">
							<div className="min-w-0 flex-1">
								<p className="text-sm font-medium text-(--color-foreground)">Server-reported configuration</p>
								<p className="truncate text-xs text-(--color-foreground-tertiary)">
									只读能力清单 · 不展示 secrets · 不推断未公开连接
								</p>
							</div>
							{isRefreshing && <StatusBadge label="refreshing" variant="idle" size="sm" />}
							{unavailableCount > 0 && (
								<StatusBadge label={`${unavailableCount} unavailable`} variant="critical" size="sm" />
							)}
							<Button type="button" variant="outline" size="xs" onClick={refresh}>
								重新读取
							</Button>
							<PageActionBar ariaLabel="平台设置操作" actions={systemSettingsActions} onOpen={setActiveOverlay} />
						</div>
						<div className="min-h-0 flex-1 overflow-y-auto p-(--density-panel-padding)">
							{isLoading && (
								<p className="mb-3 text-xs text-(--color-foreground-tertiary)" role="status">
									正在读取运行时配置证据…
								</p>
							)}
							<div className="grid items-start gap-(--section-gap) xl:grid-cols-2">
								<RuntimePanel query={settings.runtime} />
								<CatalogPanel query={settings.assets} />
								<div className="xl:col-span-2">
									<AgentPanel query={settings.agent} />
								</div>
							</div>
						</div>
					</main>
				}
				detail={
					<aside className="h-full overflow-y-auto" aria-label="设置边界">
						<Panel className="m-3">
							<PanelHeader title="Configuration boundary" subtitle="narrowed scope" />
							<PanelBody className="p-3 text-xs text-(--color-foreground-secondary)">
								<p>当前 API 只公开系统状态、Catalog 资产与 Agent capability。页面据此提供可审计只读视图。</p>
								<div className="mt-3 rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-strip) p-3">
									<p className="font-medium text-(--color-foreground)">未公开的设置面</p>
									<ul className="mt-2 space-y-1.5">
										<li>Manual / Paper runtime configuration</li>
										<li>Notification policy configuration</li>
										<li>Config save / rollback history</li>
									</ul>
								</div>
								<p className="mt-3 text-(--color-foreground-tertiary)">
									这些能力没有公共读写契约，因此不会显示虚假的连接状态、保存按钮或回滚点。
								</p>
							</PanelBody>
						</Panel>

						<Panel className="mx-3 mb-3" data-info-level="l2" data-info-unit="settings-endpoints">
							<PanelHeader title="Evidence endpoints" count={3} />
							<PanelBody>
								{["GET /api/v1/status", "GET /api/v1/ingestion/catalog/assets", "GET /api/v1/agent/capabilities"].map(
									(endpoint) => (
										<code
											key={endpoint}
											className="block border-t border-(--color-border-subtle) px-3 py-2 text-xs first:border-0"
										>
											{endpoint}
										</code>
									),
								)}
							</PanelBody>
						</Panel>
					</aside>
				}
			/>
			<SystemSettingsOverlays
				active={activeOverlay}
				agentState={settings.agent.data?.runtimeState ?? "not reported"}
				assetCount={settings.assets.data?.length ?? 0}
				onClose={() => setActiveOverlay(null)}
				onRefresh={refresh}
				runtimeState={settings.runtime.data?.status ?? "not reported"}
			/>
		</>
	);
}
