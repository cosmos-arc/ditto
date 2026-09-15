export type ApiValidationIssue = {
	readonly location: readonly (string | number)[];
	readonly message: string;
	readonly type: string;
};

export class ApiError extends Error {
	readonly status: number;
	readonly errorCode: string | undefined;
	readonly requestId: string | undefined;
	readonly detail: string | undefined;
	readonly timestamp: string | number | undefined;
	readonly validationIssues: readonly ApiValidationIssue[];
	readonly payload: unknown;

	constructor(params: {
		readonly status: number;
		readonly message: string;
		readonly payload: unknown;
		readonly errorCode?: string | undefined;
		readonly requestId?: string | undefined;
		readonly detail?: string | undefined;
		readonly timestamp?: string | number | undefined;
		readonly validationIssues?: readonly ApiValidationIssue[] | undefined;
	}) {
		super(params.message);
		this.status = params.status;
		this.errorCode = params.errorCode;
		this.requestId = params.requestId;
		this.detail = params.detail;
		this.timestamp = params.timestamp;
		this.validationIssues = params.validationIssues ?? [];
		this.payload = params.payload;
		this.name = "ApiError";
	}
}
