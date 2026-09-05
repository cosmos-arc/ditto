import { ApiError, apiClient, type EventStreamRequest } from "@/api";
import {
	type AgentCampaignSsePayload,
	type AgentRunSsePayload,
	type AgentSsePayload,
	isTerminalAgentSsePayload,
	parseAgentSsePayload,
} from "@/api/agent-validation";

export type AgentStreamState =
	| "connecting"
	| "open"
	| "reconnecting"
	| "paused"
	| "complete"
	| "authorization-required"
	| "not-found"
	| "cursor-expired"
	| "error"
	| "stopped";

export type AgentEventNotification = {
	readonly id: number;
	readonly eventType: string;
	readonly payload: AgentSsePayload;
};

type VisibilityTarget = {
	readonly visibilityState: DocumentVisibilityState;
	addEventListener(type: "visibilitychange", listener: () => void): void;
	removeEventListener(type: "visibilitychange", listener: () => void): void;
};

type AgentEventStreamOptions = {
	readonly target: { readonly kind: "runs" | "campaigns"; readonly identity: string };
	readonly initialCursor?: number;
	readonly request?: EventStreamRequest;
	readonly onEvent: (event: AgentEventNotification) => void;
	readonly onState?: (state: AgentStreamState) => void;
	readonly visibilityTarget?: VisibilityTarget;
	readonly minimumRetryMs?: number;
	readonly maximumRetryMs?: number;
};

export function parseAgentSse(
	text: string,
	afterCursor = 0,
	target?: AgentEventStreamOptions["target"],
	previousPayload?: AgentSsePayload,
): readonly AgentEventNotification[] {
	const parsed: AgentEventNotification[] = [];
	let previousWireId: number | null = null;
	for (const block of text.replaceAll("\r\n", "\n").split("\n\n")) {
		if (!block.trim()) continue;
		let id: number | null = null;
		let eventType = "message";
		const data: string[] = [];
		let hasEventField = false;
		for (const line of block.split("\n")) {
			if (line.startsWith("id:")) {
				hasEventField = true;
				id = Number(line.slice(3).trim());
			} else if (line.startsWith("event:")) {
				hasEventField = true;
				eventType = line.slice(6).trim();
			} else if (line.startsWith("data:")) {
				hasEventField = true;
				data.push(line.slice(5).trimStart());
			}
		}
		if (!hasEventField) continue;
		if (id === null) throw new Error("agentSse.id: expected a durable event ID");
		if (!Number.isSafeInteger(id) || id < 1)
			throw new Error(`agentSse.id: expected a positive safe integer, received ${id}`);
		if (data.length === 0) throw new Error("agentSse.data: expected a durable event payload");
		if (previousWireId !== null && id <= previousWireId) {
			throw new Error(`agentSse.id: expected strictly increasing IDs after ${previousWireId}, received ${id}`);
		}
		const payload = parseAgentSsePayload(JSON.parse(data.join("\n")), {
			id,
			eventType,
			...(target ? { target } : {}),
		});
		parsed.push({ id, eventType, payload });
		previousWireId = id;
	}
	for (let index = 1; index < parsed.length; index += 1) {
		assertAdjacentPayloads(parsed[index - 1]?.payload, parsed[index]?.payload);
	}
	const result = parsed.filter((notification) => notification.id > afterCursor);
	const firstNew = result[0];
	if (firstNew) {
		if (previousPayload) {
			assertAdjacentPayloads(previousPayload, firstNew.payload);
		} else if (!parsed.some((notification) => notification.id < firstNew.id)) {
			assertChainOrigin(firstNew.payload, afterCursor);
		}
	}
	const terminalIndex = parsed.findIndex(
		(notification) => isRunPayload(notification.payload) && isTerminalAgentSsePayload(notification.payload),
	);
	if (terminalIndex !== -1 && terminalIndex !== parsed.length - 1) {
		throw new Error("agentSse terminal: terminal event must be the final durable frame");
	}
	return result;
}

function isRunPayload(payload: AgentSsePayload): payload is AgentRunSsePayload {
	return "run_id" in payload;
}

