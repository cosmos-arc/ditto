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
	readonly payload: Readonly<Record<string, unknown>>;
};

type VisibilityTarget = {
	readonly visibilityState: DocumentVisibilityState;
	addEventListener(type: "visibilitychange", listener: () => void): void;
	removeEventListener(type: "visibilitychange", listener: () => void): void;
};

type AgentEventStreamOptions = {
	readonly path: string;
	readonly initialCursor?: number;
	readonly fetcher?: typeof fetch;
	readonly onEvent: (event: AgentEventNotification) => void;
	readonly onState?: (state: AgentStreamState) => void;
	readonly visibilityTarget?: VisibilityTarget;
	readonly minimumRetryMs?: number;
	readonly maximumRetryMs?: number;
};

function isRecord(value: unknown): value is Record<string, unknown> {
	return typeof value === "object" && value !== null;
}

export function parseAgentSse(text: string, afterCursor = 0): readonly AgentEventNotification[] {
	const result: AgentEventNotification[] = [];
	let cursor = afterCursor;
	for (const block of text.replaceAll("\r\n", "\n").split("\n\n")) {
		if (!block.trim()) continue;
		let id: number | null = null;
		let eventType = "message";
		const data: string[] = [];
		for (const line of block.split("\n")) {
			if (line.startsWith("id:")) id = Number(line.slice(3).trim());
			else if (line.startsWith("event:")) eventType = line.slice(6).trim();
			else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
		}
		if (id === null || !Number.isSafeInteger(id) || id <= cursor || data.length === 0) continue;
		try {
			const payload: unknown = JSON.parse(data.join("\n"));
			if (!isRecord(payload)) continue;
			result.push({ id, eventType, payload });
			cursor = id;
		} catch {}
	}
	return result;
}

function apiUrl(path: string): string {
	if (/^https?:\/\//u.test(path)) return path;
	const configuredBase = import.meta.env.VITE_API_BASE_URL ?? "/api";
	const base = configuredBase.endsWith("/") ? configuredBase.slice(0, -1) : configuredBase;
	return `${base}${path.startsWith("/") ? path : `/${path}`}`;
}

function terminalEvent(eventType: string): boolean {
	return /(?:^|_)(?:completed|failed|cancelled)$/u.test(eventType);
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

	constructor(options: AgentEventStreamOptions) {
		this.#options = {
			...options,
			minimumRetryMs: options.minimumRetryMs ?? 500,
			maximumRetryMs: options.maximumRetryMs ?? 10_000,
		};
		this.#cursor = options.initialCursor ?? 0;
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
		if (!this.#running) {
			this.#running = true;
			void this.#connect(true);
		}
	};

	async #connect(reconnecting: boolean): Promise<void> {
		if (this.#disposed || !this.#running) return;
		this.#emitState(reconnecting ? "reconnecting" : "connecting");
		this.#abortController = new AbortController();
		try {
			const response = await (this.#options.fetcher ?? fetch)(apiUrl(this.#options.path), {
				headers: { Accept: "text/event-stream", "Last-Event-ID": String(this.#cursor) },
				signal: this.#abortController.signal,
			});
			if (response.status === 401 || response.status === 403) return this.#halt("authorization-required");
			if (response.status === 404) return this.#halt("not-found");
			if (response.status === 410) return this.#halt("cursor-expired");
			if (!response.ok) return this.#scheduleReconnect();
			this.#emitState("open");
			const notifications = parseAgentSse(await response.text(), this.#cursor);
			for (const notification of notifications) {
				this.#cursor = notification.id;
				this.#options.onEvent(notification);
				if (terminalEvent(notification.eventType)) return this.#halt("complete");
			}
			this.#retryCount = 0;
			this.#scheduleReconnect();
		} catch (error) {
			if (error instanceof DOMException && error.name === "AbortError") return;
			this.#emitState("error");
			this.#scheduleReconnect();
		}
	}

	#scheduleReconnect(): void {
		if (this.#disposed || !this.#running) return;
		this.#emitState("reconnecting");
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
		this.#options.onState?.(state);
	}
}

export function createRecoverableAgentEventStream(options: AgentEventStreamOptions): RecoverableAgentEventStream {
	return new RecoverableAgentEventStream(options);
}
