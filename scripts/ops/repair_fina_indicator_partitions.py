"""#613 一次性运维：fina_indicator 存量跨分区错位修复.

历史根因：#196 回补时代按「摄取锚年」落分区，后续按「报告期年」修正；
锚年分区（2026）留下 33,851 行错位副本，与正确分区的同键行构成跨分区
双胞胎——有界读（按报告年）看不到错位行、无界读确定性返回错位副本，
两者结果不一致。

修复语义（有界读真相不变）：
- 错位行的键在正确分区已有双胞胎 → 删除错位副本（正确分区行是例行
  修正通道（KEEP_LAST_FLAGGED）持续升级的权威版本）。双胞胎默认要求
  非键值列逐列一致；值分歧组须 --allow-value-divergence 显式放行并留
  计数（分歧按正确分区裁决，correctness F3）；
- 错位行的键在正确分区不存在（孤儿）→ 移动到正确分区（重写集合 =
  错位分区 ∪ 孤儿目标分区，correctness F2——否则孤儿会被静默丢弃）。

用法（dev 根示例）:
    uv run --no-sync python scripts/ops/repair_fina_indicator_partitions.py \
        [--data-root <root>] [--apply] [--allow-value-divergence]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[2]

KEYS = ["instrument_id", "report_date", "knowledge_date"]
SORT_KEYS = [*KEYS, "source_ticker"]


def scan_misplaced(
    partitions: dict[int, pl.DataFrame],
) -> dict[int, pl.DataFrame]:
    """各分区中报告期年 ≠ 分区年的错位行."""
    misplaced: dict[int, pl.DataFrame] = {}
    for part_year, df in partitions.items():
        wrong = df.filter(pl.col("report_date").dt.year() != part_year)
        if wrong.height:
            misplaced[part_year] = wrong
    return misplaced


def correct_rows(
    partitions: dict[int, pl.DataFrame], misplaced: dict[int, pl.DataFrame]
) -> pl.DataFrame:
    """全部「正确归位」行（非错位分区的行 + 错位分区中归属本区的行）."""
    return pl.concat(
        [df for year, df in partitions.items() if year not in misplaced]
        + [
            partitions[year].filter(pl.col("report_date").dt.year() == year)
            for year in misplaced
        ]
    )


def plan_repair(
    partitions: dict[int, pl.DataFrame],
    misplaced: dict[int, pl.DataFrame],
    *,
    allow_value_divergence: bool,
) -> tuple[int, pl.DataFrame, int]:
    """错位行分类：正确分区同键（双胞胎→删，须值一致）或没有（孤儿→移）."""
    correct = correct_rows(partitions, misplaced)
    twins = 0
    divergent = 0
    orphans = pl.DataFrame()
    for wrong in misplaced.values():
        joined = wrong.join(correct, on=KEYS, how="inner", suffix="_correct")
        orphan = wrong.join(correct.select(KEYS), on=KEYS, how="anti")
        if joined.height:
            value_cols = [c for c in wrong.columns if c not in KEYS]
            same_values = pl.all_horizontal(
                [pl.col(c).eq_missing(pl.col(f"{c}_correct")) for c in value_cols]
            )
            divergent += joined.filter(~same_values).height
        twins += joined.height
        if orphan.height:
            orphans = pl.concat([orphans, orphan])
    if divergent and not allow_value_divergence:
        raise SystemExit(
            f"{divergent} 行错位双胞胎与正确分区同键行的非键值列不一致; "
            "检查备份后以 --allow-value-divergence 放行, 按正确分区裁决"
        )
    return twins, orphans, divergent


def apply_repair(
    dataset_dir: Path,
    partitions: dict[int, pl.DataFrame],
    misplaced: dict[int, pl.DataFrame],
    orphans: pl.DataFrame,
) -> None:
    """受影响分区重写（错位分区 ∪ 孤儿目标分区）：删错位、收孤儿、全序落盘."""
    target_years = set(misplaced)
    if orphans.height:
        target_years |= set(orphans["report_date"].dt.year().unique().to_list())
    for part_year in sorted(target_years):
        df = partitions[part_year]
        keep = df.filter(pl.col("report_date").dt.year() == part_year)
        moved_in = (
            orphans.filter(pl.col("report_date").dt.year() == part_year)
            if orphans.height
            else orphans
        )
        merged = pl.concat([keep, moved_in]) if moved_in.height else keep
        merged = merged.sort(SORT_KEYS)
        tmp = dataset_dir / f"{part_year}.parquet.tmp"
        merged.write_parquet(tmp)
        tmp.replace(dataset_dir / f"{part_year}.parquet")
        print(f"partition {part_year}: {df.height} -> {merged.height}")


def verify_repaired(
    dataset_dir: Path, total_before: int, deleted: int, moved: int
) -> None:
    """修复后校验：无错位、无跨分区同键、行数守恒（真实删除须显式 raise）."""
    after = {
        int(p.stem): pl.read_parquet(p) for p in sorted(dataset_dir.glob("*.parquet"))
    }
    total_after = sum(df.height for df in after.values())
    if total_after != total_before - deleted:
        raise SystemExit(f"行数守恒失败: {total_before} - {deleted} != {total_after}")
    for part_year, df in after.items():
        misplaced_after = df.filter(pl.col("report_date").dt.year() != part_year)
        if misplaced_after.height:
            raise SystemExit(
                f"partition {part_year} 仍有 {misplaced_after.height} 行错位"
            )
    dup = pl.concat([df.select(KEYS) for df in after.values()]).unique().height
    if dup != total_after:
        raise SystemExit(f"跨分区同键残留: unique={dup} total={total_after}")
    print(
        f"verified: total_rows={total_after} (deleted={deleted}, moved={moved}), "
        "no misplacement, no cross-partition dups"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-root",
        type=Path,
        default=ROOT / "data",
        help="state 数据根, 默认 <repo>/data",
    )
    parser.add_argument(
        "--apply", action="store_true", help="执行写入, 默认 dry-run 只报告"
    )
    parser.add_argument(
        "--allow-value-divergence",
        action="store_true",
        help="放行与正确分区同键但非键值列不一致的双胞胎, 按正确分区裁决",
    )
    args = parser.parse_args()

    dataset_dir = args.data_root / "fundamental" / "fina_indicator"
    partitions = {
        int(p.stem): pl.read_parquet(p) for p in sorted(dataset_dir.glob("*.parquet"))
    }
    total_before = sum(df.height for df in partitions.values())
    print(f"partitions={sorted(partitions)} total_rows={total_before}")

    misplaced = scan_misplaced(partitions)
    misplaced_total = sum(df.height for df in misplaced.values())
    print(f"misplaced_rows={misplaced_total} in partitions={sorted(misplaced)}")
    if not misplaced_total:
        print("nothing to do")
        return

    twins, orphans, divergent = plan_repair(
        partitions, misplaced, allow_value_divergence=args.allow_value_divergence
    )
    print(
        f"twin_deletions={twins} (value_divergent={divergent}) "
        f"orphan_moves={orphans.height}"
    )

    if not args.apply:
        print("dry-run: no changes written (pass --apply)")
        return

    apply_repair(dataset_dir, partitions, misplaced, orphans)
    verify_repaired(dataset_dir, total_before, twins, orphans.height)


if __name__ == "__main__":
    main()
