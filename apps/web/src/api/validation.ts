export class RuntimeValidationError extends Error {
	readonly boundary: string;
	readonly field: string;

	constructor(boundary: string, field: string, message: string) {
		super(`${boundary}.${field}: ${message}`);
		this.boundary = boundary;
		this.field = field;
		this.name = "RuntimeValidationError";
	}
}

export function recordValue(value: unknown, boundary: string, field = "payload"): Record<string, unknown> {
	if (typeof value !== "object" || value === null || Array.isArray(value)) {
		throw new RuntimeValidationError(boundary, field, "expected an object");
	}
	return value as Record<string, unknown>;
}

export function stringValue(record: Readonly<Record<string, unknown>>, field: string, boundary: string): string {
	const value = record[field];
	if (typeof value !== "string" || value.length === 0) {
		throw new RuntimeValidationError(boundary, field, "expected a non-empty string");
	}
	return value;
}

export function booleanValue(record: Readonly<Record<string, unknown>>, field: string, boundary: string): boolean {
	const value = record[field];
	if (typeof value !== "boolean") throw new RuntimeValidationError(boundary, field, "expected a boolean");
	return value;
}

export function integerValue(
	record: Readonly<Record<string, unknown>>,
	field: string,
	boundary: string,
	minimum = Number.MIN_SAFE_INTEGER,
): number {
	const value = record[field];
	if (!Number.isSafeInteger(value) || (value as number) < minimum) {
		throw new RuntimeValidationError(boundary, field, `expected an integer >= ${minimum}`);
	}
	return value as number;
}

export function enumValue<const Values extends readonly string[]>(
	record: Readonly<Record<string, unknown>>,
	field: string,
	values: Values,
	boundary: string,
): Values[number] {
	const value = record[field];
	if (typeof value !== "string" || !values.includes(value)) {
		throw new RuntimeValidationError(boundary, field, `expected one of ${values.join(", ")}`);
	}
	return value;
}

export function hashValue(record: Readonly<Record<string, unknown>>, field: string, boundary: string): string {
	const value = stringValue(record, field, boundary);
	if (!/^[0-9a-f]{64}$/u.test(value)) {
		throw new RuntimeValidationError(boundary, field, "expected a lowercase SHA-256 hash");
	}
	return value;
}

export function arrayValue(record: Readonly<Record<string, unknown>>, field: string, boundary: string): unknown[] {
	const value = record[field];
	if (!Array.isArray(value)) throw new RuntimeValidationError(boundary, field, "expected an array");
	return value;
}
