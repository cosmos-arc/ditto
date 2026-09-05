export function capturedRequest(calls: readonly Parameters<typeof fetch>[], index = 0): Request {
	const call = calls[index];
	if (!call) throw new Error(`expected fetch call ${index + 1}`);
	const [input, init] = call;
	if (input instanceof Request && init === undefined) return input;
	const normalized = input instanceof URL ? input.href : input;
	return init === undefined ? new Request(normalized) : new Request(normalized, init);
}

export function requestPath(request: Request): string {
	const url = new URL(request.url);
	return `${url.pathname}${url.search}`;
}

export async function requestJson(request: Request): Promise<unknown> {
	return request.clone().json();
}
