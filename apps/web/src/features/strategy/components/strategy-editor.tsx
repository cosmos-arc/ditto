import { useStrategyVersions } from "../hooks/use-strategy-versions";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { DittoErrorBoundary } from "@/lib/error-boundary";
import { ContextSection } from "@/components/domain/context-section";

interface StrategyEditorProps {
	readonly id: string;
}

function StrategyEditorContent({ id }: StrategyEditorProps) {
	const { data, isLoading, isError } = useStrategyVersions(id);

	if (isLoading) {
		return <LoadingSkeleton />;
	}

	if (isError || !data) {
		throw new Error("Failed to load strategy versions");
	}

	const latestVersion = data.versions[data.versions.length - 1];
	const code = latestVersion?.code ?? "";

	return (
		<div className="flex flex-col gap-[var(--section-gap)] p-[var(--density-panel-padding)]">
			<ContextSection title="策略代码">
				<pre className="overflow-auto p-[var(--density-panel-padding)] text-sm text-(--color-foreground-tertiary)">
					<code>{code}</code>
				</pre>
			</ContextSection>
		</div>
	);
}

export function StrategyEditor(props: StrategyEditorProps) {
	return (
		<DittoErrorBoundary>
			<StrategyEditorContent {...props} />
		</DittoErrorBoundary>
	);
}
