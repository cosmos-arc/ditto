#!/usr/bin/env python3
"""
数学学习计划读取工具

从学习计划 Markdown 文件中提取指定 Day 的任务，
供 Claude Code 或用户快速查询"今天该学什么"。

用法：
  # 查看今天（启动日 2026-03-17 + Day 偏移）
  python today.py

  # 查看指定 Day
  python today.py --day 42

  # 查看当前阶段概览
  python today.py --overview

  # 查看里程碑进度
  python today.py --milestones
"""

import argparse
import re
import sys
from datetime import date
from pathlib import Path

# 启动日期和学习计划文件路径
START_DATE = date(2026, 3, 17)
PLAN_FILE = (
    Path(__file__).parent.parent.parent
    / "docs"
    / "plans"
    / "2026-03-17-math-learning-plan.md"
)


def _read_plan() -> str:
    """读取学习计划文件"""
    if not PLAN_FILE.exists():
        # 尝试从参数或环境变量中查找
        alt = Path("/mnt/d/learning/math/chevy-math-learning/docs") / PLAN_FILE.name
        if alt.exists():
            return alt.read_text(encoding="utf-8")
        print(f"错误：学习计划文件不存在: {PLAN_FILE}")
        print("请将学习计划文件放在正确路径，或使用 --plan 参数指定")
        sys.exit(1)
    return PLAN_FILE.read_text(encoding="utf-8")


def day_to_date(day: int) -> date:
    """将 Day 编号转换为实际日期"""
    from datetime import timedelta

    return START_DATE + timedelta(days=day - 1)


def date_to_day(target: date) -> int:
    """将实际日期转换为 Day 编号"""
    delta = target - START_DATE
    return delta.days + 1


def get_current_day() -> int:
    """获取当前应该学习的 Day 编号"""
    today = date.today()
    day = date_to_day(today)
    return max(1, day)


def extract_day_tasks(content: str, day: int) -> list[str]:
    """提取指定 Day 的任务列表"""
    tasks = []

    # 匹配 "**Day XX**" 或 "**Day XX（周X）**" 模式
    pattern = rf"\*\*Day {day}[^*]*\*\*\s*(.+?)(?=\*\*Day|\Z)"
    match = re.search(pattern, content, re.DOTALL)

    if not match:
        return tasks

    section = match.group(1)

    # 提取 checkbox 任务
    checkboxes = re.findall(r"- \[ \]\s*(.+)", section)
    tasks.extend(checkboxes)

    # 提取普通列表项（非 checkbox 但是具体任务）
    list_items = re.findall(r"^- (.+?)(?=\n-|\n\n|\n[|#*])", section, re.MULTILINE)
    for item in list_items:
        item = item.strip()
        if item and item not in tasks and not item.startswith("["):
            if len(item) > 5 and not item.startswith(
                ("完成", "整理", "复习总结", "里程碑")
            ):
                tasks.append(item)

    return tasks


def extract_day_section(content: str, day: int) -> str:
    """提取指定 Day 的完整章节文本"""
    pattern = rf"\*\*Day {day}[^*]*\*\*(.+?)(?=\*\*Day|\Z)"
    match = re.search(pattern, content, re.DOTALL)
    if match:
        return match.group(0).strip()
    return ""


def extract_milestones(content: str) -> list[dict]:
    """提取所有里程碑"""
    milestones = []
    for match in re.finditer(r"- \[([ xX])\] 里程碑[：:]?\s*(.+)", content):
        done = match.group(1).lower() == "x"
        milestones.append({"done": done, "name": match.group(2).strip()})
    return milestones


def extract_phase_info(content: str) -> list[dict]:
    """提取阶段信息"""
    phases = []
    for match in re.finditer(
        r"## 阶段 (\d)[：:]\s*(.+?)(?=\n##|\Z)", content, re.DOTALL
    ):
        phase_num = int(match.group(1))
        phase_title = match.group(2).strip().split("\n")[0]
        phases.append({"num": phase_num, "title": phase_title})
    return phases


def cmd_today(args):
    """显示今日学习任务"""
    day = args.day or get_current_day()
    content = _read_plan()

    target_date = day_to_date(day)
    print(f"📅 Day {day} | {target_date} ({target_date.strftime('%A')})")
    print(f"📖 阶段: {_get_current_phase(content, day)}")
    print("=" * 55)

    section = extract_day_section(content, day)
    if section:
        # 清理 markdown 格式
        clean = re.sub(r"\*\*", "", section)
        clean = re.sub(r"`([^`]+)`", r"\1", clean)
        print(clean)
    else:
        print("❓ 未找到该 Day 的计划内容")
        print("   提示：可能是周末或休息日，请查看前后 Day 的安排")

    # 显示明天预告
    next_section = extract_day_section(content, day + 1)
    if next_section:
        next_tasks = extract_day_tasks(content, day + 1)
        if next_tasks:
            print(f"\n📝 明日 (Day {day + 1}) 预告:")
            for t in next_tasks[:3]:
                print(f"  - {t}")


def _get_current_phase(content: str, day: int) -> str:
    """推断当前阶段"""
    if day <= 14:
        return "阶段 0：基础唤醒"
    elif day <= 91:
        return "阶段 1：核心数学"
    elif day <= 168:
        return "阶段 2：量化金融数学"
    else:
        return "阶段 3：ML/AI 数学"


def cmd_overview(args):
    """显示当前阶段概览"""
    content = _read_plan()
    day = args.day or get_current_day()
    phases = extract_phase_info(content)

    print(f"📅 当前: Day {day} | {day_to_date(day)}")
    print("=" * 55)

    for phase in phases:
        phase_ranges = {0: (1, 14), 1: (15, 91), 2: (92, 168), 3: (169, 224)}
        start, end = phase_ranges.get(phase["num"], (0, 0))
        if start <= day <= end:
            progress = (day - start) / (end - start) * 100
            bar_len = 30
            filled = int(bar_len * progress / 100)
            bar = "█" * filled + "░" * (bar_len - filled)
            print(f"\n▶ {phase['title']}  ← 当前阶段")
            print(f"  [{bar}] {progress:.0f}%")
            print(f"  Day {start}-{end} ({day - start + 1}/{end - start + 1} 天)")
        else:
            status = "✅ 已完成" if day > end else "⏳ 未开始"
            print(f"\n  {phase['title']}  {status}")
            print(f"  Day {start}-{end}")


def cmd_milestones(args):
    """显示里程碑进度"""
    content = _read_plan()
    milestones = extract_milestones(content)

    print("🏆 里程碑进度")
    print("=" * 55)

    completed = 0
    for m in milestones:
        icon = "✅" if m["done"] else "⬜"
        completed += m["done"]
        print(f"  {icon} {m['name']}")

    total = len(milestones)
    if total > 0:
        pct = completed / total * 100
        print(f"\n📊 进度: {completed}/{total} ({pct:.0f}%)")


def main():
    parser = argparse.ArgumentParser(description="数学学习计划查询工具")
    parser.add_argument("--day", "-d", type=int, default=None, help="指定 Day 编号")
    parser.add_argument("--plan", "-p", default=None, help="学习计划文件路径")
    parser.add_argument("--overview", "-o", action="store_true", help="查看阶段概览")
    parser.add_argument(
        "--milestones", "-m", action="store_true", help="查看里程碑进度"
    )

    args = parser.parse_args()

    if args.plan:
        global PLAN_FILE
        PLAN_FILE = Path(args.plan)

    if args.milestones:
        cmd_milestones(args)
    elif args.overview:
        cmd_overview(args)
    else:
        cmd_today(args)


if __name__ == "__main__":
    main()
