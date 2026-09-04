import type { FormEvent } from "react";
import { useMemo, useState } from "react";
import { StatusBadge } from "@/components/status/status-badge/status-badge";
import { Button } from "@/components/ui/button";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { CatalogLayout, Panel, PanelBody, PanelHeader } from "@/features/shell";
import { ApiError } from "@/lib/api-client";
import type { UniverseDefinition } from "../api/universes";
import { useUniverseCommands, useUniverseMembers, useUniverses } from "../hooks";

const FIELD_CLASS =
	"h-9 w-full rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-app) px-3 text-xs outline-none focus:border-(--color-border-strong)";
const SELECT_CLASS =
	"h-9 w-28 rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-app) px-3 text-xs outline-none focus:border-(--color-border-strong)";
const TEXTAREA_CLASS = `${FIELD_CLASS} h-24 resize-none py-2`;

function typedError(error: Error, fallbackCode: string): string {
	return error instanceof ApiError
		? `${error.status} ${error.errorCode ?? fallbackCode}: ${error.message}`
		: error.message;
}

function parseMembers(value: FormDataEntryValue | null): string[] | undefined {
	const members = String(value ?? "")
		.split(/[\s,]+/u)
		.map((item) => item.trim())
		.filter(Boolean);
	return members.length > 0 ? members : undefined;
}

function CreateUniverseSheet({
	onCreated,
	onOpenChange,
	open,
}: {
	readonly onCreated: (universeId: string) => void;
	readonly onOpenChange: (open: boolean) => void;
	readonly open: boolean;
}) {
	const command = useUniverseCommands().create;
	async function submit(event: FormEvent<HTMLFormElement>) {
		event.preventDefault();
		const data = new FormData(event.currentTarget);
		const universeId = String(data.get("universeId") ?? "").trim();
		await command.mutateAsync({
			universeId,
			name: String(data.get("name") ?? "").trim(),
			description: String(data.get("description") ?? "").trim(),
		});
		onCreated(universeId);
		onOpenChange(false);
	}
	return (
		<Sheet
			open={open}
			onOpenChange={(next) => {
				if (!next) command.reset();
				onOpenChange(next);
			}}
		>
			<SheetContent side="right" className="p-0">
				<SheetHeader className="border-b border-(--color-border-subtle) px-5 py-4 pr-14">
					<SheetTitle>新建股票池</SheetTitle>
					<SheetDescription>创建自定义定义；成员可在创建后用显式生效日维护。</SheetDescription>
				</SheetHeader>
				<form onSubmit={(event) => void submit(event)} className="flex min-h-0 flex-1 flex-col">
					<div className="flex-1 space-y-4 overflow-y-auto p-5">
						<label className="block space-y-1.5 text-xs">
							<span>Universe ID</span>
							<input
								required
								name="universeId"
								aria-label="Universe ID"
								className={FIELD_CLASS}
								placeholder="etf_core"
							/>
						</label>
						<label className="block space-y-1.5 text-xs">
							<span>股票池名称</span>
							<input required name="name" aria-label="股票池名称" className={FIELD_CLASS} />
						</label>
						<label className="block space-y-1.5 text-xs">
							<span>股票池描述</span>
							<textarea name="description" aria-label="股票池描述" className={TEXTAREA_CLASS} />
						</label>
						{command.error && (
							<p role="alert" className="text-xs text-(--color-led-danger)">
								{typedError(command.error, "UNIVERSE_CREATE_ERROR")}
							</p>
						)}
					</div>
					<SheetFooter className="border-t border-(--color-border-subtle) p-4">
						<Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
							取消
						</Button>
						<Button type="submit" disabled={command.isPending}>
							创建股票池
						</Button>
					</SheetFooter>
				</form>
			</SheetContent>
		</Sheet>
	);
}

