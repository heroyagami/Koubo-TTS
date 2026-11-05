# Koubo-TTS

一套面向法律案例短视频的工作流：把案例材料整理成口播稿，经人工审核后生成配音、字幕和核查报告。适合律师本人不出镜，使用头像、字幕、图示和素材画面的账号。

**准备案例 → 按顺序写稿 → 人工审核 → 配音 → 字幕对齐 → 核查与试听 → 导入剪辑软件**

写稿由 AI 助手配合仓库中的 Skill 完成；配音与字幕由 Python 工具执行。本仓库不包含自动剪辑或视频渲染功能。

## 已有项目，从这里开始

| 要做什么 | 使用哪个工具 |
|---|---|
| 从上次停下的位置继续写稿 | `legal-case-video-writer` Skill，读取项目规则、进度与续写指针 |
| 给审核后的稿件配音、生成字幕 | `scripts/tts_batch.py` |
| 只更新旧字幕的末尾标点 | `scripts/update_caption_punctuation.py` |
| 检查字幕错字、版本与时间轴 | `scripts/audit_subtitles.py` |
| 根据真实音频重新识别可疑篇目 | `scripts/recheck_audio.py` |
| 检查音频能否完整解码 | `scripts/check_audio_decode.py` |

所有命令在仓库根目录运行。下文以 Windows PowerShell 为例，将 `D:\我的案例口播项目` 换成自己的项目目录。只改字幕标点时，直接看[已有字幕的标点更新](#已有字幕的标点更新)，无需重新配音。

## 第一次使用

### 1. 安装工具与依赖

需要 Python 3.10 或以上版本，以及包含 `ffmpeg`、`ffprobe` 的 FFmpeg 安装。

```powershell
git clone https://github.com/heroyagami/Koubo-TTS.git
Set-Location Koubo-TTS

python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\Activate.ps1

ffmpeg -version
ffprobe -version
```

如果无法激活环境，可将后文的 `python` 换成 `.\.venv\Scripts\python.exe`。配音工具需要 `ffmpeg` 和 `ffprobe` 加入 PATH，或通过 `--ffmpeg`、`--ffprobe` 指定路径。依赖中的 `imageio-ffmpeg` 不替代配音工具对 `ffprobe` 的要求。

Whisper 首次使用可能下载模型。仓库中的识别命令默认使用 CPU，长音频需要等待。

### 2. 配置配音服务

```powershell
Copy-Item .env.example .env
```

在本机 `.env` 中填写：

```dotenv
FISH_AUDIO_API_KEY=你的API密钥
FISH_AUDIO_REFERENCE_ID=你的声音reference_id
FISH_AUDIO_MODEL=s2.1-pro-free
```

`FISH_AUDIO_MODEL` 是当前脚本的默认配置，实际可用模型与费用以自己的 Fish Audio 账户为准。配音会将口播正文发送给 Fish Audio，`model` 通过 HTTP header 传递。

仅处理已有字幕或运行本地音频识别时，无需配置配音密钥。不要提交真实 `.env`，也不要公开自己的密钥和私人声音配置。

### 3. 准备案例项目

工具仓库与案例项目可以放在不同位置。建议把素材、正式稿和进度集中放在一个项目文件夹中。

```powershell
python scripts/init_case_project.py "D:\我的案例口播项目"
```

初始化工具建立以下目录和管理文件，不覆盖已有同名管理文件：

```text
我的案例口播项目/
├─ 原始案例素材库/
├─ 正式稿/
├─ 案例口播稿生产规则.md
├─ 案例口播稿处理进度.md
└─ 下一篇从这里开始.md
```

配音时再生成 `配音字幕/out`。已有项目直接沿用，不必重新初始化。

## 写稿、审核与续写

将 [skills/legal-case-video-writer](skills/legal-case-video-writer/SKILL.md) 整个文件夹连同 `references` 放入所用助手的 Skill 目录。该 Skill 可供 Codex、Claude Code 等支持 Skill 的助手使用，不必另装其他文风 Skill。

项目中的三份文件负责长期接续：

| 文件 | 作用 |
|---|---|
| `案例口播稿生产规则.md` | 文风、时长、事实边界、画面形式和交付要求 |
| `案例口播稿处理进度.md` | 记录完成项、重复项和缺材料项 |
| `下一篇从这里开始.md` | 记录下一编号、下一案例和素材路径 |

每次续写先读这三份文件，每完成一案更新进度与指针。按已确认的素材原顺序处理；标题与正文冲突时以正文为准；重复案例记录后跳过。

推荐提示词：

```text
使用 legal-case-video-writer Skill。
我的案例项目目录是 D:\我的案例口播项目。
先读取生产规则、处理进度和续写指针，从下一篇开始按素材原顺序处理。
每案完整读取正文，核对案名、金额、审级与裁判结论，检查重复，保留编号。
完成正式稿后更新进度和下一篇指针。新稿标为待审核，不直接配音。
```

默认表达为自然叙事80%、视频结构20%；初始化模板采用约5—7分钟的深度版。自己的项目规则可另行指定时长和表达方式，实际时长以配音为准。

### 正式稿格式

推荐文件名为 `A001_标题.md`。配音工具也支持 `20261105-A001标题.md`。

```markdown
# A001｜标题

审核状态：待审核

## 三个标题候选
1. 标题一
2. 标题二
3. 标题三

## 封面短句
封面文字

## 完整口播稿
这里填写实际需要朗读的正文。

## 画面节点建议
6—10个画面节点。

## 事实核验
核对日期、金额、案号、审级、裁判结果和法律适用时点。

## 原始案例来源
`原始案例素材库/对应材料文件`
```

人工审核后，将状态改成 `审核状态：已审核`。其他状态或缺少状态时，配音工具会跳过。

配音工具只提取 `## 完整口播稿` 或 `## 口播稿` 下的内容，直到下一个二级标题或文件末尾。朗读提示、画面指令和来源说明应放在正文区以外。

检查标准结构：

```powershell
python scripts/validate_case_project.py "D:\我的案例口播项目"
```

此检查器当前按 `A###_标题.md` 和上述标准章节检查，不覆盖配音工具支持的所有历史命名与章节变体，也不能代替事实审核。

## 配音与字幕生成

先预览计划，不调用配音接口：

```powershell
python scripts/tts_batch.py `
  --script-dir "D:\我的案例口播项目\正式稿" `
  --out-dir "D:\我的案例口播项目\配音字幕\out" `
  --only A001 A002 `
  --dry-run
```

确认后去掉 `--dry-run` 执行。省略 `--only` 会扫描目录中所有符合命名条件的稿件。同一编号有多个版本时，`--only A001` 可能选中多个文件；也可以传入完整文件主名选择具体版本。

输出文件保留编号和标题：

```text
A001_标题__声音ID前8位_full.mp3
A001_标题__声音ID前8位_full.srt
A001_标题__声音ID前8位_alignment.json
```

MP3 是配音，SRT 是导入剪辑软件的字幕，对齐报告记录来源、内容指纹、匹配度和待复核项。

字幕文字取自原稿；Whisper 根据真实音频提供逐词时间，未匹配的字符由相邻识别位置插值定位。工具检查匹配度、连续缺读或多读、时间重叠和尾段时长。自动通过仍需要试听，尤其是姓名、金额、日期、法律术语和分块衔接处。

### 字幕标点规则

| 原稿 | 默认字幕显示 |
|---|---|
| `这笔钱能分。` | `这笔钱能分` |
| `先看流水，` | `先看流水` |
| `凭什么？` | `凭什么？` |
| `别急！` | `别急！` |
| `等等……` | `等等……` |
| `他说“可以。”` | `他说“可以”` |

默认仅省略每条字幕末尾的逗号、句号，保留问号、感叹号、省略号、冒号、分号、引号和书名号。句内标点、小数点不删除。配音原稿保留标点控制停顿和语气。

若希望连末尾逗号、句号也保留，在配音命令中加入 `--keep-caption-ending-punctuation`。

### 续跑与重新配音

默认开启续跑。只有正文、音频、字幕指纹和标点策略符合记录，匹配度达标且无待复核项，才跳过该篇。

- 音频与当前正文指纹一致：可复用音频，继续生成字幕。
- 正文改过、音频被替换或旧记录缺少必要指纹：提示复核，不仅凭文件时间判断版本。
- 只改字幕标点：使用下一节的工具。
- 确定重新配音：限定 `--only`，加入 `--no-resume`。这会重新请求 Fish Audio，并覆盖所选稿件的同名输出；先另存需要保留的版本。

## 已有字幕的标点更新

先预览：

```powershell
python scripts/update_caption_punctuation.py "D:\我的案例口播项目"
```

确认后备份并修改：

```powershell
python scripts/update_caption_punctuation.py "D:\我的案例口播项目" --apply
```

处理 `配音字幕/out`、`preview`、`临时输出` 中的 SRT，历史备份不修改。

只修改字幕末尾显示标点，不改正文文字、分条、时间轴和音频。旧规则删掉的语气标点，仅在字幕全文与对应原稿文字精确对应时恢复；无可靠原稿或全文不一致时，不猜测添加。

文件清单见 `配音字幕/字幕标点更新报告.json`，原文件保存在 `配音字幕/字幕标点备份/时间戳/`。原有音频待复核事项继续保留。

## 字幕对不上音频时

先分清是字幕错字、时间轴错位、版本不符，还是音频本身漏读、重复。

### 1. 核查现有文件

```powershell
python scripts/audit_subtitles.py "D:\我的案例口播项目"
python scripts/check_audio_decode.py "D:\我的案例口播项目"
```

查看 `配音字幕/字幕全量核查报告.md` 和 `.json`。核查工具会写入报告，但不修改字幕。解码结果见 `配音字幕/音频解码检查.json`；能够解码只说明文件可读取，不代表朗读正确。

### 2. 独立识别可疑篇目

```powershell
python scripts/recheck_audio.py "D:\我的案例口播项目" A001 A002
python scripts/audit_subtitles.py "D:\我的案例口播项目"
```

独立识别读取 `配音字幕/out` 中对应编号的音频，将结果保存到 `配音字幕/音频复核`，不重新配音。默认复用已有识别结果；加入 `--force` 可重新识别并保留上一版结果。后续核查优先使用独立识别数据。

### 3. 修复能够确认的字幕问题

```powershell
python scripts/audit_subtitles.py "D:\我的案例口播项目" --repair
```

符合匹配度与时间轴要求、无连续朗读差异的字幕才自动修复，修改前备份到 `配音字幕/字幕修复备份`。有逐词识别数据时据此重建，否则沿用原字幕的识别时间边界。

如果音频疑似漏读、重复或属于另一稿件版本，应按报告时间点听音确认。把原稿套到字幕上不能修复错误音频；需要重配时，再执行限定篇目的配音命令。

## 换电脑或移动项目

GitHub 保存工具、Skill、模板和测试，**不会自动同步本机的案例材料、正式稿、进度或音频**。

换电脑时，在新电脑克隆仓库、安装依赖与 FFmpeg，单独配置 `.env`，再复制完整案例项目及需要保留的识别数据、报告和备份。更新命令中的项目路径；项目文件、报告中的旧绝对路径也要检查。

更新工具：

```powershell
git pull
python -m pip install -r requirements.txt
```

如本机改过仓库文件，先保留这些改动再更新。原始素材、正式稿、MP3、SRT 和常见本地配置已列入忽略规则，但报告等其他文件仍需自己确认是否适合公开。

## 常见问题

**显示 `pending`，没有配音**：检查稿件中是否有精确的 `审核状态：已审核`。

**找不到 FFmpeg**：检查 `ffmpeg -version`、`ffprobe -version`，或用 `--ffmpeg`、`--ffprobe` 指定路径。

**配音成功，字幕失败**：重新执行同一命令。音频与当前正文指纹一致时可复用；若提示复核，先看报告，不要为了重做字幕直接强制重新配音。

**更新代码后旧字幕没变化**：代码更新不会自动改写磁盘上的历史字幕，请运行标点更新工具。

**匹配度很高，是否就能发布**：还需核对连续差异和实际朗读。全局匹配度、时间轴结构与总时长均不能替代试听。

## 工具索引与测试

| 路径 | 用途 |
|---|---|
| [写稿 Skill](skills/legal-case-video-writer/SKILL.md) | 写稿、去重、顺序处理与进度维护 |
| [init_case_project.py](scripts/init_case_project.py) | 新建项目目录和管理文件 |
| [validate_case_project.py](scripts/validate_case_project.py) | 标准稿件结构检查 |
| [tts_batch.py](scripts/tts_batch.py) | 配音与字幕对齐 |
| [update_caption_punctuation.py](scripts/update_caption_punctuation.py) | 保持时间轴不变，更新历史字幕标点 |
| [audit_subtitles.py](scripts/audit_subtitles.py) | 核查来源、文字、时间轴及音频差异 |
| [recheck_audio.py](scripts/recheck_audio.py) | 独立识别指定案例音频 |
| [check_audio_decode.py](scripts/check_audio_decode.py) | 完整解码检查 |

```powershell
python -m unittest discover -s tests -v
```

发布前人工核验案件事实、法律适用时点和裁判结论。只使用本人或获授权的声音；向配音服务发送正文前，确认其中不含不宜外传的客户资料。
