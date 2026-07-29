/**
 * Spec 编辑器共享表单原子。
 *
 * Wave 1 表单全手写原生 `<input>`（无 shadcn Input/无 RHF）；样式与 trading 域
 * `fill-correction-fields.tsx` 的 `INPUT_CLASS` 保持一致（feature 自包含，不跨域 import）。
 * SpecForm / NodeInspector 复用此处字段组件渲染受控输入。
 */

/** 受控文本/数字输入的共享样式（项目内事实标准 input 样式）。 */
export const INPUT_CLASS =
	"rounded-(--radius-sm) border border-(--color-border-subtle) bg-(--color-surface-1) px-2 py-1.5 font-data text-(--color-foreground) disabled:opacity-60";

interface TextFieldProps {
	readonly label: string;
	readonly value: string;
	readonly disabled?: boolean;
	readonly onChange: (value: string) => void;
}

/** 受控文本字段（label + input），onChange 回调新字符串。 */
export function TextField({ label, value, disabled, onChange }: TextFieldProps) {
	return (
		<label className="flex flex-col gap-1 text-(length:--text-sm)">
			<span className="text-(--color-foreground-secondary)">{label}</span>
			<input
				aria-label={label}
				className={INPUT_CLASS}
				disabled={disabled}
				value={value}
				onChange={(event) => onChange(event.target.value)}
			/>
		</label>
	);
}

interface NumberFieldProps {
	readonly label: string;
	readonly value: number;
	readonly disabled?: boolean;
	readonly onChange: (value: number) => void;
}

/** 受控数值字段；空或非数字输入回退为 0（与后端数值语义一致，避免 NaN 入 spec_json）。 */
export function NumberField({ label, value, disabled, onChange }: NumberFieldProps) {
	return (
		<label className="flex flex-col gap-1 text-(length:--text-sm)">
			<span className="text-(--color-foreground-secondary)">{label}</span>
			<input
				aria-label={label}
				className={INPUT_CLASS}
				disabled={disabled}
				inputMode="decimal"
				type="number"
				value={Number.isFinite(value) ? value : 0}
				onChange={(event) => {
					const parsed = Number(event.target.value);
					onChange(Number.isFinite(parsed) ? parsed : 0);
				}}
			/>
		</label>
	);
}
