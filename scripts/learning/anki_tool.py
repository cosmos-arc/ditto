#!/usr/bin/env python3
"""
Anki 自动化工具 — 通过 AnkiConnect API 操作 Anki

使用前：
  1. 安装 Anki 桌面端 (https://apps.ankiweb.net/)
  2. 安装 AnkiConnect 插件（插件代码：2055492159）
  3. 确保 Anki 正在运行

用法：
  python anki_tool.py status                          # 查看 Anki 连接状态
  python anki_tool.py decks                           # 列出所有 Deck
  python anki_tool.py create-deck "Math::微积分"      # 创建 Deck
  python anki_tool.py add "Math::微积分"             # 添加单张卡片
    --front "链式法则的直觉是什么？"
    --back "复合函数的导数 = 外函数导数 × 内函数导数"
  python anki_tool.py add-csv /path/to/cards.csv      # 从 CSV 批量添加
  python anki_tool.py stats                           # 查看学习统计
"""

import argparse
import json
import sys
import urllib.error
import urllib.request

ANKI_CONNECT_URL = "http://localhost:8765"

# 数学卡片模型 — 优先使用已有的"问答题"模型
MATH_MODEL_NAME = "问答题"
# AnkiConnect 中 createModel 的字段名是 css/html/...
# 如果已有模型则直接复用


