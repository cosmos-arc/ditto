#!/usr/bin/env python3
"""
数据质量检查脚本 - Phase 0.5
生成 Golden Dataset 数据质量报告.

Usage:
    python scripts/check_data_quality.py [--symbol SYMBOL] [--output FILE]

Examples:
    # 检查所有 Golden Dataset 标的
    python scripts/check_data_quality.py

    # 检查单个标的
    python scripts/check_data_quality.py --symbol 510300.SH

    # 指定输出文件
    python scripts/check_data_quality.py --output quality_report.json

"""

import argparse
import json
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

# Import from installed packages (editable mode)
from ditto_core.data.quality.reporter import DataQualityReporter
from ditto_core.data.service import DataService
from ditto_foundation.config import get_settings

# Golden Dataset 标的配置
GOLDEN_SYMBOLS = [
    "510300.SH",  # 沪深300ETF
    "516010.SH",  # 游戏ETF
    "513100.SH",  # 纳指ETF
    "000300.SH",  # 沪深300指数
]

# 质量分数阈值
EXCELLENT_THRESHOLD = 0.9
GOOD_THRESHOLD = 0.7


def check_single_symbol_quality(
    symbol: str, reporter: DataQualityReporter, data_service: DataService
) -> dict[str, Any]:
    """
    检查单个标的数据质量。.

    Args:
        symbol: 标的代码
        reporter: DataQualityReporter实例
        data_service: DataService实例

    Returns:
        质量报告字典

    """
    print(f"检查 {symbol}...")

    # 加载数据（2022-2024年）
    df = data_service.analytics.get_daily_data(
        symbol=symbol,
        start_date="2022-01-01",
        end_date="2024-12-31",
    )

    if df.empty:
        print(f"  ❌ {symbol}: 无数据")
        return {"symbol": symbol, "error": "No data available"}

    print(f"  ✅ {symbol}: {len(df)} 条记录")

    # 生成报告
    report = reporter.generate_report(df, symbol)
    return report


