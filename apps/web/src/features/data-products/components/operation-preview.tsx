import { useState } from "react";
import { Button } from "@/components/ui/button";

export type DataProductOperation = "bootstrap" | "repair" | "certify" | "promotion" | "revoke";

interface OperationPreviewProps {
	readonly datasetId: string;
	readonly operations: readonly DataProductOperation[];
}

const OPERATION_ARGUMENTS: Readonly<Record<DataProductOperation, string>> = {
	bootstrap: "--start-date <YYYY-MM-DD> --end-date <YYYY-MM-DD>",
	repair: "",
	certify: "--report-id <REPORT_ID> --actor <ACTOR>",
	promotion: "--criterion <CRITERION> --evidence-uri <EVIDENCE_URI> --actor <ACTOR>",
	revoke: "--report-id <REPORT_ID> --actor <ACTOR> --reason <REASON>",
};

function confirmationPhrase(operation: DataProductOperation, datasetId: string): string {
	return `data-product:${operation}:${datasetId}:confirm`;
}

function commandTemplate(operation: DataProductOperation, datasetId: string): string {
	const argumentsTemplate = OPERATION_ARGUMENTS[operation];
	const argumentsSegment = argumentsTemplate ? ` ${argumentsTemplate}` : "";
	return `ditto data-products ${operation} ${datasetId}${argumentsSegment} --confirm ${confirmationPhrase(operation, datasetId)}`;
}

export function OperationPreview({ datasetId, operations }: OperationPreviewProps) {
	const [operation, setOperation] = useState<DataProductOperation>();
	const [confirmation, setConfirmation] = useState("");
	const [confirmedCommand, setConfirmedCommand] = useState<string>();
	const phrase = operation ? confirmationPhrase(operation, datasetId) : "";

	function preview(nextOperation: DataProductOperation): void {
		setOperation(nextOperation);
		setConfirmation("");
		setConfirmedCommand(undefined);
	}

	function confirm(): void {
		if (!operation || confirmation !== phrase) return;
		setConfirmedCommand(commandTemplate(operation, datasetId));
	}

	return (
		<div className="flex flex-col gap-3">
			<div className="flex flex-wrap gap-2">
				{operations.map((item) => (
					<Button
						key={item}
						type="button"
						variant={item === "revoke" ? "destructive" : "outline"}
						size="xs"
						onClick={() => preview(item)}
					>
						预览 {item}
					</Button>
				))}
			</div>
			{operation && (
				<section
					aria-label={`${operation} 操作预览`}
					className="rounded-(--radius-sm) border border-(--color-border-default) bg-(--color-surface-muted) p-3"
				>
					<p className="text-xs font-medium text-(--color-foreground)">仅生成本地操作指令，不会从浏览器直接执行</p>
					<p className="mt-2 text-xs text-(--color-foreground-tertiary)">确认短语</p>
					<code className="mt-1 block break-all font-code text-xs text-(--color-risk-high-fg)">{phrase}</code>
					<label className="mt-3 block text-xs text-(--color-foreground-secondary)" htmlFor="data-product-confirmation">
						输入完整确认短语
					</label>
					<input
						id="data-product-confirmation"
						value={confirmation}
						onChange={(event) => setConfirmation(event.currentTarget.value)}
						autoComplete="off"
						spellCheck={false}
						className="mt-1 h-(--height-input) w-full rounded-(--radius-sm) border border-(--color-border-default) bg-(--color-surface-panel-base) px-2 font-code text-xs text-(--color-foreground) outline-none focus-visible:border-(--color-focus-border) focus-visible:ring-3 focus-visible:ring-(--color-focus-ring)"
					/>
					<Button className="mt-3" type="button" size="sm" disabled={confirmation !== phrase} onClick={confirm}>
						生成已确认指令
					</Button>
				</section>
			)}
			{confirmedCommand && operation && (
				<div
					role="status"
					className="rounded-(--radius-sm) border border-(--color-border-warning) bg-(--color-risk-medium-bg) p-3"
				>
					<p className="text-xs font-medium text-(--color-risk-medium-fg)">
						已确认 {operation}，请补齐占位参数并在受控终端执行
					</p>
					<code className="mt-2 block break-all font-code text-xs text-(--color-foreground)">{confirmedCommand}</code>
				</div>
			)}
		</div>
	);
}
