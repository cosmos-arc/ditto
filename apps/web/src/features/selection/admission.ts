import type { AdmissionResponse } from "./api";

const PURPOSES: Record<string, string> = {
	display: "展示",
	exploration: "探索",
	formal_research: "正式研究",
	promotion_paper: "晋级/Paper 数据输入",
};
const REASONS: Record<string, string> = {
	HISTORY_SNAPSHOT_MISSING: "请绑定历史证券池的主数据、交易状态及必要的成分关系快照。",
	HISTORY_SNAPSHOT_CONFLICT: "历史证券池身份或来源不一致，请重新读取指定时点的证券池。",
	HISTORY_ROSTER_CONFLICT: "输入名单与历史观察池不一致，请保留退市及不可投资样本。",
	HISTORY_FIELDS_MISSING: "来源缺少历史有效区间或可知时间，不能用今日名单代替。",
	HISTORY_NOT_OBSERVED: "该来源在知识截止前尚未被观察，无法证明当时可用。",
	HISTORY_ADMISSION_BLOCKED: "历史证券池字段尚未通过许可、覆盖和认证检查。",
	FIELD_EVIDENCE_MISSING: "请补齐该字段的认证与范围证据，再重新检查。",
	CONSUMER_INPUT_MISMATCH: "输入内容、区间或依赖与审核证据不一致，请恢复原输入包或重新验证。",
	CONSUMER_BINDING_MISSING: "输入缺少经审核的字段来源绑定，请补齐输入包。",
	CERTIFICATION_MISSING: "没有有效认证，请检查审核或撤销记录。",
	LICENSE_MISSING: "未找到来源许可，请核实并登记相应用途权益。",
	LICENSE_RESTRICTED: "当前许可不允许此用途，请调整用途或核实权益。",
	LICENSE_INTERVAL_MISSING: "许可在当前使用日无效，请核实有效期。",
	LICENSE_CERTIFICATION_CONFLICT: "许可与认证引用不一致，请重新核对证据。",
	FIELD_COVERAGE_MISSING: "字段覆盖不足，请缩小研究区间或补齐证据。",
	INSTRUMENT_SCOPE_MISSING: "证券不在认证范围内，请调整证券范围。",
	TIME_EVIDENCE_MISSING: "历史可得时间未知，请补齐时间证据。",
	TIME_NOT_VISIBLE: "该字段在决策截止时尚不可得，请调整决策时点。",
	SNAPSHOT_MISSING: "找不到指定快照，请检查输入包中的引用。",
	SNAPSHOT_CONFLICT: "快照与当前输入或认证不一致，请使用匹配版本。",
	SNAPSHOT_UNBOUND: "该快照来源未被任何消费字段绑定，请移除多余来源或补齐字段绑定。",
	SNAPSHOT_COVERAGE_MISSING: "快照没有覆盖所需区间，请缩小范围或使用匹配快照。",
	SNAPSHOT_PAYLOAD_MISSING: "快照未保留原始载荷，无法提供可重放证据。",
};

export function toAdmissionView(value: AdmissionResponse) {
	if (
		typeof value.allowed !== "boolean" ||
		value.rule_version !== "field-admission-v2" ||
		!Array.isArray(value.fields)
	) {
		throw new Error("数据准入响应无效，请重新检查");
	}
	const computed =
		value.fields.length > 0 &&
		value.fields.every((field) => Array.isArray(field.allowed_uses) && field.allowed_uses.includes(value.purpose));
	if (value.purpose !== "formal_research" || computed !== value.allowed)
		throw new Error("数据准入响应无效，请重新检查");
	return {
		allowed: value.allowed,
		ruleVersion: value.rule_version,
		fields: value.fields.map((field) => ({
			label: `${field.dataset_id || "输入包"} · ${field.field}`,
			consumer: field.consumer_field,
			uses: field.allowed_uses.map((use) => PURPOSES[use] ?? use).join("、") || "暂无允许用途",
			reasons: field.reason_codes.map((reason) => REASONS[reason] ?? `需要处理：${reason}`),
			coverage: field.covered_from && field.covered_to ? `${field.covered_from} — ${field.covered_to}` : "覆盖未知",
			timePrecision: field.time_precision,
			snapshot: field.snapshot_id || "未绑定",
			license: field.license_record_id ?? "未找到",
			certification: field.certification_report_id ?? "未找到",
			evidence: field.evidence_uri ?? "未提供",
		})),
	};
}
export type AdmissionView = ReturnType<typeof toAdmissionView>;
