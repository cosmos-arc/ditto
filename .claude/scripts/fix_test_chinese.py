"""
批量替换测试文件中的中文文档字符串为英文。

主要用于 P2-1 任务：统一测试文档字符串为英文。
"""

import re
from pathlib import Path

# 中文到英文的映射表
TRANSLATIONS = {
    # 类文档字符串
    "排序验证增强测试。": "Tests for enhanced sorting validation.",
    "测试 OnDuplicate 语义。": "Tests for OnDuplicate semantics.",
    "测试 batch 内部重复检测和去重。": "Tests for batch internal duplicate detection and deduplication.",
    "测试 read 的去重和排序逻辑。": "Tests for read deduplication and sorting logic.",
    "测试 trade_date 类型规范化的完整覆盖。": "Tests for complete trade_date type normalization coverage.",
    "测试 write 返回值的完整性。": "Tests for write return value completeness.",
    "边界条件测试。": "Tests for edge cases.",
    "测试多年份分区的边界情况。": "Tests for multi-year partition edge cases.",

    # 方法文档字符串
    "跨年分区数据的排序正确性。": "Tests sorting correctness across year partitions.",
    "重复键的正确处理（keep=\"last\"）。": "Tests correct handling of duplicate keys (keep='last').",
    "合并后排序顺序的稳定性。": "Tests sorting order stability after merge.",
    "测试 write 检测并去除 batch 内部重复（保留第一条）。": "Tests write detects and removes batch internal duplicates (keeps first).",
    "测试不包含内部重复的 batch 正常写入。": "Tests batch without internal duplicates writes normally.",
    "测试 read 使用 unique(keep='last') 去重。": "Tests read uses unique(keep='last') for deduplication.",
    "测试 read 返回按 (sid, trade_date) 排序的结果。": "Tests read returns results sorted by (sid, trade_date).",
    "测试 write 规范化 string 类型的 trade_date。": "Tests write normalizes string type trade_date.",
    "测试 write 保持 Date 类型不变。": "Tests write preserves Date type.",
    "测试 write 规范化 datetime 类型的 trade_date。": "Tests write normalizes datetime type trade_date.",
    "测试 write 对无效日期格式抛出错误。": "Tests write raises error on invalid date format.",
    "测试 write 返回正确的文件路径和校验和。": "Tests write returns correct file path and checksum.",
    "测试合并写入后返回的校验和会更新。": "Tests returned checksum updates after merge write.",
    "测试 read 同时使用所有过滤条件。": "Tests read with all filters applied simultaneously.",
    "测试 read 在不指定日期时使用默认年份范围（1990-2099）。": "Tests read uses default year range (1990-2099) when dates not specified.",
    "测试写入单行数据。": "Tests writing single row data.",
    "测试写入空 DataFrame。": "Tests writing empty DataFrame.",
    "测试跨年边界日期的读取。": "Tests reading across year boundary dates.",
    "测试写入到不存在的年份分区。": "Tests writing to non-existent year partition.",

    # 常见短语
    "创建包含内部重复的数据": "Create data with internal duplicates",
    "创建包含重复的数据（通过多次写入制造）": "Create data with duplicates (via multiple writes)",
    "创建不包含重复的数据": "Create data without duplicates",
    "创建未排序的数据": "Create unsorted data",
    "创建包含 string trade_date 的 DataFrame": "Create DataFrame with string trade_date",
    "创建包含 Date 类型的 DataFrame": "Create DataFrame with Date type",
    "创建包含 datetime 类型的 DataFrame": "Create DataFrame with datetime type",
    "创建包含无效日期格式的 DataFrame": "Create DataFrame with invalid date format",
    "写入数据，应该自动去重（保留第一条）": "Write data, should auto-deduplicate (keep first)",
    "写入": "Write",
    "再次写入包含重复键的数据（更新现有记录）": "Write data with duplicate keys again (update existing records)",
    "追加写入": "Append write",
    "读取数据，read 应该使用 unique(keep='last')": "Read data, read should use unique(keep='last')",
    "读取数据": "Read data",
    "读取并验证去重结果（应该保留第一条）": "Read and verify deduplication result (should keep first)",
    "读取并验证": "Read and verify",
    "读取应该返回空结果": "Read should return empty result",
    "验证写入成功": "Verify write succeeded",
    "验证返回值": "Verify return values",
    "验证校验和与文件一致": "Verify checksum matches file",
    "验证文件路径相同，但校验和不同（因为内容变了）": "Verify same file path but different checksum (content changed)",
    "验证保留的是第一条记录的值": "Verify kept value is from first record",
    "验证去重后保留最后一条记录": "Verify deduplication keeps last record",
    "验证结果按": "Verify results are sorted by",
    "验证排序：": "Verify sorting:",
    "验证结果包含两个分区的数据": "Verify result contains data from both partitions",
    "验证结果": "Verify result",
    "验证文件被创建": "Verify file was created",
    "验证": "Verify",
    "使用的是最后写入的值": "uses last written value",
    "使用所有过滤条件": "Use all filters",
    "写入应该规范化为 Date 类型": "Write should normalize to Date type",
    "应该能写入空 DataFrame": "Should be able to write empty DataFrame",
    "应该能创建新分区": "Should be able to create new partition",
    "应该抛出异常（": "Should raise exception (",
    "不指定日期范围，应该能读取到所有数据": "No date range specified, should read all data",
    "没有重复，所有记录都保留": "no duplicates, all records kept",
    "查询跨年数据": "Query cross-year data",
    "准备测试数据": "Prepare test data",
    "第一条记录的值": "value of first record",
    "最后写入的值": "last written value",
    "最后写入的值": "last written value",
    "polars 解析日期失败": "polars date parsing failed",
    "更新后的值": "updated value",
    "sid 升序，相同 sid 时 trade_date 升序": "sid ascending, trade_date ascending for same sid",
    "和": "and",
    "唯一记录": "unique records",
    "唯一键": "unique keys",
    "写入 2024 年数据": "Write 2024 data",
    "写入跨年数据": "Write cross-year data",
    "重复": "duplicate",
    "重复 1000001/2024-01-02": "duplicate 1000001/2024-01-02",
    "重复 1000002/2024-01-03": "duplicate 1000002/2024-01-03",
    "重复记录不同值": "duplicate records with different values",
}


