# Koubo-TTS

面向法律案例短视频的可移植口播稿生产流程。

这套仓库把案例读取、事实核验、口播改写、画面节点、进度管理和断点续写整理成一个可安装的 Codex / Claude Code Skill。它不会包含案件原文、当事人资料、照片或任何本机绝对路径。

## 能做什么

- 按素材清单原顺序逐案制作口播稿
- 以正文为准纠正错误文件名或外部标题
- 通过正文哈希识别完全重复的案例
- 采用「80%有温度的自然叙事＋20%视频钩子与节奏」的表达方式
- 强制核验金额、日期、案号、审级、裁判结果和法律适用时点
- 每篇输出标题、封面短句、口播稿、画面节点、事实核验和来源路径
- 每篇完成后更新进度表和续写指针，换电脑或换对话也能继续

## 安装 Skill

克隆仓库后，将 `skills/legal-case-video-writer` 整个目录复制到对应工具的技能目录。

Codex 默认目录：

```text
~/.codex/skills/legal-case-video-writer
```

Claude Code 常用目录：

```text
~/.claude/skills/legal-case-video-writer
```

也可以让 Codex 读取仓库中的 `skills/legal-case-video-writer/SKILL.md` 后按该流程工作。

## 新建案例项目

需要 Python 3.10 或更高版本：

```powershell
python scripts/init_case_project.py "D:\我的案例口播项目"
```

程序会建立：

```text
我的案例口播项目/
├─ 原始案例素材库/
├─ 正式稿/
├─ 案例口播稿生产规则.md
├─ 案例口播稿处理进度.md
└─ 下一篇从这里开始.md
```

把 Word、Markdown 或纯文本案例放入 `原始案例素材库`，再让模型使用 `$legal-case-video-writer` 按顺序处理即可。

## 检查项目

```powershell
python scripts/validate_case_project.py "D:\我的案例口播项目"
```

检查程序会核对正式稿编号、必要章节、来源路径字段以及进度指针，不会修改文件。

## 推荐提示词

```text
使用 $legal-case-video-writer，读取本项目的生产规则、处理进度和续写指针，从下一篇开始按素材原顺序连续处理。每篇先完整读取正文，以正文纠正标题，检查重复，再制作正式稿并更新进度。不要因完成一个小批次而停止，直到本次指定素材全部处理完。
```

## 隐私提示

不要把未公开案件材料、身份证件、客户信息、证据原件或律师工作底稿提交到公开仓库。建议素材目录加入项目自己的 `.gitignore`，或使用私有仓库。
