import { useState } from "react";
import type { AdmissionView } from "../admission";

export function SelectionAdmission({ value }: { readonly value: AdmissionView }) {
	const [selected, setSelected] = useState(0);
	const field = value.fields[selected];
	return (
		<section
			aria-label="字段用途准入"
			className="grid gap-2 rounded-(--radius-md) border border-(--color-border-subtle) p-3 text-xs"
		>
			<p role="status">
				{value.allowed ? "数据准入通过" : "数据准入未通过"} · {value.ruleVersion}
			</p>
			<p>数据合格不代表策略已通过研究验证或获得晋级批准。</p>
			{value.fields.length === 0 ? (
				<p>没有可检查的字段，请补齐输入包。</p>
			) : (
				<>
					<label className="grid gap-1">
						选择输入字段
						<select
							aria-label="选择输入字段"
							value={selected}
							onChange={(event) => setSelected(Number(event.currentTarget.value))}
							className="rounded-(--radius-md) border border-(--color-border-primary) bg-(--color-surface-1) p-2"
						>
							{value.fields.map((item, index) => (
								<option key={`${item.consumer}:${item.snapshot}:${item.label}`} value={index}>
									{item.label}
								</option>
							))}
						</select>
					</label>
					{field && (
						<div className="grid gap-1 break-all">
							<p>消费字段：{field.consumer}</p>
							<p>允许用途：{field.uses}</p>
							<p>
								覆盖：{field.coverage} · 时间精度：{field.timePrecision}
							</p>
							{field.reasons.map((reason) => (
								<p key={reason}>{reason}</p>
							))}
							<details>
								<summary className="cursor-pointer">查看来源证据</summary>
								<p>快照：{field.snapshot}</p>
								<p>许可：{field.license}</p>
								<p>认证：{field.certification}</p>
								<p>证据：{field.evidence}</p>
							</details>
						</div>
					)}
				</>
			)}
		</section>
	);
}