def _request(action: dict, timeout: int = 10) -> dict:
    """向 AnkiConnect 发送请求"""
    payload = json.dumps(
        {"action": action["action"], "version": 6, "params": action.get("params", {})}
    ).encode("utf-8")
    req = urllib.request.Request(
        ANKI_CONNECT_URL, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        # 绕过系统代理（WSL2 mirrored 模式下代理会拦截 localhost 请求）
        proxy_handler = urllib.request.ProxyHandler({})
        opener = urllib.request.build_opener(proxy_handler)
        with opener.open(req, timeout=timeout) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError:
        print("错误：无法连接到 Anki。请确认：")
        print("  1. Anki 桌面端正在运行")
        print("  2. AnkiConnect 插件已安装（插件代码：2055492159）")
        sys.exit(1)
    if result.get("error"):
        print(f"AnkiConnect 错误：{result['error']}")
        sys.exit(1)
    return result.get("result", {})


def _ensure_math_model() -> str:
    """确保数学学习笔记类型存在，返回模型名称"""
    models = _request({"action": "modelNames"})
    if MATH_MODEL_NAME in models:
        return MATH_MODEL_NAME
    print(f"错误：未找到 '{MATH_MODEL_NAME}' 模型。请先在 Anki 中确认存在该笔记类型。")
    print(f"当前可用模型: {models}")
    sys.exit(1)


def cmd_status(_args):
    """检查 Anki 连接状态"""
    try:
        result = _request({"action": "version"}, timeout=3)
        print(f"✅ Anki 已连接 (AnkiConnect 版本: {result})")
        decks = _request({"action": "deckNames"})
        print(f"📊 当前 Deck 数: {len(decks)}")
        card_count = _request({"action": "findCards", "params": {"query": ""}})
        print(f"📝 总卡片数: {card_count}")
    except SystemExit:
        raise
    except Exception as e:
        print(f"❌ 连接失败: {e}")


def cmd_decks(_args):
    """列出所有 Deck"""
    decks = _request({"action": "deckNames"})
    deck_info = _request({"action": "deckNamesAndIds"})
    print("📋 Anki Decks:")
    print("-" * 50)
    for name in sorted(decks):
        did = deck_info[name]
        query = f'"deck:{name}"'
        count = _request({"action": "findCards", "params": {"query": query}})
        print(f"  {name} ({len(count)} cards) [id: {did}]")
    print("-" * 50)
    print(f"共 {len(decks)} 个 Deck")


def cmd_create_deck(args):
    """创建 Deck"""
    deck_name = args.deck_name
    _request({"action": "createDeck", "params": {"deck": deck_name}})
    print(f"✅ Deck 已创建: {deck_name}")


def cmd_add(args):
    """添加单张卡片"""
    _ensure_math_model()
    note = {
        "deckName": args.deck,
        "modelName": MATH_MODEL_NAME,
        "fields": {"正面": args.front, "背面": args.back},
        "tags": args.tags.split(",") if args.tags else [],
    }
    _request({"action": "addNote", "params": {"note": note}})
    print(f"✅ 卡片已添加到 {args.deck}")
    print(f"   正面: {args.front[:50]}...")
    print(f"   背面: {args.back[:50]}...")


def cmd_add_csv(args):
    """从 CSV 批量添加卡片

    CSV 格式: deck,front,back,tags
    示例: Math::微积分,链式法则的直觉是什么？,复合函数导数=外导×内导,calculus;chain-rule
    """
    import csv

    filepath = args.csv_file
    added = 0
    skipped = 0
    with open(filepath, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row_num, row in enumerate(reader, 2):
            deck = row.get("deck", "Math::Default")
            front = row.get("front", "").strip()
            back = row.get("back", "").strip()
            tags_str = row.get("tags", "")
            if not front or not back:
                print(f"⚠️  第 {row_num} 行跳过：正面或背面为空")
                skipped += 1
                continue
            tags = [t.strip() for t in tags_str.split(";") if t.strip()]
            note = {
                "deckName": deck,
                "modelName": MATH_MODEL_NAME,
                "fields": {"正面": front, "背面": back},
                "tags": tags,
            }
            try:
                _request({"action": "addNote", "params": {"note": note}})
                added += 1
            except SystemExit:
                raise
            except Exception as e:
                print(f"⚠️  第 {row_num} 行添加失败: {e}")
                skipped += 1

    print(f"\n📊 批量导入完成：✅ {added} 张成功，⚠️ {skipped} 张跳过")


def cmd_stats(_args):
    """查看学习统计"""
    # 获取今日复习统计
    today_reviews = _request({"action": "findCards", "params": {"query": "rated:1"}})
    print(f"📅 今日复习卡片数: {len(today_reviews)}")

    # 获取各 Deck 卡片数
    decks = _request({"action": "deckNames"})
    print("\n📊 各 Deck 卡片数:")
    print("-" * 40)
    for deck in sorted(decks):
        if "Math" in deck or "math" in deck:
            count = _request(
                {"action": "findCards", "params": {"query": f'"deck:{deck}"'}}
            )
            print(f"  {deck}: {len(count)}")
    print("-" * 40)


def main():
    parser = argparse.ArgumentParser(
        description="Anki 自动化工具（通过 AnkiConnect API）"
    )
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    subparsers.add_parser("status", help="检查 Anki 连接状态")
    subparsers.add_parser("decks", help="列出所有 Deck")
    subparsers.add_parser("stats", help="查看学习统计")

    p_deck = subparsers.add_parser("create-deck", help="创建 Deck")
    p_deck.add_argument("deck_name", help="Deck 名称，如 'Math::微积分'")

    p_add = subparsers.add_parser("add", help="添加单张卡片")
    p_add.add_argument("deck", help="目标 Deck")
    p_add.add_argument("--front", "-f", required=True, help="正面（问题）")
    p_add.add_argument("--back", "-b", required=True, help="背面（答案）")
    p_add.add_argument("--tags", "-t", default="", help="标签，逗号分隔")

    p_csv = subparsers.add_parser("add-csv", help="从 CSV 批量添加卡片")
    p_csv.add_argument("csv_file", help="CSV 文件路径")

    args = parser.parse_args()

    commands = {
        "status": cmd_status,
        "decks": cmd_decks,
        "stats": cmd_stats,
        "create-deck": cmd_create_deck,
        "add": cmd_add,
        "add-csv": cmd_add_csv,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
