import type { ReactElement } from "react";
import { fetchDataProductEvidence } from "@/features/data-products";
import {
	type InstrumentHubSearch,
	InstrumentHubPage as InstrumentHubView,
	type InstrumentTechnicalDependencies,
	InstrumentTechnicalView as InstrumentTechnicalEvidenceView,
	type InstrumentTechnicalSlotProps,
} from "@/features/instruments";
import { getSelectionRun, selectionKeys } from "@/features/selection";

const technicalDependencies: InstrumentTechnicalDependencies = {
	fetchSourceEvidence: fetchDataProductEvidence,
	getSelectionRun,
	selectionRunKey: selectionKeys.run,
};

/** Compose Instrument analysis with Selection and certified Data Product evidence. */
export function InstrumentTechnicalView(props: InstrumentTechnicalSlotProps): ReactElement {
	return <InstrumentTechnicalEvidenceView {...props} dependencies={technicalDependencies} />;
}

function renderTechnical(props: InstrumentTechnicalSlotProps): ReactElement {
	return <InstrumentTechnicalView {...props} />;
}

/** Route-ready Instrument hub whose peer capability wiring stays above features. */
export function InstrumentHubPage({ search = {} }: { readonly search?: InstrumentHubSearch }): ReactElement {
	return <InstrumentHubView renderTechnical={renderTechnical} search={search} />;
}
