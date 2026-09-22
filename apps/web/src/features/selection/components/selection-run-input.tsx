import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { toAdmissionView } from "../admission";
import { assessSelectionAdmission, type CreateSelectionRunBody, resolveSelectionUniverse } from "../api";
import { SelectionAdmission } from "./selection-admission";

const STORAGE_KEY = "ditto.selection-run-input.v1";

function parseRunInput(value: string): CreateSelectionRunBody {
	const parsed: unknown = JSON.parse(value);
	if (typeof parsed !== "object" || parsed === null || !("selection_spec" in parsed)) {
		throw new Error("输入必须包含 selection_spec");
	}
	const spec = Reflect.get(parsed, "selection_spec");
	if (typeof spec !== "object" || spec === null || typeof Reflect.get(spec, "spec_id") !== "string") {
		throw new Error("selection_spec.spec_id 必须是字符串");
	}
	return parsed as CreateSelectionRunBody;
}

export function readSavedSelectionInput(): string {
	return localStorage.getItem(STORAGE_KEY) ?? "";
}

export function SelectionRunInput({
	busy,
	onRun,
	onSaved,
}: {
	readonly busy: boolean;
	readonly onRun: (input: CreateSelectionRunBody) => void;
	readonly onSaved: (input: CreateSelectionRunBody) => void;
}) {
	const [value, setValue] = useState(readSavedSelectionInput);
	const [message, setMessage] = useState<string | null>(null);
	const [instrument, setInstrument] = useState("");
	const inspection = useMutation({
		mutationFn: async ({ raw, instrument }: { raw: string; instrument: string }) =>
			toAdmissionView(await assessSelectionAdmission(parseRunInput(raw), instrument ? Number(instrument) : undefined)),
	});
	const universe = useMutation({
		mutationFn: (raw: string) => resolveSelectionUniverse(parseRunInput(raw)),
	});
	const historical = universe.variables === value ? universe.data : undefined;
	const currentInspection = inspection.variables?.raw === value && inspection.variables.instrument === instrument;
	let instruments: CreateSelectionRunBody["instruments"] = [];
	try {
		const input = parseRunInput(value);
		if (Array.isArray(input.instruments))
			instruments = input.instruments.filter(
				(item) => item && typeof item.instrument_id === "number" && typeof item.instrument_name === "string",
			);
	} catch {
		/* Incomplete drafts are validated on explicit action. */
	}
	const admission = currentInspection ? inspection.data : undefined;

	function validated(): CreateSelectionRunBody | null {
		try {
			const input = parseRunInput(value);
			setMessage(null);
			return input;
		} catch (error) {
			setMessage(error instanceof Error ? error.message : "运行输入不是有效 JSON");
			return null;
		}
	}

	function save(): void {
		const input = validated();
		if (!input) return;
		localStorage.setItem(STORAGE_KEY, JSON.stringify(input, null, 2));
		setValue(JSON.stringify(input, null, 2));
		setMessage("已保存精确输入草案到本机");
		onSaved(input);
	}

	return (
		<details className="border-b border-(--color-border-subtle) bg-(--color-surface-strip)">
			<summary className="cursor-pointer px-4 py-2 text-xs font-medium text-(--color-foreground-secondary)">
				新建运行 · 导入规范化输入包
			</summary>
			<div className="grid gap-3 px-4 pb-4">
				<p className="max-w-3xl text-xs leading-5 text-(--color-foreground-tertiary)">
					输入包需绑定字段来源、数据区间及历史证券池快照。观察池须保留退市与不可投资证券；服务端会核对完整名单、许可、认证和时点。
				</p>
				<textarea
					aria-label="Selection 输入 JSON"
					className="min-h-40 w-full rounded-(--radius-md) border border-(--color-border-primary) bg-(--color-surface-1) p-3 font-mono text-xs text-(--color-foreground)"
					placeholder='{"as_of":"...","selection_spec":{"spec_id":"..."}}'
					spellCheck={false}
					value={value}
					onChange={(event) => {
						setValue(event.currentTarget.value);
						setInstrument("");
					}}
				/>
				<label className="grid gap-1 text-xs">
					选择证券查看字段资格
					<select
						aria-label="选择证券"
						value={instrument}
						onChange={(event) => setInstrument(event.currentTarget.value)}
						className="rounded-(--radius-md) border border-(--color-border-primary) bg-(--color-surface-1) p-2"
					>
						<option value="">全部输入证券</option>
						{instruments.map((item) => (
							<option key={item.instrument_id} value={item.instrument_id}>
								{item.instrument_name} · {item.instrument_id}
							</option>
						))}
					</select>
				</label>
				{instrument && <p className="text-xs">当前仅检查所选证券的数据资格；执行时服务端仍校验输入包的全部证券。</p>}
				<div className="flex items-center gap-2">
					<Button
						type="button"
						variant="outline"
						disabled={inspection.isPending || !value.trim()}
						onClick={() => {
							if (validated()) inspection.mutate({ raw: value, instrument });
						}}
					>
						{inspection.isPending ? "检查中…" : "检查字段准入"}
					</Button>
					<Button
						type="button"
						variant="outline"
						disabled={universe.isPending || !value.trim()}
						onClick={() => universe.mutate(value)}
					>
						{universe.isPending ? "读取中…" : "查看历史证券池"}
					</Button>
					<Button type="button" variant="outline" onClick={save}>
						校验并保存输入
					</Button>
					<Button
						type="button"
						disabled={busy || value.trim().length === 0 || (!instrument && admission?.allowed === false)}
						onClick={() => {
							const input = validated();
							if (input) onRun(input);
						}}
					>
						{busy ? "运行中…" : "执行 SelectionRun"}
					</Button>
					{message && (
						<span role="status" className="text-xs text-(--color-foreground-tertiary)">
							{message}
						</span>
					)}
				</div>
				{currentInspection && inspection.isError && <p role="alert">{inspection.error.message}</p>}
				{universe.variables === value && universe.isError && <p role="alert">{universe.error.message}</p>}
				{historical && (
					<section aria-label="历史证券池" className="space-y-2 text-xs">
						<p>
							历史观察池 · {historical.asOf} · {historical.members.length} 只证券
						</p>
						<p className="break-all">快照：{historical.snapshotId}</p>
						<p>
							知识截止：{historical.knowledgeCutoff} · 披露截止：{historical.publicationCutoff}
						</p>
						{historical.members.length === 0 ? (
							<p>该时点没有可见证券。</p>
						) : (
							<ul className="max-h-48 overflow-auto">
								{historical.members.map((member) => (
									<li key={member.instrumentId}>
										{member.instrumentId} · {member.investable ? "可投资" : "不可投资"} · {member.reasons}
									</li>
								))}
							</ul>
						)}
					</section>
				)}
				{admission && (
					<SelectionAdmission
						key={`${value}:${instrument}`}
						value={admission}
						scope={instrument ? "所选证券" : "全部输入证券"}
					/>
				)}
			</div>
		</details>
	);
}
