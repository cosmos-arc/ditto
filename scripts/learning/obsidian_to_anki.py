#!/usr/bin/env python3
"""
Obsidian 笔记 → Anki 卡片转换工具

从 Obsidian 仓库的每日笔记中提取标记为 [Anki 待生成] 的内容，
自动生成 Anki 卡片并写入 CSV 文件（可导入 Anki 或直接通过 AnkiConnect 添加）。

用法：
  # 扫描笔记生成 CSV（默认输出到 Obsidian 仓库 5-ANKI/ 目录）
  python obsidian_to_anki.py --vault /mnt/d/learning/math/chevy-math-learning

  # 生成后直接导入 Anki（需要 Anki 正在运行）
  python obsidian_to_anki.py --vault /mnt/d/learning/math/chevy-math-learning --import

  # 扫描指定日期
  python obsidian_to_anki.py --vault /mnt/d/learning/math/chevy-math-learning --date 2026-03-17
"""

import argparse
import csv
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# Anki 卡片 CSV 表头
CSV_HEADER = ["deck", "front", "back", "tags"]

# 默认 Deck 前缀
DEFAULT_DECK_PREFIX = "Math"

# 阶段对应 Deck 映射
PHASE_DECK_MAP = {
    "阶段 0": "Math::Phase0-基础唤醒",
    "阶段 1": "Math::Phase1-核心数学",
    "阶段 2": "Math::Phase2-量化金融",
    "阶段 3": "Math::Phase3-ML-AI",
}


def parse_frontmatter(content: str) -> dict:
    """解析 Markdown frontmatter"""
    match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return {}
    fm = {}
    for line in match.group(1).strip().split("\n"):
        if ":" in line:
            key, _, value = line.partition(":")
            fm[key.strip()] = value.strip().strip('"')
    return fm


def extract_anki_items(content: str, frontmatter: dict) -> list[dict]:
    """从笔记内容中提取 [Anki 待生成] 下的条目"""
    items = []

    # 匹配 "## Anki 待生成" 或 "### Anki 待生成" 下方的列表项
    anki_section = re.search(
        r"#{1,3}\s*Anki 待生成\s*\n((?:\s*-\s*\[.\]\s*.*\n?)+)",
        content,
        re.IGNORECASE,
    )
    if not anki_section:
        return items

    section_text = anki_section.group(1)
    # 提取未完成（[ ]）的条目
    entries = re.findall(r"-\s*\[\s\]\s*(.+)", section_text)

    phase = frontmatter.get("phase", "阶段 1")
    topic = frontmatter.get("topic", "")
    deck = PHASE_DECK_MAP.get(phase, f"Math::{phase}")
    if topic:
        deck = f"{deck}::{topic}"

    tags = []
    if phase:
        tags.append(phase.replace(" ", "-"))
    if topic:
        tags.append(topic)

    for entry in entries:
        entry = entry.strip()
        if not entry:
            continue

        # 如果条目中包含 "："或 ":"，前半部分作为正面，后半部分作为背面
        if "：" in entry or ":" in entry:
            sep = "：" if "：" in entry else ":"
            parts = entry.split(sep, 1)
            front = parts[0].strip()
            back = parts[1].strip()
        else:
            # 没有分隔符的条目，正面是问题形式，背面需要标注待补充
            front = entry
            back = "（待补充答案 — 请手动填写或在笔记中用 '：' 分隔问题和答案）"

        items.append(
            {"deck": deck, "front": front, "back": back, "tags": ";".join(tags)}
        )

    return items


