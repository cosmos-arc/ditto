import { Button } from "@/components/ui/button";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogFooter,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";

interface SignalsBatchReviewDialogProps {
	readonly open: boolean;
	readonly onOpenChange: (open: boolean) => void;
	readonly pendingCount: number;
	readonly onStartReview: () => void;
}

export function SignalsBatchReviewDialog({
	open,
	onOpenChange,
	pendingCount,
	onStartReview,
}: SignalsBatchReviewDialogProps) {
	return (
		<Dialog open={open} onOpenChange={onOpenChange}>
			<DialogContent aria-describedby="signals-batch-review-description">
				<DialogHeader>
					<DialogTitle>批量复核</DialogTitle>
					<DialogDescription id="signals-batch-review-description">
						当前共有 {pendingCount}{" "}
						个待处理项。后端未提供批量确认接口，因此这里组织逐条人工复核，不会伪造确认或忽略状态。
					</DialogDescription>
				</DialogHeader>
				<div className="rounded-(--radius-md) border border-(--color-border-subtle) bg-(--color-surface-panel-base) p-4 text-sm text-(--color-foreground-secondary)">
					每一项都需要单独检查信号证据、目标与可执行仓位、风险原因和已有 execution intent。
				</div>
				<DialogFooter>
					<Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
						取消
					</Button>
					<Button type="button" onClick={onStartReview} disabled={pendingCount === 0}>
						开始逐条复核
					</Button>
				</DialogFooter>
			</DialogContent>
		</Dialog>
	);
}
