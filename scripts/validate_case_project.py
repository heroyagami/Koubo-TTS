from __future__ import annotations

import argparse
import re
from pathlib import Path


REQUIRED_PROJECT_FILES = (
    "案例口播稿生产规则.md",
    "案例口播稿处理进度.md",
    "下一篇从这里开始.md",
)
REQUIRED_SECTIONS = (
    "## 三个标题候选",
    "## 封面短句",
    "## 完整口播稿",
    "## 画面节点建议",
    "## 事实核验",
    "## 原始案例来源",
)


def main() -> int:
    parser = argparse.ArgumentParser(description="检查法律案例口播稿项目结构")
    parser.add_argument("project_dir", type=Path)
    args = parser.parse_args()
    root = args.project_dir.expanduser().resolve()
    errors: list[str] = []

    for name in REQUIRED_PROJECT_FILES:
        if not (root / name).is_file():
            errors.append(f"缺少项目文件：{name}")

    drafts_dir = root / "正式稿"
    if not drafts_dir.is_dir():
        errors.append("缺少目录：正式稿")
    else:
        numbers: list[int] = []
        for draft in sorted(drafts_dir.glob("A[0-9][0-9][0-9]_*.md")):
            text = draft.read_text(encoding="utf-8")
            number = int(draft.name[1:4])
            numbers.append(number)
            for section in REQUIRED_SECTIONS:
                if text.count(section) != 1:
                    errors.append(f"{draft.name} 的章节数量异常：{section}")
            if not re.search(r"## 原始案例来源\s+`[^`]+`", text):
                errors.append(f"{draft.name} 缺少反引号包裹的来源路径")
        for previous, current in zip(numbers, numbers[1:]):
            if current <= previous:
                errors.append(f"正式稿编号重复或倒序：A{previous:03d}、A{current:03d}")

    if errors:
        print("检查未通过：")
        for error in errors:
            print(f"- {error}")
        return 1

    print("检查通过：项目文件和正式稿结构正常。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