def extract_concept_cards(content: str) -> list[dict]:
    """从概念笔记中提取结构化卡片"""
    items = []

    fm = parse_frontmatter(content)
    tags_raw = fm.get("tags", [])
    if isinstance(tags_raw, str):
        tags_list = [t.strip() for t in tags_raw.strip("[]").split(",")]
    else:
        tags_list = tags_raw

    # 提取 "一句话直觉" 作为直觉卡片
    intuition_match = re.search(r"##\s*一句话直觉\s*\n>\s*(.+)", content)
    if intuition_match:
        title_match = re.search(r"^#\s+(.+)", content, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else "Unknown"
        items.append(
            {
                "deck": _get_deck_from_tags(tags_list),
                "front": f"[直觉] {title} 用一句话怎么解释？",
                "back": intuition_match.group(1).strip(),
                "tags": ";".join(tags_list + ["intuition"]),
            }
        )

    # 提取 "常见误区" 作为辨析卡片
    misconception_section = re.search(
        r"##\s*常见误区\s*\n((?:.*\n?)+?)(?=\n##|\Z)",
        content,
    )
    if misconception_section:
        # 匹配 ❌/✅ 对
        pairs = re.findall(
            r"- ❌\s*(.+?)\n\s*- ✅\s*(.+)", misconception_section.group(1)
        )
        for wrong, correct in pairs:
            items.append(
                {
                    "deck": _get_deck_from_tags(tags_list),
                    "front": f"[辨析] {wrong.strip()}",
                    "back": f"❌ 错误理解\n✅ 正确理解：{correct.strip()}",
                    "tags": ";".join(tags_list + ["misconception"]),
                }
            )

    return items


def _get_deck_from_tags(tags: list[str]) -> str:
    """根据标签推断 Deck"""
    tag_to_phase = {
        "phase-0": "Math::Phase0-基础唤醒",
        "phase-1": "Math::Phase1-核心数学",
        "phase-2": "Math::Phase2-量化金融",
        "phase-3": "Math::Phase3-ML-AI",
    }
    for tag in tags:
        if tag in tag_to_phase:
            return tag_to_phase[tag]
    # 根据学科标签推断
    subject_tags = [
        "calculus",
        "linear-algebra",
        "probability",
        "time-series",
        "stochastic",
        "ml",
        "foundation",
    ]
    subject_map = {
        "calculus": "Math::Phase1-核心数学::微积分",
        "linear-algebra": "Math::Phase1-核心数学::线性代数",
        "probability": "Math::Phase1-核心数学::概率统计",
        "time-series": "Math::Phase2-量化金融::时间序列",
        "stochastic": "Math::Phase2-量化金融::随机微积分",
        "ml": "Math::Phase3-ML-AI",
        "foundation": "Math::Phase0-基础唤醒",
    }
    for tag in tags:
        if tag in subject_map:
            return subject_map[tag]
    return "Math::Default"


def scan_vault(vault_path: str, date_filter: str | None = None) -> list[dict]:
    """扫描 Obsidian 仓库，提取所有待生成的 Anki 卡片"""
    vault = Path(vault_path)
    all_cards = []

    # 1. 扫描每日笔记
    daily_dir = vault / "0-DAILY"
    if daily_dir.exists():
        for md_file in daily_dir.glob("*.md"):
            if date_filter and date_filter not in md_file.stem:
                continue
            content = md_file.read_text(encoding="utf-8")
            fm = parse_frontmatter(content)
            cards = extract_anki_items(content, fm)
            if cards:
                all_cards.extend(cards)
                # 标记已处理
                _mark_processed(md_file)

    # 2. 扫描概念笔记
    concepts_dir = vault / "1-CONCEPTS"
    if concepts_dir.exists():
        for md_file in concepts_dir.rglob("*.md"):
            content = md_file.read_text(encoding="utf-8")
            cards = extract_concept_cards(content)
            all_cards.extend(cards)

    return all_cards


def _mark_processed(filepath: Path):
    """将笔记中的 [Anki 待生成] 标记为已处理"""
    content = filepath.read_text(encoding="utf-8")
    # 将 [ ] 标记为 [x]（已处理）
    updated = re.sub(
        r"(##\s*Anki 待生成\s*\n(?:.*\n?)*)((?:\s*-\s*)\[\s\])",
        r"\1\2x",
        content,
    )
    if updated != content:
        filepath.write_text(updated, encoding="utf-8")


def write_csv(cards: list[dict], output_path: str):
    """将卡片写入 CSV 文件"""
    with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADER)
        writer.writeheader()
        writer.writerows(cards)
    print(f"📝 CSV 已写入: {output_path} ({len(cards)} 张卡片)")


def import_to_anki(csv_path: str):
    """通过 AnkiConnect 导入卡片"""
    # 动态导入 anki_tool
    script_dir = Path(__file__).parent
    sys.path.insert(0, str(script_dir))
    from anki_tool import cmd_add_csv

    class Args:
        def __init__(self, csv_file):
            self.csv_file = csv_file

    cmd_add_csv(Args(csv_path))


def main():
    parser = argparse.ArgumentParser(description="Obsidian 笔记 → Anki 卡片转换")
    parser.add_argument(
        "--vault",
        "-v",
        default="/mnt/d/learning/math/chevy-math-learning",
        help="Obsidian 仓库路径",
    )
    parser.add_argument(
        "--date", "-d", default=None, help="只处理指定日期的笔记（如 2026-03-17）"
    )
    parser.add_argument(
        "--output", "-o", default=None, help="CSV 输出路径（默认输出到 vault/5-ANKI/）"
    )
    parser.add_argument(
        "--import", dest="do_import", action="store_true", help="生成后直接导入 Anki"
    )
    parser.add_argument("--dry-run", action="store_true", help="只预览，不写入文件")

    args = parser.parse_args()

    vault_path = args.vault
    if not Path(vault_path).exists():
        print(f"错误：Obsidian 仓库不存在: {vault_path}")
        sys.exit(1)

    print(f"🔍 扫描 Obsidian 仓库: {vault_path}")
    if args.date:
        print(f"📅 日期过滤: {args.date}")

    cards = scan_vault(vault_path, args.date)

    if not cards:
        print("📭 没有找到待生成的 Anki 卡片")
        print("   提示：在 Obsidian 笔记中添加 ## Anki 待生成 部分，格式：")
        print("   - [ ] 问题：答案")
        return

    print(f"\n📊 找到 {len(cards)} 张待生成卡片：\n")
    for i, card in enumerate(cards, 1):
        print(f"  {i}. [{card['deck']}] {card['front'][:60]}...")

    if args.dry_run:
        print("\n🔍 Dry run 模式，未写入文件")
        return

    # 写入 CSV
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    default_output = os.path.join(vault_path, "5-ANKI", f"cards-{timestamp}.csv")
    output_path = args.output or default_output
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    write_csv(cards, output_path)

    # 可选：直接导入 Anki
    if args.do_import:
        print("\n📤 正在导入到 Anki...")
        import_to_anki(output_path)


if __name__ == "__main__":
    main()
