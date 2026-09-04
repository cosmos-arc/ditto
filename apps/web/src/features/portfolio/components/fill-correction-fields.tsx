import type { FillCorrectionFormState } from "./fill-correction-form";

interface FillCorrectionFieldsProps {
	readonly form: FillCorrectionFormState;
	readonly showReplacement: boolean;
	readonly disabled: boolean;
	readonly onChange: (field: keyof FillCorrectionFormState, value: string) => void;
}

const INPUT_CLASS =
	"rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-1) px-2 py-1.5 font-data text-(--color-foreground) disabled:opacity-60";

function TextField(props: {
	readonly label: string;
	readonly value: string;
	readonly inputMode?: "numeric" | "decimal";
	readonly type?: "date";
	readonly disabled: boolean;
	readonly onChange: (value: string) => void;
}) {
	return (
		<label className="flex flex-col gap-1 text-(length:--text-sm)">
			<span className="text-(--color-foreground-secondary)">{props.label}</span>
			<input
				aria-label={props.label}
				className={INPUT_CLASS}
				disabled={props.disabled}
				inputMode={props.inputMode}
				type={props.type}
				value={props.value}
				onChange={(event) => props.onChange(event.target.value)}
			/>
		</label>
	);
}

export function FillCorrectionFields({ form, showReplacement, disabled, onChange }: FillCorrectionFieldsProps) {
	return (
		<div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
			{showReplacement && (
				<>
					<TextField
						label="替换成交日期"
						type="date"
						value={form.tradeDate}
						disabled={disabled}
						onChange={(value) => onChange("tradeDate", value)}
					/>
					<TextField
						label="替换成交数量"
						inputMode="numeric"
						value={form.quantity}
						disabled={disabled}
						onChange={(value) => onChange("quantity", value)}
					/>
					<TextField
						label="替换成交价格"
						inputMode="decimal"
						value={form.fillPrice}
						disabled={disabled}
						onChange={(value) => onChange("fillPrice", value)}
					/>
					<TextField
						label="替换手续费"
						inputMode="decimal"
						value={form.fee}
						disabled={disabled}
						onChange={(value) => onChange("fee", value)}
					/>
					<TextField
						label="替换滑点"
						inputMode="decimal"
						value={form.slippage}
						disabled={disabled}
						onChange={(value) => onChange("slippage", value)}
					/>
					<label className="flex flex-col gap-1 text-(length:--text-sm) sm:col-span-2">
						<span className="text-(--color-foreground-secondary)">替换备注</span>
						<textarea
							aria-label="替换备注"
							className={`${INPUT_CLASS} min-h-16 resize-none font-sans`}
							disabled={disabled}
							value={form.notes}
							onChange={(event) => onChange("notes", event.target.value)}
						/>
					</label>
				</>
			)}
			<label className="flex flex-col gap-1 text-(length:--text-sm) sm:col-span-2">
				<span className="text-(--color-foreground-secondary)">更正原因</span>
				<textarea
					aria-label="更正原因"
					className={`${INPUT_CLASS} min-h-20 resize-none font-sans`}
					disabled={disabled}
					value={form.reason}
					onChange={(event) => onChange("reason", event.target.value)}
				/>
			</label>
		</div>
	);
}
