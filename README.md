# Koubo-TTS

面向法律案例短视频的可移植工作流：生成口播稿、人工审核、调用 Fish Audio 配音，再由 Whisper small 根据真实音频生成 SRT 时间轴。

> 核心原则：先生成真实 MP3，再做 ASR。字幕时间不按文本长度估算。

## 功能

- 按素材顺序生成法律案例口播稿，并记录处理进度
- 支持 `A127_标题.md` 和 `20260916-A127标题.md`
- 只有 `审核状态：已审核` 的稿件才能进入 TTS
- 仅提取 `## 口播稿` 或 `## 完整口播稿` 下的正文
- Fish Audio 分块配音，模型通过 HTTP header 传递
- Whisper small 从真实音频反推时间轴
- 最终 SRT 文字来自已审核原稿，ASR 只提供时间边界
- 默认去掉每条字幕末尾的标点，但TTS仍使用带标点原稿控制停顿和语气
- 支持 `--only`、断点续跑和只续跑缺失字幕
- 输出 MP3、SRT 和字幕对齐报告
- 输出文件名始终保留口播稿标题，不能只留下A编号和音色标识

## 项目结构

```text
Koubo-TTS/
├─ scripts/
│  ├─ init_case_project.py       # 初始化案例项目
│  ├─ validate_case_project.py   # 检查项目与稿件结构
│  └─ tts_batch.py               # Fish Audio + Whisper 批处理
├─ skills/
│  └─ legal-case-video-writer/   # Codex / Claude Code 写稿 Skill
├─ tests/
│  └─ test_tts_batch.py
├─ .env.example
├─ requirements.txt
└─ README.md
```

案件材料、正式稿、API Key、声音 ID、MP3 和 SRT 默认不进入 Git。

## 快速开始

### 1. 克隆仓库

```powershell
git clone https://github.com/heroyagami/Koubo-TTS.git
Set-Location Koubo-TTS
```

### 2. 创建 Python 环境

需要 Python 3.10 或更高版本。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 3. 安装 FFmpeg

Whisper 需要 `ffmpeg`，音频时长检查需要 `ffprobe`。

安装后确认：

```powershell
ffmpeg -version
ffprobe -version
```

如果没有加入 `PATH`，运行时可以显式传入：

```powershell
--ffmpeg "C:\tools\ffmpeg\bin\ffmpeg.exe" `
--ffprobe "C:\tools\ffmpeg\bin\ffprobe.exe"
```

### 4. 配置 Fish Audio

复制配置模板：

```powershell
Copy-Item .env.example .env
```

编辑 `.env`：

```text
FISH_AUDIO_API_KEY=你的API密钥
FISH_AUDIO_REFERENCE_ID=你的声音reference_id
FISH_AUDIO_MODEL=s2.1-pro-free
```

安全说明：

- `.env` 已加入 `.gitignore`
- 不要把真实 API Key 发到聊天、Issue 或提交记录
- `reference_id` 也建议作为私人配置保存
- 脚本不会把 `model` 放入请求 body，而是放在 Fish Audio HTTP header 中

## 新建案例项目

```powershell
python scripts\init_case_project.py "D:\我的案例口播项目"
```

生成结构：

```text
我的案例口播项目/
├─ 原始案例素材库/
├─ 正式稿/
├─ 案例口播稿生产规则.md
├─ 案例口播稿处理进度.md
└─ 下一篇从这里开始.md
```

检查项目：

```powershell
python scripts\validate_case_project.py "D:\我的案例口播项目"
```

## 正式稿要求

案例稿至少应包含：

```markdown
# A127｜标题

审核状态：待审核

## 三个标题候选

## 封面短句

## 完整口播稿

这里是唯一会送入 Fish Audio 的正文。

## 画面节点建议

## 事实核验

## 原始案例来源
```

人工核验事实、法律结论和朗读效果后，将状态改为：

```text
审核状态：已审核
```

其他状态或缺少审核状态时，脚本只会跳过，不会调用 Fish Audio。

## 配音与字幕

### 先检查计划

```powershell
python scripts\tts_batch.py `
  --script-dir "D:\我的案例口播项目\正式稿" `
  --out-dir "D:\我的案例口播项目\配音字幕\out" `
  --only A127 `
  --dry-run
```

### 正式执行

```powershell
python scripts\tts_batch.py `
  --script-dir "D:\我的案例口播项目\正式稿" `
  --out-dir "D:\我的案例口播项目\配音字幕\out" `
  --only A127
```

`--only A127` 既能匹配 `A127_标题.md`，也能匹配 `20260916-A127标题.md`。

### 批量执行

```powershell
python scripts\tts_batch.py `
  --script-dir "D:\我的案例口播项目\正式稿" `
  --out-dir "D:\我的案例口播项目\配音字幕\out" `
  --only A127 A128 A129
