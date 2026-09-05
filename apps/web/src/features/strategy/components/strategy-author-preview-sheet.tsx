import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import type { StrategyAuthorOperation, StrategyAuthorPreview } from "@/types/strategy";

interface StrategyAuthorPreviewSheetProps {
	readonly error: string | null;
	readonly isPending: boolean;
	readonly isStale: boolean;
	readonly onClose: () => void;
	readonly open: boolean;
	readonly preview: StrategyAuthorPreview | null;
}

function StageCard({ title, operation }: { readonly title: string; readonly operation: StrategyAuthorOperation }) {
	return (
		<section className="rounded-(--radius-md) border border-(--color-border-subtle) bg-(--color-surface-2) p-3">
			<div className="flex items-center justify-between gap-3">
				<h3 className="text-xs font-semibold uppercase tracking-[0.14em] text-(--color-foreground)">{title}</h3>
				<span className={operation.valid ? "text-(--color-led-success)" : "text-(--color-led-danger)"}>
					{operation.valid ? "PASS" : "FAIL"}
				</span>
			</div>
			<dl className="mt-2 grid grid-cols-[5rem_minmax(0,1fr)] gap-x-2 gap-y-1 text-[11px]">
				<dt className="text-(--color-foreground-tertiary)">subject</dt>
				<dd className="truncate font-data text-(--color-foreground-secondary)">
					{operation.subjectId}@{operation.subjectVersion}
				</dd>
				<dt className="text-(--color-foreground-tertiary)">payload</dt>
				<dd className="truncate font-data text-(--color-foreground-secondary)">{operation.payloadHash}</dd>
			</dl>
		</section>
	);
}

export function StrategyAuthorPreviewSheet({
	error,
	isPending,
	isStale,
	onClose,
	open,
	preview,
}: StrategyAuthorPreviewSheetProps) {
	return (
		<Sheet open={open} onOpenChange={(isOpen) => !isOpen && onClose()}>
			<SheetContent side="right" aria-label="Author 安全预览" className="p-0 sm:max-w-xl">
				<SheetHeader className="border-b border-(--color-border-subtle) px-5 py-4 pr-14">
					<div className="flex items-center gap-2">
						<SheetTitle>Author 安全预览</SheetTitle>
						<span className="rounded-full border border-(--color-led-warning) px-2 py-0.5 text-xs text-(--color-led-warning)">
							只读预览 · 不可发布
						</span>
					</div>
					<SheetDescription>同一 working copy 的 Draft、Compile、Validate、Diff 与主机断言。</SheetDescription>
				</SheetHeader>
				<div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-5 text-xs">
					{isPending ? (
						<p role="status" className="text-(--color-foreground-tertiary)">
							正在运行 detached Author pipeline…
						</p>
					) : error ? (
						<p
							role="alert"
							className="rounded-(--radius-md) border border-(--color-led-danger) p-3 text-(--color-led-danger)"
						>
							{error}
						</p>
					) : preview ? (
						<>
							<div
								className={`rounded-(--radius-md) border p-3 ${
									preview.valid && !isStale
										? "border-(--color-led-success) bg-(--color-led-success-bg)"
										: "border-(--color-led-warning) bg-(--color-led-warning-bg)"
								}`}
							>
								<p className="font-medium text-(--color-foreground)">
									{isStale ? "预览已过期" : preview.valid ? "全部 Author 检查通过" : "Author 检查未通过"}
								</p>
								<code className="mt-1 block break-all font-data text-[11px] text-(--color-foreground-secondary)">
									{preview.canonicalHash ?? "canonical hash 未认证"}
								</code>
							</div>
							<StageCard title="Draft" operation={preview.draft} />
							<section>
								<h3 className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-(--color-foreground)">
									Compile
								</h3>
								{preview.compile.length > 0 ? (
									<div className="space-y-2">
										{preview.compile.map((operation) => (
											<StageCard
												key={`${operation.subjectId}@${operation.subjectVersion}`}
												title={operation.subjectId}
												operation={operation}
											/>
										))}
									</div>
								) : (
									<p className="text-(--color-foreground-tertiary)">working copy 没有表达式。</p>
								)}
							</section>
							<StageCard title="Validate" operation={preview.validation} />
							<StageCard title="Diff" operation={preview.diff} />
							<section className="rounded-(--radius-md) border border-(--color-border-subtle) p-3">
								<h3 className="text-xs font-semibold uppercase tracking-[0.14em] text-(--color-foreground)">Tests</h3>
								<ul className="mt-2 space-y-2">
									{preview.tests.map((test) => (
										<li key={test.name} className="grid grid-cols-[1fr_auto] gap-3">
											<div>
												<code className="font-data text-(--color-foreground)">{test.name}</code>
												<p className="text-[11px] text-(--color-foreground-tertiary)">{test.detail}</p>
											</div>
											<span className={test.passed ? "text-(--color-led-success)" : "text-(--color-led-danger)"}>
												{test.passed ? "PASS" : "FAIL"}
											</span>
										</li>
									))}
								</ul>
							</section>
						</>
					) : (
						<p className="text-(--color-foreground-tertiary)">点击 Author 预览运行只读 pipeline。</p>
					)}
					<SheetFooter className="mt-auto">
						<Button variant="outline" onClick={onClose}>
							关闭
						</Button>
					</SheetFooter>
				</div>
			</SheetContent>
		</Sheet>
	);
}
