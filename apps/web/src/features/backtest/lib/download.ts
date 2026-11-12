/** 回测导出物统一落盘方式：内存 Blob → 一次性对象 URL → 下载后立即回收。 */
export function downloadTextBlob(content: string, filename: string, type = "text/csv;charset=utf-8"): void {
	const url = URL.createObjectURL(new Blob([content], { type }));
	const anchor = document.createElement("a");
	anchor.href = url;
	anchor.download = filename;
	anchor.click();
	URL.revokeObjectURL(url);
}