def check_golden_dataset_quality(args: argparse.Namespace) -> None:
    """
    检查 Golden Dataset 数据质量。.

    Args:
        args: 命令行参数

    """
    print("=" * 60)
    print("Ditto Phase 0.5 数据质量检查")
    print("=" * 60)

    # 获取配置
    settings = get_settings()

    # 初始化服务和报告器
    with DataService(settings) as data_service:
        reporter = DataQualityReporter()

        # 检查单个标的
        if args.symbol:
            if args.symbol not in GOLDEN_SYMBOLS:
                print(f"\n⚠️  警告: {args.symbol} 不在 Golden Dataset 标的列表中")
                print(f"Golden Dataset 标的: {', '.join(GOLDEN_SYMBOLS)}")

            report = check_single_symbol_quality(args.symbol, reporter, data_service)

            # 输出报告
            print("\n" + "=" * 60)
            print("数据质量报告")
            print("=" * 60)
            print(f"标的: {report['symbol']}")
            print(f"检查时间: {report['timestamp']}")
            print(f"数据记录数: {report['total_records']:,}")
            print(f"质量分数: {report['quality_score']:.2%}")

            if report.get("date_range"):
                print(
                    f"数据范围: {report['date_range']['start']} 至 {report['date_range']['end']}"
                )

            print("\n验证结果:")
            print(f"  - 通过: {report['summary']['passed']}")
            print(f"  - 失败: {report['summary']['failed']}")

            print("\n详细验证:")
            for validator in report["validators"]:
                status_icon = "✅" if validator["status"] == "passed" else "❌"
                print(f"  {status_icon} {validator['name']}: {validator['message']}")

            # 保存报告
            if args.output:
                save_report(report, args.output)
            else:
                # 默认文件名
                filename = f"quality_report_{args.symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                save_report(report, filename)

            return

        # 批量检查
        print(f"\n检查标的: {', '.join(GOLDEN_SYMBOLS)}")
        print("\n1. 加载数据...")

        data_dict = {}
        for symbol in GOLDEN_SYMBOLS:
            df = data_service.analytics.get_daily_data(
                symbol=symbol,
                start_date="2022-01-01",
                end_date="2024-12-31",
            )

            if not df.empty:
                data_dict[symbol] = df
                print(f"  ✅ {symbol}: {len(df):,} 条记录")
            else:
                print(f"  ❌ {symbol}: 无数据")

        if not data_dict:
            print("\n❌ 错误: 没有可用的数据")
            sys.exit(1)

        print("\n2. 生成质量报告...")
        batch_report = reporter.generate_batch_report(data_dict)

        # 输出汇总报告
        print("\n" + "=" * 60)
        print("数据质量汇总报告")
        print("=" * 60)
        print(f"检查标的数: {batch_report['total_symbols']}")
        print(f"总记录数: {batch_report['summary']['total_records']:,}")
        print(f"平均质量分数: {batch_report['summary']['avg_quality_score']:.2%}")

        # 质量分数分布
        dist = batch_report["summary"]["score_distribution"]
        print("\n质量分数分布:")
        print(f"  - 优秀 (90-100%): {dist['excellent']}")
        print(f"  - 良好 (70-90%): {dist['good']}")
        print(f"  - 一般 (50-70%): {dist['fair']}")
        print(f"  - 较差 (<50%): {dist['poor']}")

        # 问题标的
        if batch_report["summary"]["failed_symbols"]:
            print(
                f"\n⚠️  问题标的: {', '.join(batch_report['summary']['failed_symbols'])}"
            )

        # 各标的质量分数
        print("\n各标的质量分数:")
        for report in batch_report["reports"]:
            status_icon = (
                "✅"
                if report["quality_score"] >= 0.9
                else "⚠️"
                if report["quality_score"] >= 0.7
                else "❌"
            )
            print(f"  {status_icon} {report['symbol']}: {report['quality_score']:.2%}")

        # 详细问题
        print("\n" + "=" * 60)
        print("详细问题")
        print("=" * 60)
        has_issues = False
        for report in batch_report["reports"]:
            if report["summary"]["failed"] > 0:
                has_issues = True
                print(
                    f"\n{report['symbol']} (质量分数: {report['quality_score']:.2%}):"
                )
                for validator in report["validators"]:
                    if validator["status"] == "failed":
                        print(f"  ❌ {validator['name']}: {validator['message']}")

        if not has_issues:
            print("\n✅ 所有标的都通过了质量检查！")

        # 保存报告
        if args.output:
            save_report(batch_report, args.output)
        else:
            # 默认文件名
            filename = (
                f"batch_quality_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            )
            save_report(batch_report, filename)


def save_report(report: dict[str, Any], filename: str) -> None:
    """
    保存报告到JSON文件。.

    Args:
        report: 报告字典
        filename: 输出文件名

    """
    # 确保reports目录存在
    report_path = Path("reports") / filename
    report_path.parent.mkdir(exist_ok=True)

    # 保存报告
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)

    print(f"\n📄 详细报告已保存至: {report_path}")


def main() -> None:
    """主函数."""
    parser = argparse.ArgumentParser(
        description="Ditto Phase 0.5 数据质量检查工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s                           # 检查所有 Golden Dataset 标的
  %(prog)s --symbol 510300.SH       # 检查单个标的
  %(prog)s --output report.json     # 指定输出文件
        """,
    )

    parser.add_argument(
        "--symbol",
        type=str,
        help="检查单个标的代码（如 510300.SH）",
    )

    parser.add_argument(
        "--output",
        type=str,
        help="指定报告输出文件名（默认保存在 reports/ 目录）",
    )

    args = parser.parse_args()

    try:
        check_golden_dataset_quality(args)
    except KeyboardInterrupt:
        print("\n\n用户中断操作")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
