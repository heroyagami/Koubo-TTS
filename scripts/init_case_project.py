from __future__ import annotations

import argparse
from pathlib import Path


RULES = """# 案例口播稿生产规则

- 默认时长：5—7分钟深度版，最终以TTS试听为准。
- 表达比例：自然、有温度的叙事80%，视频钩子与节奏20%。
- 顺序规则：严格按照素材清单原始顺序逐案处理。
- 事实规则：完整读取正文，以正文纠正错误标题，核验金额、日期、案号、审级、裁判结果和法律时点。
- 去重规则：规范化正文SHA-256完全相同时，只制作一篇正式稿。
- 画面规则：律师本人不出镜，仅使用圆形头像、字幕、图示和素材画面。
- 交付结构：三个标题、封面短句、完整口播稿、6—10个画面节点、事实核验、原始来源路径。
- 续写规则：每篇完成后更新处理进度和下一篇指针。
- 禁止虚构数字、对话、心理、律师经历或案件细节，不扩大个案规则。
"""

PROGRESS = """# 案例口播稿处理进度

| 编号 | 案例 | 素材校验 | 状态 | 成稿 |
|---|---|---|---|---|
"""

POINTER = """# 下一篇从这里开始

- 当前状态：**等待处理素材**
- 已处理至：**尚未开始**
- 下一编号：**A001**
- 下一案例：**按素材清单第一项确定**
- 下一原始文件：**待确定**
- 原始文件目录：`原始案例素材库`
- 成稿目录：`正式稿`
- 更新时间：**请在首次处理时填写**

## 后续继续时必须执行

1. 读取《案例口播稿生产规则.md》《案例口播稿处理进度.md》和本文件。
2. 使用 `legal-case-video-writer` Skill。
3. 完整读取正文后再写，标题冲突时以正文为准。
4. 按素材原始顺序处理并记录重复项。
"""


def write_new(path: Path, content: str) -> None:
    if not path.exists():
        path.write_text(content, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="初始化法律案例口播稿项目")
    parser.add_argument("project_dir", type=Path)
    args = parser.parse_args()

    root = args.project_dir.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    (root / "原始案例素材库").mkdir(exist_ok=True)
    (root / "正式稿").mkdir(exist_ok=True)
    write_new(root / "案例口播稿生产规则.md", RULES)
    write_new(root / "案例口播稿处理进度.md", PROGRESS)
    write_new(root / "下一篇从这里开始.md", POINTER)
    print(f"项目已初始化：{root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
