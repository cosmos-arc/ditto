import type { ReactElement } from "react";
import { NumberField, TextField } from "./spec-fields";

interface ParamFieldsProps {
	readonly params: Readonly<Record<string, unknown>>;
	readonly onChange: (params: Readonly<Record<string, unknown>>) => void;
}

function isScalarValue(value: unknown): value is number | string {
	return typeof value === "number" || typeof value === "string";
}

/**
 * 渲染 `params` 中的标量（number/string）条目为可编辑字段；非标量（对象/数组）跳过。
 *
 * 每次编辑把更新后的 key 合并回完整 params 后回调 onChange，保持 spec_json 中其它键不变。
 */
export function ParamFields({ params, onChange }: ParamFieldsProps): ReactElement {
	const entries = Object.entries(params);
	const hasScalar = entries.some(([, value]) => isScalarValue(value));

	if (!hasScalar) {
		return <p className="text-xs text-(--color-foreground-tertiary)">无可编辑参数</p>;
	}

	return (
		<div className="flex flex-col gap-2">
			{entries.map(([key, value]) => {
				if (typeof value === "number") {
					return (
						<NumberField
							key={key}
							label={key}
							value={value}
							onChange={(newValue) => onChange({ ...params, [key]: newValue })}
						/>
					);
				}
				if (typeof value === "string") {
					return (
						<TextField
							key={key}
							label={key}
							value={value}
							onChange={(newValue) => onChange({ ...params, [key]: newValue })}
						/>
					);
				}
				return null;
			})}
		</div>
	);
}