function assertChainOrigin(payload: AgentSsePayload, afterCursor: number): void {
	if (isRunPayload(payload)) {
		if (afterCursor === 0 && payload.run_sequence !== 1) {
			throw new Error(`agentSse.run_sequence: expected 1 at chain origin, received ${payload.run_sequence}`);
		}
		return;
	}
	if (payload.event_id !== afterCursor + 1) {
		throw new Error(`agentSse.event_id: expected Campaign ordinal ${afterCursor + 1}, received ${payload.event_id}`);
	}
}

function assertAdjacentPayloads(previous: AgentSsePayload | undefined, current: AgentSsePayload | undefined): void {
	if (!previous || !current) throw new Error("agentSse chain: adjacent payload is missing");
	if (isRunPayload(previous) && isRunPayload(current)) {
		if (current.run_sequence !== previous.run_sequence + 1) {
			throw new Error(`agentSse.run_sequence: expected ${previous.run_sequence + 1}, received ${current.run_sequence}`);
		}
		if (current.prev_hash !== previous.event_hash) {
			throw new Error("agentSse.prev_hash: does not match the preceding event_hash");
		}
		return;
	}
	if (!isRunPayload(previous) && !isRunPayload(current)) {
		const previousCampaign = previous as AgentCampaignSsePayload;
		const currentCampaign = current as AgentCampaignSsePayload;
		if (currentCampaign.event_id !== previousCampaign.event_id + 1) {
			throw new Error(
				`agentSse.event_id: expected Campaign ordinal ${previousCampaign.event_id + 1}, received ${currentCampaign.event_id}`,
			);
		}
		if (currentCampaign.previous_status !== previousCampaign.status) {
			throw new Error("agentSse.previous_status: does not match the preceding Campaign status");
		}
		return;
	}
	throw new Error("agentSse chain: stream identity kind changed within one replay");
}

class RecoverableAgentEventStream {
	readonly #options: Required<Pick<AgentEventStreamOptions, "minimumRetryMs" | "maximumRetryMs">> &
		Omit<AgentEventStreamOptions, "minimumRetryMs" | "maximumRetryMs">;
	#abortController: AbortController | null = null;
	#disposed = false;
	#retryCount = 0;
	#retryTimer: ReturnType<typeof setTimeout> | null = null;
	#running = false;
	#cursor: number;
	#previousPayload: AgentSsePayload | undefined;

