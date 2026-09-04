import { useState } from "react";
import { Button } from "@/components/ui/button";
import type { CreateSelectionRunBody } from "../api";

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
					输入包必须来自已认证 snapshot；这里不会以演示值补齐价格、因子或可交易性事实。
				</p>
				<textarea
					aria-label="Selection 输入 JSON"
					className="min-h-40 w-full rounded-(--radius-md) border border-(--color-border-primary) bg-(--color-surface-1) p-3 font-mono text-xs text-(--color-foreground)"
					placeholder='{"as_of":"...","selection_spec":{"spec_id":"..."}}'
					spellCheck={false}
					value={value}
					onChange={(event) => setValue(event.currentTarget.value)}
				/>
				<div className="flex items-center gap-2">
					<Button type="button" variant="outline" onClick={save}>
						校验并保存输入
					</Button>
					<Button
						type="button"
						disabled={busy || value.trim().length === 0}
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
			</div>
		</details>
	);
}