function EditUniverseSheet({
	onOpenChange,
	open,
	universe,
}: {
	readonly onOpenChange: (open: boolean) => void;
	readonly open: boolean;
	readonly universe: UniverseDefinition | null;
}) {
	const command = useUniverseCommands().update;
	if (!universe) return null;
	const definition = universe;
	async function submit(event: FormEvent<HTMLFormElement>) {
		event.preventDefault();
		const data = new FormData(event.currentTarget);
		const members = parseMembers(data.get("members"));
		const effectiveDate = String(data.get("effectiveDate") ?? "").trim();
		if (members && !effectiveDate) return;
		await command.mutateAsync({
			universeId: definition.universeId,
			name: String(data.get("name") ?? "").trim(),
			description: String(data.get("description") ?? "").trim(),
			effectiveDate: effectiveDate || undefined,
			members,
		});
		onOpenChange(false);
	}
	return (
		<Sheet
			open={open}
			onOpenChange={(next) => {
				if (!next) command.reset();
				onOpenChange(next);
			}}
		>
			<SheetContent side="right" className="p-0">
				<SheetHeader className="border-b border-(--color-border-subtle) px-5 py-4 pr-14">
					<SheetTitle>编辑 {universe.universeId}</SheetTitle>
					<SheetDescription>定义字段直接更新；只有提供成员时才要求显式生效日期。</SheetDescription>
				</SheetHeader>
				<form onSubmit={(event) => void submit(event)} className="flex min-h-0 flex-1 flex-col">
					<div className="flex-1 space-y-4 overflow-y-auto p-5">
						<label className="block space-y-1.5 text-xs">
							<span>股票池名称</span>
							<input
								required
								name="name"
								aria-label="股票池名称"
								className={FIELD_CLASS}
								defaultValue={universe.name}
							/>
						</label>
						<label className="block space-y-1.5 text-xs">
							<span>股票池描述</span>
							<textarea
								name="description"
								aria-label="股票池描述"
								className={TEXTAREA_CLASS}
								defaultValue={universe.description}
							/>
						</label>
						<div className="border-t border-(--color-border-subtle) pt-4">
							<p className="text-xs font-medium text-(--color-foreground)">可选成员修订</p>
							<p className="mt-1 text-xs text-(--color-foreground-tertiary)">
								成员 ID 用换行或逗号分隔；修订必须绑定 effective date。
							</p>
						</div>
						<label className="block space-y-1.5 text-xs">
							<span>生效日期</span>
							<input type="date" name="effectiveDate" aria-label="成员修订生效日期" className={FIELD_CLASS} />
						</label>
						<label className="block space-y-1.5 text-xs">
							<span>成员 Instrument IDs</span>
							<textarea name="members" aria-label="成员 Instrument IDs" className={TEXTAREA_CLASS} />
						</label>
						{command.error && (
							<p role="alert" className="text-xs text-(--color-led-danger)">
								{typedError(command.error, "UNIVERSE_UPDATE_ERROR")}
							</p>
						)}
					</div>
					<SheetFooter className="border-t border-(--color-border-subtle) p-4">
						<Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
							取消
						</Button>
						<Button type="submit" disabled={command.isPending}>
							保存股票池
						</Button>
					</SheetFooter>
				</form>
			</SheetContent>
		</Sheet>
	);
}

function DeleteUniverseDialog({
	onDeleted,
	onOpenChange,
	open,
	universe,
}: {
	readonly onDeleted: () => void;
	readonly onOpenChange: (open: boolean) => void;
	readonly open: boolean;
	readonly universe: UniverseDefinition | null;
}) {
	const command = useUniverseCommands().remove;
	if (!universe) return null;
	const definition = universe;
	async function remove() {
		await command.mutateAsync(definition.universeId);
		onDeleted();
		onOpenChange(false);
	}
	return (
		<Dialog
			open={open}
			onOpenChange={(next) => {
				if (!next) command.reset();
				onOpenChange(next);
			}}
		>
			<DialogContent>
				<DialogHeader>
					<DialogTitle>删除股票池</DialogTitle>
					<DialogDescription>将永久删除自定义定义 {universe.universeId}。预设定义不提供此动作。</DialogDescription>
				</DialogHeader>
				{command.error && (
					<p role="alert" className="text-xs text-(--color-led-danger)">
						{typedError(command.error, "UNIVERSE_DELETE_ERROR")}
					</p>
				)}
				<DialogFooter>
					<Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
						取消
					</Button>
					<Button type="button" variant="destructive" disabled={command.isPending} onClick={() => void remove()}>
						确认删除股票池
					</Button>
				</DialogFooter>
			</DialogContent>
		</Dialog>
	);
}

