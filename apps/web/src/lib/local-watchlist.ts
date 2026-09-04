export const LOCAL_WATCHLIST_STORAGE_KEY = "ditto.market-watchlist.v1";

export function readLocalWatchlist(): number[] {
	try {
		const parsed = JSON.parse(localStorage.getItem(LOCAL_WATCHLIST_STORAGE_KEY) ?? "[]") as unknown;
		if (!Array.isArray(parsed)) return [];
		return parsed.filter((value): value is number => Number.isInteger(value) && value > 0);
	} catch {
		return [];
	}
}

export function addToLocalWatchlist(instrumentId: number): void {
	const current = readLocalWatchlist();
	if (current.includes(instrumentId)) return;
	localStorage.setItem(LOCAL_WATCHLIST_STORAGE_KEY, JSON.stringify([...current, instrumentId]));
}
