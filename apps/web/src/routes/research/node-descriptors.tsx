import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/research/node-descriptors")({
	component: NodeDescriptorPage,
	staticData: { title: "节点描述符" },
});

function NodeDescriptorPage() {
	return <div className="p-6 text-sm text-(--color-foreground-tertiary)">节点描述符 · T18 接线中</div>;
}
