import { ContextSection } from "@/components/domain/context-section";
import { StatusBadge } from "@/components/status/status-badge/status-badge";
import type { SpecValidation } from "@/types/strategy";

interface ValidationPanelProps {
	/** validate 端点结果（null = 尚未校验）。 */
	readonly validation: SpecValidation | null;
	readonly isValidating: boolean;
	readonly isStale?: boolean;
}

/**
 * Spec 校验面板（保存前 pre-save validation）。
 *
 * 展示 `POST /v1/strategies/{id}/versions/{v}/validate` 的 canonical hash、合法性、
 * 变更检测与错误列表。后端对非法 candidate 返 200 + `valid=false`（不抛），UI 如实
 * 反射，绝不自造通过。
 */
export function ValidationPanel({ validation, isValidating, isStale = false }: ValidationPanelProps) {
	return (
		<ContextSection title="Spec 校验">
			{isValidating ? (
				<p className="text-sm text-(--color-foreground-tertiary)">校验中…</p>
			) : !validation ? (
				<p className="text-sm text-(--color-foreground-tertiary)">编辑后点击校验，查看 canonical hash 与合法性。</p>
			) : isStale ? (
				<div role="status" className="flex flex-col gap-1 text-sm text-(--color-led-warning)">
					<span>校验已过期</span>
					<span className="text-xs text-(--color-foreground-tertiary)">working copy 已变化，请重新校验后再保存。</span>
				</div>
			) : (
				<div className="flex flex-col gap-2 text-sm">
					<div className="flex items-center gap-2">
						<StatusBadge
							variant={validation.valid ? "healthy" : "error"}
							label={validation.valid ? "有效" : "无效"}
							size="sm"
						/>
						<span className="text-(--color-foreground-tertiary)">{validation.changed ? "已变更" : "无变更"}</span>
					</div>
					<p className="font-data text-xs text-(--color-foreground-tertiary)">canonical: {validation.canonicalHash}</p>
					<p className="font-data text-xs text-(--color-foreground-tertiary)">base: {validation.baseSpecHash}</p>
					{validation.errors.length > 0 && (
						<ul className="flex flex-col gap-1">
							{validation.errors.map((error) => (
								<li key={error} className="text-(--color-led-danger)">
									{error}
								</li>
							))}
						</ul>
					)}
				</div>
			)}
		</ContextSection>
	);
}
