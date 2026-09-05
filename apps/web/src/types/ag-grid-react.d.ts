import type { AgGridReactProps } from "ag-grid-react";
import type { Component } from "react";

/*
 * Bun's isolated peer layout leaves ag-grid-react's declaration unable to see
 * the workspace @types/react package. Merge the resolved React Component
 * surface back into the vendor class so JSX still validates the real grid
 * props instead of falling back to an untyped compatibility cast.
 */
declare module "ag-grid-react" {
	interface AgGridReact<TData> extends Component<AgGridReactProps<TData>, object> {}
}
