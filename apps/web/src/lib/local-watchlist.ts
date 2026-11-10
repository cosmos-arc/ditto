export const LOCAL_WATCHLIST_STORAGE_KEY = "ditto.market-watchlist.v1";

export function readLocalWatchlist(): number[] {
	try {
		const parsed = JSON.parse(localStorage.getItem(LOCAL_WATCHLIST_STORAGE_KEY) ?? "[]") as unknown;
		if (!Array.isArray(parsed)) return [];
		// 历史版本可能写入重复 ID；保留首次出现顺序去重。
		const seen = new Set<number>();
		return parsed.filter((value): value is number => {
			if (!Number.isInteger(value) || value <= 0) return false;
			if (seen.has(value)) return false;
			seen.add(value);
			return true;
		});
	} catch {
		return [];
	}
}

export function addToLocalWatchlist(instrumentId: number): void {
	const current = readLocalWatchlist();
	if (current.includes(instrumentId)) return;
	localStorage.setItem(LOCAL_WATCHLIST_STORAGE_KEY, JSON.stringify([...current, instrumentId]));
}