```

### 断点续跑

默认启用断点续跑：

```powershell
python scripts\tts_batch.py --script-dir "D:\项目\正式稿" --out-dir "D:\项目\out" --resume
```

- 只有口播正文、MP3、SRT 的 SHA-256 与对齐报告一致，且匹配度至少90%、无待复核条目，才整篇跳过
- 音频内容指纹与原稿记录一致但字幕缺失：复用 MP3，只重新运行 Whisper
- 旧音频缺少指纹、或原稿已改动：提示复核，不能根据修改时间自动认定可以复用
- 使用 `--no-resume`：强制重新生成

## 输出文件

### 历史产物全量检查

```powershell
python scripts/audit_subtitles.py "D:\我的案例口播项目"
python scripts/audit_subtitles.py "D:\我的案例口播项目" --repair
```

逐份检查正式稿、同名音频、字幕文本、字幕重叠和音频总时长，结果保存到项目内 `配音字幕/字幕全量核查报告.json`。
修复只适用于文字匹配度至少90%、时长合理的条目；修改前自动备份字幕及原报告。匹配度低、版本不同或缺少源稿时保留原文件并列为需复核。
若有保存的 Whisper 逐词时间数据，优先用于重建时间轴；否则沿用旧识别时间边界。自动检查通过不等于逐句试听通过。

需要独立核对可疑音频时：

```powershell
python scripts/recheck_audio.py "D:\我的案例口播项目" A018 A124
```

该命令使用本地 Whisper small 重新识别，结果保存到 `配音字幕/音频复核`，不调用配音服务。完成后再次运行核查命令，会优先使用这份独立识别数据；音色试听和临时输出也会列入检查。依赖已包含 `imageio-ffmpeg`。

普通正式稿输出：

```text
A127_拒绝亲子鉴定就一定会败诉吗口播稿__<reference前8位>_full.mp3
A127_拒绝亲子鉴定就一定会败诉吗口播稿__<reference前8位>_full.srt
A127_拒绝亲子鉴定就一定会败诉吗口播稿__<reference前8位>_alignment.json
```

日期文件名同样保留完整主文件名：

```text
20260916-A127标题__<reference前8位>_full.mp3
20260916-A127标题__<reference前8位>_full.srt
20260916-A127标题__<reference前8位>_alignment.json
```

对齐报告包含：

- 原稿和音频路径
- 字幕文字来源
- 对齐置信度
- 建议人工复核的字幕编号

文件名中的中文标题直接来自已审核Markdown文件名，方便在资源管理器、剪辑软件和素材库中辨认内容。请在配音前先把正式稿文件名改成最终标题。

## 常用参数

| 参数 | 作用 |
|---|---|
| `--script-dir` | 正式稿目录 |
| `--out-dir` | MP3、SRT 和报告输出目录 |
| `--only A127 A128` | 只处理指定编号 |
| `--dry-run` | 只显示计划，不调用 API |
| `--keep-caption-ending-punctuation` | 保留字幕末尾标点；默认不保留 |
| `--resume` | 断点续跑，默认启用 |
| `--no-resume` | 强制重做 |
| `--voice-id` | 临时覆盖 `FISH_AUDIO_REFERENCE_ID` |
| `--model` | 临时覆盖 `FISH_AUDIO_MODEL` |
| `--env-file` | 指定其他 `.env` 文件 |
| `--ffmpeg` | 指定 ffmpeg 路径 |
| `--ffprobe` | 指定 ffprobe 路径 |

## 常见问题

### Whisper 报 `FileNotFoundError`

通常是找不到 FFmpeg。先运行 `ffmpeg -version`，或者通过 `--ffmpeg`、`--ffprobe` 指定路径。

### Fish Audio 临时断线

重新运行同一条命令即可。已生成的 MP3 会被复用，不会因为字幕阶段失败而重复调用 TTS。

### 稿件显示 `pending`

确认稿件中存在且仅存在：

```text
审核状态：已审核
```

`已通过`、`待审核` 或缺少状态都不会配音。

### SRT 中有错字吗

最终字幕文字来自审核后的口播稿，不直接采用 Whisper 的识别文字。仍应检查对齐报告中的 `review_cues`，并重点试听低置信度篇目。

### 字幕末尾为什么没有标点

这是默认的视频字幕显示规则。句号、逗号、问号等仍保留在送给 Fish Audio 的文本中，用于控制配音停顿和语气，只在最终 SRT 的每条字幕末尾隐藏。需要保留时增加 `--keep-caption-ending-punctuation`。

## 运行测试

```powershell
python -m unittest discover -s tests -v
python -m py_compile scripts\tts_batch.py
```

## Skill 使用

将 `skills/legal-case-video-writer` 复制到相应工具的 Skill 目录：

```text
Codex:       ~/.codex/skills/legal-case-video-writer
Claude Code: ~/.claude/skills/legal-case-video-writer
```

推荐提示词：

```text
使用 $legal-case-video-writer，读取本项目的生产规则、处理进度和续写指针，从下一篇开始按素材原顺序连续处理。每篇完整读取正文，以正文纠正标题，检查重复，再制作正式稿并更新进度。
```

## 隐私与授权

- 只克隆和使用本人或明确授权的声音
- 不要向公开仓库提交未公开案件材料、客户信息、身份证件或证据原件
- 发布前人工核验事实、法律适用时点、案号、金额和裁判结论
- AI 生成内容和 ASR 时间轴都需要人工抽查