export function UniverseListPage() {
	const query = useUniverses();
	const universes = query.data ?? [];
	const [search, setSearch] = useState("");
	const [type, setType] = useState("all");
	const [selectedId, setSelectedId] = useState<string | null>(null);
	const [membershipScope, setMembershipScope] = useState({ universeId: "", asOf: "" });
	const [createOpen, setCreateOpen] = useState(false);
	const [editOpen, setEditOpen] = useState(false);
	const [deleteOpen, setDeleteOpen] = useState(false);
	const types = useMemo(() => [...new Set(universes.map((row) => row.universeType))].sort(), [universes]);
	const filtered = useMemo(() => {
		const needle = search.trim().toLowerCase();
		return universes.filter(
			(row) =>
				(type === "all" || row.universeType === type) &&
				(!needle || row.universeId.toLowerCase().includes(needle) || row.name.toLowerCase().includes(needle)),
		);
	}, [search, type, universes]);
	const selected = filtered.find((row) => row.universeId === selectedId) ?? filtered[0] ?? null;
	const membershipAsOf = selected?.universeId === membershipScope.universeId ? membershipScope.asOf : "";
	const membersQuery = useUniverseMembers(selected?.universeId ?? "", membershipAsOf);

	return (
		<section aria-label="受控股票池目录" className="h-full min-h-0">
			<CatalogLayout
				className="max-[899px]:grid-cols-1 max-[899px]:grid-rows-[auto_1fr] max-[899px]:[grid-template-areas:'toolbar''main']"
				toolbar={
					<div className="flex h-[42px] items-center gap-3 border-b border-(--color-border-subtle) bg-(--color-surface-strip) px-4">
						<div className="min-w-0">
							<p className="text-sm font-medium text-(--color-foreground)">股票池目录</p>
							<p className="hidden text-xs text-(--color-foreground-tertiary) 2xl:block">
								definition · source · PIT membership
							</p>
						</div>
						<label className="ml-auto min-w-44 max-w-64 flex-1">
							<span className="sr-only">搜索股票池</span>
							<input
								type="search"
								aria-label="搜索股票池"
								value={search}
								onChange={(event) => setSearch(event.currentTarget.value)}
								placeholder="id / name"
								className={FIELD_CLASS}
							/>
						</label>
						<select
							aria-label="按类型筛选股票池"
							value={type}
							onChange={(event) => setType(event.currentTarget.value)}
							className={SELECT_CLASS}
						>
							<option value="all">全部类型</option>
							{types.map((value) => (
								<option key={value} value={value}>
									{value}
								</option>
							))}
						</select>
						<Button size="sm" onClick={() => setCreateOpen(true)}>
							新建股票池
						</Button>
					</div>
				}
				main={
					<Panel className="m-3 h-[calc(100%-1.5rem)]">
						<PanelHeader
							title="Universes"
							count={filtered.length}
							actions={
								<span className="font-data text-xs text-(--color-foreground-tertiary)">
									{universes.filter((row) => row.universeType === "custom").length} CUSTOM
								</span>
							}
						/>
						<PanelBody className="p-0">
							<div className="grid grid-cols-[minmax(11rem,1fr)_minmax(11rem,1.2fr)_7rem_minmax(10rem,1fr)] border-b border-(--color-border-subtle) bg-(--color-surface-strip) px-3 py-2 text-xs uppercase tracking-[0.08em] text-(--color-foreground-tertiary)">
								<span>ID</span>
								<span>Name</span>
								<span>Type</span>
								<span>Source</span>
							</div>
							{query.error ? (
								<div className="p-4 text-xs">
									<p role="alert" className="text-(--color-led-danger)">
										{typedError(query.error, "UNIVERSE_CATALOG_ERROR")}
									</p>
									<Button size="sm" variant="outline" className="mt-3" onClick={() => void query.refetch()}>
										重试股票池目录
									</Button>
								</div>
							) : query.isLoading ? (
								<p className="p-4 text-xs text-(--color-foreground-tertiary)">正在加载股票池定义…</p>
							) : filtered.length === 0 ? (
								<p className="p-4 text-xs text-(--color-foreground-tertiary)">当前筛选下没有股票池。</p>
							) : (
								<div className="divide-y divide-(--color-border-subtle)">
									{filtered.map((row) => {
										const active = selected?.universeId === row.universeId;
										return (
											<button
												key={row.universeId}
												type="button"
												aria-label={`选择股票池 ${row.universeId}`}
												aria-pressed={active}
												onClick={() => setSelectedId(row.universeId)}
												className={`grid w-full grid-cols-[minmax(11rem,1fr)_minmax(11rem,1.2fr)_7rem_minmax(10rem,1fr)] items-center px-3 py-3 text-left text-xs transition-colors ${active ? "bg-[color-mix(in_oklch,var(--color-accent)_8%,transparent)]" : "hover:bg-(--color-interaction-hover-subtle-bg)"}`}
											>
												<span className="truncate font-data font-medium text-(--color-foreground)">
													{row.universeId}
												</span>
												<span className="truncate text-(--color-foreground-secondary)">{row.name}</span>
												<StatusBadge
													label={row.universeType}
													variant={row.universeType === "custom" ? "warning" : "idle"}
													size="sm"
												/>
												<span className="truncate font-data text-xs text-(--color-foreground-tertiary)">
													{row.sourceRef || "未发布"}
												</span>
											</button>
										);
									})}
								</div>
							)}
						</PanelBody>
					</Panel>
				}
				detail={
					<aside
						aria-label="股票池详情"
						className="h-full border-l border-(--color-border-subtle) bg-(--color-surface-1) max-[899px]:hidden"
					>
						<div className="flex h-10 items-center justify-between border-b border-(--color-border-subtle) px-4">
							<p className="text-xs font-medium">Definition & members</p>
							<span className="font-data text-xs text-(--color-foreground-tertiary)">PIT</span>
						</div>
						<div className="h-[calc(100%-2.5rem)] overflow-y-auto p-(--density-panel-padding)">
							{selected ? (
								<div className="space-y-4">
									<div>
										<h2 className="font-data text-base font-semibold">{selected.universeId}</h2>
										<p className="mt-1 text-xs text-(--color-foreground-secondary)">{selected.name}</p>
									</div>
									<dl className="grid grid-cols-[6rem_1fr] gap-x-3 gap-y-2 text-xs">
										<dt className="text-(--color-foreground-tertiary)">Type</dt>
										<dd className="font-data">{selected.universeType}</dd>
										<dt className="text-(--color-foreground-tertiary)">Source</dt>
										<dd className="break-all font-data">{selected.sourceRef || "未发布"}</dd>
										<dt className="text-(--color-foreground-tertiary)">Description</dt>
										<dd>{selected.description || "未提供"}</dd>
									</dl>
									<div className="border-t border-(--color-border-subtle) pt-4">
										<label className="block space-y-1.5 text-xs">
											<span>成分 as-of</span>
											<input
												type="date"
												aria-label="股票池成分 as-of 日期"
												value={membershipAsOf}
												onChange={(event) =>
													setMembershipScope({ universeId: selected.universeId, asOf: event.currentTarget.value })
												}
												className={FIELD_CLASS}
											/>
										</label>
										{!membershipAsOf ? (
											<p className="mt-3 text-xs text-(--color-foreground-tertiary)">
												选择 as-of 日期后读取成分；未绑定时不会回退最新成员。
											</p>
										) : membersQuery.isLoading ? (
											<p className="mt-3 text-xs text-(--color-foreground-tertiary)">正在读取 {membershipAsOf} 成分…</p>
										) : membersQuery.error ? (
											<div className="mt-3">
												<p role="alert" className="text-xs text-(--color-led-danger)">
													{typedError(membersQuery.error, "UNIVERSE_MEMBERS_ERROR")}
												</p>
												<Button
													size="sm"
													variant="outline"
													className="mt-2"
													onClick={() => void membersQuery.refetch()}
												>
													重试股票池成分
												</Button>
											</div>
										) : (
											<div className="mt-3">
												<p className="font-data text-xs text-(--color-foreground-tertiary)">
													{membersQuery.data?.length ?? 0} MEMBERS @ {membershipAsOf}
												</p>
												<div className="mt-2 max-h-48 space-y-1 overflow-y-auto">
													{membersQuery.data?.length ? (
														membersQuery.data.map((member) => (
															<p
																key={member.instrumentId}
																className="rounded-(--radius-sm) bg-(--color-surface-strip) px-2 py-1.5 font-data text-xs"
															>
																Instrument #{member.instrumentId}
															</p>
														))
													) : (
														<p className="text-xs text-(--color-foreground-tertiary)">该日期没有可见成员。</p>
													)}
												</div>
											</div>
										)}
										<p className="mt-3 text-xs leading-4 text-(--color-foreground-tertiary)">
											当前公共 API 仅声明有效日期，不返回 knowledge cutoff 或 source
											snapshot；此列表不作为交易决策证据。
										</p>
									</div>
									{selected.universeType === "custom" && (
										<div className="grid grid-cols-2 gap-2 border-t border-(--color-border-subtle) pt-4">
											<Button size="sm" variant="outline" onClick={() => setEditOpen(true)}>
												编辑股票池
											</Button>
											<Button size="sm" variant="outline" onClick={() => setDeleteOpen(true)}>
												删除股票池
											</Button>
										</div>
									)}
								</div>
							) : (
								<p className="text-xs text-(--color-foreground-tertiary)">选择定义以查看详情。</p>
							)}
						</div>
					</aside>
				}
			/>
			<CreateUniverseSheet open={createOpen} onOpenChange={setCreateOpen} onCreated={setSelectedId} />
			<EditUniverseSheet
				key={selected?.universeId ?? "none"}
				open={editOpen}
				onOpenChange={setEditOpen}
				universe={selected}
			/>
			<DeleteUniverseDialog
				open={deleteOpen}
				onOpenChange={setDeleteOpen}
				universe={selected}
				onDeleted={() => setSelectedId(null)}
			/>
		</section>
	);
}
