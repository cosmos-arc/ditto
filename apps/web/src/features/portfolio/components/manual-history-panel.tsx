import {
	fetchManualAccountHistory,
	type ManualHistoryQueryIdentity,
	type ManualLedgerRevision,
} from "../api/manual-accounts";
import { tradingKeys } from "../api/query-keys";
import { AccountHistoryPanel } from "./account-history-panel";

/** MANUAL variant of the shared history panel: real recorded ledger facts. */
export function ManualHistoryPanel({
	accountId,
	asOf,
	ledgerRevision,
}: {
	readonly accountId: string;
	readonly asOf: string;
	readonly ledgerRevision: ManualLedgerRevision;
}) {
	return (
		<AccountHistoryPanel
			scopeLabel="实盘记录（Manual）"
			scopeNote={`只读重放：账本修订 ${ledgerRevision.event_count} 条事件；价格来自显式保留快照，不回退 latest`}
			asOf={asOf}
			ledgerRevision={ledgerRevision}
			queryKeyFor={(identity: ManualHistoryQueryIdentity) => tradingKeys.manualHistory(accountId, identity)}
			fetchHistory={(identity: ManualHistoryQueryIdentity) => fetchManualAccountHistory(accountId, identity)}
		/>
	);
}