def fix_chinese_in_file(file_path: Path) -> bool:
    """修复单个文件中的中文。

    Args:
        file_path: 测试文件路径

    Returns:
        是否有修改
    """
    content = file_path.read_text(encoding="utf-8")
    original = content

    # 第一阶段：替换完整短语
    for chinese, english in sorted(TRANSLATIONS.items(), key=lambda x: -len(x[0])):
        # 文档字符串
        content = content.replace(f'"""{chinese}"""', f'"""{english}"""')
        content = content.replace(f"'''{chinese}'''", f"'''{english}'''")
        # 注释
        content = re.sub(rf'# {re.escape(chinese)}([^\n])', rf'# {english}\1', content)
        content = re.sub(rf'# {re.escape(chinese)}\n', rf'# {english}\n', content)

    # 第二阶段：处理常见的中英混合模式
    replacements = [
        # 处理中文标点
        ("。", "."),

        # 处理 "3 条唯一记录" -> "3 unique records"
        (r'(\d+)\s*条唯一记录', r'\1 unique records'),
        (r'(\d+)\s*条唯一键', r'\1 unique keys'),

        # 处理 "第一条记录的值" -> "first record value"
        ("第一条记录的值", "first record value"),

        # 处理 "最后写入的值" -> "last written value"
        ("最后写入的值", "last written value"),

        # 处理 "duplicate记录不同值" -> "duplicate records with different values"
        ("duplicate记录不同值", "duplicate records with different values"),

        # 处理 "polars 解析日期失败" -> "polars date parsing failed"
        ("polars 解析日期失败", "polars date parsing failed"),

        # 处理 "和" 在特定上下文中
        (r'(\d+)/(\d{4}-\d{2}-\d{2})\s*和\s*(\d+)/(\d{4}-\d{2}-\d{2})',
         r'\1/\2 and \3/\4'),

        # 处理 "（" 和 "）" -> "(" 和 ")"
        ("（", "("),
        ("）", ")"),

        # 处理 "排序验证增强测试。" -> "Tests for enhanced sorting validation."
        ("排序验证增强测试。", "Tests for enhanced sorting validation."),
    ]

    for pattern, replacement in replacements:
        content = re.sub(pattern, replacement, content)

    # 第三阶段：处理剩余的常见中文模式
    content = re.sub(r'#\s*[^\x00-\x7F]+', '# [REVIEW]', content)
    content = re.sub(r'"""[^\x00-\x7F]+"""', '"""[REVIEW]"""', content)

    if content != original:
        file_path.write_text(content, encoding="utf-8")
        return True
    return False


def main():
    """主函数。"""
    # 查找所有测试文件
    project_root = Path(__file__).parent.parent.parent
    test_files = []

    # DataHub 测试文件
    datahub_tests = project_root / "packages" / "datahub" / "tests"
    if datahub_tests.exists():
        test_files.extend(datahub_tests.rglob("test_*.py"))

    # Foundation 测试文件
    foundation_tests = project_root / "packages" / "foundation" / "tests"
    if foundation_tests.exists():
        test_files.extend(foundation_tests.rglob("test_*.py"))

    # 排除 __pycache__ 和 .pyc
    test_files = [f for f in test_files if f.is_file() and f.suffix == ".py"]

    print(f"Found {len(test_files)} test files")

    modified_count = 0
    for test_file in test_files:
        try:
            if fix_chinese_in_file(test_file):
                print(f"Modified: {test_file.relative_to(project_root)}")
                modified_count += 1
        except Exception as e:
            print(f"Error processing {test_file.relative_to(project_root)}: {e}")

    print(f"\nTotal modified: {modified_count}/{len(test_files)} files")


if __name__ == "__main__":
    main()