	constructor(options: AgentEventStreamOptions) {
		const initialCursor = options.initialCursor ?? 0;
		const minimumRetryMs = options.minimumRetryMs ?? 500;
		const maximumRetryMs = options.maximumRetryMs ?? 10_000;
		if (!Number.isSafeInteger(initialCursor) || initialCursor < 0) {
			throw new RangeError("initialCursor must be a non-negative safe integer");
		}
		if (!Number.isSafeInteger(minimumRetryMs) || minimumRetryMs <= 0) {
			throw new RangeError("minimumRetryMs must be a positive safe integer");
		}
		if (!Number.isSafeInteger(maximumRetryMs) || maximumRetryMs <= 0) {
			throw new RangeError("maximumRetryMs must be a positive safe integer");
		}
		if (maximumRetryMs < minimumRetryMs) {
			throw new RangeError("retry bounds require maximumRetryMs to be at least minimumRetryMs");
		}
		this.#options = {
			...options,
			minimumRetryMs,
			maximumRetryMs,
		};
		this.#cursor = initialCursor;
	}

	get cursor(): number {
		return this.#cursor;
	}

	start(): void {
		if (this.#disposed || this.#running) return;
		this.#running = true;
		this.#options.visibilityTarget?.addEventListener("visibilitychange", this.#handleVisibility);
		if (this.#options.visibilityTarget?.visibilityState === "hidden") {
			this.#emitState("paused");
			return;
		}
		void this.#connect(false);
	}

	stop(): void {
		if (this.#disposed) return;
		this.#disposed = true;
		this.#running = false;
		this.#cleanup();
		this.#emitState("stopped");
	}

	readonly #handleVisibility = (): void => {
		if (this.#disposed) return;
		if (this.#options.visibilityTarget?.visibilityState === "hidden") {
			this.#running = false;
			this.#abortController?.abort();
			this.#clearRetry();
			this.#emitState("paused");
			return;
		}
		if (!this.#running || this.#abortController === null) {
			this.#running = true;
			void this.#connect(true);
		}
	};

	async #connect(reconnecting: boolean): Promise<void> {
		if (this.#disposed || !this.#running) return;
		const abortController = new AbortController();
		this.#abortController = abortController;
		this.#emitState(reconnecting ? "reconnecting" : "connecting");
		if (!this.#isActive(abortController)) return;
		try {
			const request = this.#options.request ?? apiClient.getEventStream;
			const response =
				this.#options.target.kind === "runs"
					? await request("/api/v1/agent/runs/{run_id}/events", {
							params: {
								header: { "Last-Event-ID": this.#cursor },
								path: { run_id: this.#options.target.identity },
							},
							signal: abortController.signal,
						})
					: await request("/api/v1/agent/campaigns/{campaign_id}/events", {
							params: {
								header: { "Last-Event-ID": this.#cursor },
								path: { campaign_id: this.#options.target.identity },
							},
							signal: abortController.signal,
						});
			if (!this.#isActive(abortController)) return;
			if (response.status === 401 || response.status === 403) return this.#halt("authorization-required");
			if (response.status === 404) return this.#halt("not-found");
			if (response.status === 410) return this.#halt("cursor-expired");
			if (response.status === 400 || response.status === 422) return this.#halt("error");
			if (!response.ok) return this.#scheduleReconnect();
			this.#emitState("open");
			if (!this.#isActive(abortController)) return;
			const responseText = await response.text();
			if (!this.#isActive(abortController)) return;
			let notifications: readonly AgentEventNotification[];
			try {
				notifications = parseAgentSse(responseText, this.#cursor, this.#options.target, this.#previousPayload);
			} catch {
				return this.#halt("error");
			}
			for (const notification of notifications) {
				if (!this.#isActive(abortController)) return;
				this.#cursor = notification.id;
				this.#previousPayload = notification.payload;
				try {
					this.#options.onEvent(notification);
				} catch {
					return this.#halt("error");
				}
				if (!this.#isActive(abortController)) return;
				if (isTerminalAgentSsePayload(notification.payload)) return this.#halt("complete");
			}
			if (!this.#isActive(abortController)) return;
			this.#retryCount = 0;
			this.#scheduleReconnect();
		} catch (error) {
			if (!this.#isActive(abortController)) return;
			if (error instanceof DOMException && error.name === "AbortError") return;
			if (error instanceof ApiError && error.errorCode === "API_CONTRACT_MISMATCH") {
				return this.#halt("error");
			}
			this.#emitState("error");
			this.#scheduleReconnect();
		}
	}

	#isActive(abortController: AbortController): boolean {
		return (
			!this.#disposed && this.#running && this.#abortController === abortController && !abortController.signal.aborted
		);
	}

	#scheduleReconnect(): void {
		if (this.#disposed || !this.#running) return;
		this.#emitState("reconnecting");
		if (this.#disposed || !this.#running) return;
		const delay = Math.min(
			this.#options.maximumRetryMs,
			this.#options.minimumRetryMs * 2 ** Math.min(this.#retryCount, 8),
		);
		this.#retryCount += 1;
		this.#retryTimer = setTimeout(() => void this.#connect(true), delay);
	}

	#halt(state: AgentStreamState): void {
		this.#disposed = true;
		this.#running = false;
		this.#cleanup();
		this.#emitState(state);
	}

	#cleanup(): void {
		this.#abortController?.abort();
		this.#abortController = null;
		this.#clearRetry();
		this.#options.visibilityTarget?.removeEventListener("visibilitychange", this.#handleVisibility);
	}

	#clearRetry(): void {
		if (this.#retryTimer !== null) clearTimeout(this.#retryTimer);
		this.#retryTimer = null;
	}

	#emitState(state: AgentStreamState): void {
		try {
			this.#options.onState?.(state);
		} catch {
			this.#disposed = true;
			this.#running = false;
			this.#cleanup();
		}
	}
}

export function createRecoverableAgentEventStream(options: AgentEventStreamOptions): RecoverableAgentEventStream {
	return new RecoverableAgentEventStream(options);
}
