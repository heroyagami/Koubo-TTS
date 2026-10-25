"""
tools/tts_batch.py
批量 TTS + Whisper srt 工具。

功能：
  1. 扫描 script_dir 下旧式 A###_*.md 和新式 YYYYMMDD-A###*.md（口播稿）
  2. 跳过"已完成"的（按 mp3/srt 是否存在 + mtime 早于 md）
  3. 跑鱼 TTS（多块拼接）
  4. 跑 Whisper small 出 srt
  5. 输出进度 + 跳过/失败清单

用法：
  python scripts/tts_batch.py --script-dir "D:\项目\正式稿" --out-dir "D:\项目\out"
  python scripts/tts_batch.py --only A002 A005   # 只跑指定
  python scripts/tts_batch.py --no-resume         # 强制重跑全部
"""
import os
import re
import io
import sys
import json
import hashlib
import time
import shutil
import argparse
import subprocess
import tempfile
import urllib.request
import urllib.error
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from opencc import OpenCC

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "正式稿"
OUT_DIR = PROJECT_ROOT / "out"
DEFAULT_ENV_PATH = PROJECT_ROOT / ".env"
LEGACY_NAME_RE = re.compile(r"^(A\d{3,})(?:_|-|｜)?(.+)$")
DATED_NAME_RE = re.compile(r"^(\d{8})-(A\d{3,})(.+)$")
EMOTION_TOKEN_RE = re.compile(r"\[(?:excited|laughing|curious|sad|angry|fearful|surprised|calm|serious|whispering)\]", re.I)
APPROVED_VALUE = "已审核"
TRADITIONAL_TO_SIMPLIFIED = OpenCC('t2s')


def load_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def resolve_binary(name: str, override: str | None = None) -> Path:
    if override:
        candidate = Path(override).expanduser()
        if candidate.is_file():
            return candidate.resolve()
        raise FileNotFoundError(f"找不到 {name}：{candidate}")
    found = shutil.which(name)
    if found:
        return Path(found).resolve()
    user_bin = Path.home() / "bin" / (f"{name}.exe" if os.name == "nt" else name)
    if user_bin.is_file():
        return user_bin.resolve()
    raise FileNotFoundError(f"找不到 {name}，请安装 FFmpeg 并加入 PATH，或使用 --{name} 指定路径")


def extract_script(md_path: Path) -> str:
    md = md_path.read_text(encoding="utf-8")
    m = re.search(
        r"^##\s*(?:完整)?\s*口播稿\s*$\r?\n(.*?)(?=^##(?:\s|$)|\Z)",
        md,
        re.MULTILINE | re.DOTALL,
    )
    if not m:
        raise ValueError(f"{md_path.name}: 找不到‘## 口播稿’到下一个二级标题的完整段落")
    return m.group(1).strip()


def parse_identity(md_path: Path) -> tuple[str, str]:
    """返回 (选择编号, 完整输出主文件名)。"""
    stem = md_path.stem
    dated = DATED_NAME_RE.fullmatch(stem)
    if dated:
        return dated.group(2), stem
    legacy = LEGACY_NAME_RE.match(stem)
    if legacy:
        return legacy.group(1), stem
    raise ValueError(f"{md_path.name}: 文件名必须是 A###_标题.md 或 YYYYMMDD-A###标题.md")


def is_approved(md_path: Path) -> bool:
    """所有稿件都必须显式标记为“审核状态：已审核”。"""
    text = md_path.read_text(encoding="utf-8")
    match = re.search(r"^(?:审核状态|status)\s*[:：]\s*(.+?)\s*$", text, re.M | re.I)
    return bool(match and match.group(1).strip() == APPROVED_VALUE)


def display_script(text: str) -> str:
    """字幕事实源：移除控制标记和 Markdown 排版，不改写原稿文字。"""
    clean = EMOTION_TOKEN_RE.sub('', text).replace('**', '').replace('`', '')
    return re.sub(r"[ \t]+", " ", clean).strip()


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def verified_outputs(report: Path, text: str, mp3: Path, srt: Path) -> bool:
    try:
        data = json.loads(report.read_text(encoding='utf-8'))
        return (data.get('script_sha256') == text_hash(text)
                and data.get('audio_sha256') == hashlib.sha256(mp3.read_bytes()).hexdigest()
                and data.get('srt_sha256') == hashlib.sha256(srt.read_bytes()).hexdigest()
                and data.get('alignment_confidence', 0) >= .90
                and not data.get('review_cues'))
    except (OSError, ValueError):
        return False


def normalize_char(char: str) -> str:
    return char.lower() if char.isalnum() or "\u4e00" <= char <= "\u9fff" else ""


def parse_srt_time(value: str) -> float:
    hours, minutes, rest = value.split(":")
    seconds, millis = rest.split(",")
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(millis) / 1000


def format_srt_time(value: float) -> str:
    millis = max(0, round(value * 1000))
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    seconds, millis = divmod(millis, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def valid_caption_timeline(srt: str, duration: float) -> bool:
    intervals = [tuple(parse_srt_time(x) for x in pair) for pair in re.findall(
        r'(\d\d:\d\d:\d\d,\d{3})\s*-->\s*(\d\d:\d\d:\d\d,\d{3})', srt)]
    previous_end = 0.0
    for start, end in intervals:
        if start < previous_end - .001 or end <= start or end > duration + .25:
            return False
        previous_end = end
    return bool(intervals) and abs(duration - previous_end) <= 2


@dataclass
class TimedChar:
    char: str
    start: float
    end: float


def parse_asr_srt(srt_text: str) -> list[TimedChar]:
    """把 Whisper 临时 SRT 展开为带时间的识别字符，仅用于对齐。"""
    timed: list[TimedChar] = []
    blocks = re.split(r"\r?\n\s*\r?\n", TRADITIONAL_TO_SIMPLIFIED.convert(srt_text).strip())
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        time_index = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if time_index is None:
            continue
        start_raw, end_raw = [part.strip().split()[0] for part in lines[time_index].split("-->")]
        start, end = parse_srt_time(start_raw), parse_srt_time(end_raw)
        chars = [c for c in "".join(lines[time_index + 1:]) if normalize_char(c)]
        if not chars:
            continue
        span = max(0.001, end - start)
        for index, char in enumerate(chars):
            timed.append(TimedChar(char, start + span * index / len(chars), start + span * (index + 1) / len(chars)))
    return timed


def source_units(text: str) -> list[tuple[int, str]]:
    return [(index, normalize_char(char)) for index, char in enumerate(text) if normalize_char(char)]


def align_source_times(source: str, asr_chars: list[TimedChar]) -> tuple[dict[int, tuple[float, float]], float]:
    units = source_units(source)
    if not units or not asr_chars:
        raise ValueError("原稿或 ASR 时间轴没有可对齐文字")
    source_norm = "".join(char for _, char in units)
    asr_norm = "".join(normalize_char(item.char) for item in asr_chars)
    matcher = SequenceMatcher(None, source_norm, asr_norm, autojunk=False)
    unit_times: dict[int, tuple[float, float]] = {}
    matched = 0
    for source_start, asr_start, length in matcher.get_matching_blocks():
        for offset in range(length):
            unit_times[source_start + offset] = (asr_chars[asr_start + offset].start, asr_chars[asr_start + offset].end)
            matched += 1
    confidence = matched / max(len(units), len(asr_chars))

    known = sorted(unit_times)
    for unit_index in range(len(units)):
        if unit_index in unit_times:
            continue
        left = next((idx for idx in reversed(known) if idx < unit_index), None)
        right = next((idx for idx in known if idx > unit_index), None)
        if left is not None and right is not None:
            ratio = (unit_index - left) / (right - left)
            anchor = unit_times[left][1] + (unit_times[right][0] - unit_times[left][1]) * ratio
            unit_times[unit_index] = (anchor, anchor)
        elif left is not None:
            unit_times[unit_index] = (unit_times[left][1], unit_times[left][1])
        elif right is not None:
            unit_times[unit_index] = (unit_times[right][0], unit_times[right][0])
    return {units[i][0]: value for i, value in unit_times.items()}, confidence


def split_caption_text(text: str, max_chars: int = 24) -> list[tuple[int, int, str]]:
    """按原稿标点和段落切字幕；返回原始字符范围，文字绝不来自 ASR。"""
    spans: list[tuple[int, int, str]] = []
    for match in re.finditer(r"[^\n]+", text):
        line = match.group().strip()
        if not line:
            continue
        line_offset = match.start() + len(match.group()) - len(match.group().lstrip())
        cursor = 0
        for sentence in re.finditer(r".+?(?:[。！？!?；;，,：:]|$)", line):
            piece = sentence.group().strip()
            if not piece:
                continue
            local_start = sentence.start() + len(sentence.group()) - len(sentence.group().lstrip())
            while len(piece) > max_chars:
                cut = max_chars
                spans.append((line_offset + local_start + cursor, line_offset + local_start + cursor + cut, piece[:cut]))
                piece, cursor = piece[cut:], cursor + cut
            if piece:
                spans.append((line_offset + local_start + cursor, line_offset + local_start + cursor + len(piece), piece))
            cursor = 0
    return spans


def caption_display_text(text: str, strip_ending_punctuation: bool = True) -> str:
    """只清理字幕末尾标点；TTS 原文保持不变，以保留停顿和语气。"""
    if not strip_ending_punctuation:
        return text
    return re.sub(r"[。！？!?；;，,：:、…]+([」』”’）】》]*)$", r"\1", text).strip()


def source_locked_srt(
    source: str,
    asr_srt: str,
    min_confidence: float = 0.55,
    strip_ending_punctuation: bool = True,
) -> tuple[str, float, list[int]]:
    timed_chars = parse_asr_srt(asr_srt)
    char_times, confidence = align_source_times(source, timed_chars)
    cues = []
    review: list[int] = []
    previous_end = 0.0
    for start_index, end_index, text in split_caption_text(source):
        relevant = [char_times[i] for i in range(start_index, end_index) if i in char_times]
        if relevant:
            start, end = relevant[0][0], relevant[-1][1]
        else:
            start = end = previous_end
        rendered_text = caption_display_text(text, strip_ending_punctuation)
        if not rendered_text or not source_units(rendered_text):
            continue
        cue_index = len(cues) + 1
        if not relevant:
            review.append(cue_index)
        start = max(previous_end, start)
        end = max(start + 0.12, end)
        previous_end = end
        cues.append(f"{cue_index}\n{format_srt_time(start)} --> {format_srt_time(end)}\n{rendered_text}")
    if confidence < min_confidence:
        review = list(range(1, len(cues) + 1))
    return "\n\n".join(cues) + "\n", confidence, review


def split_chunks(text: str, max_chars: int = 800) -> list[str]:
    chunks, buf = [], ""
    for para in [p.strip() for p in text.split("\n\n") if p.strip()]:
        if len(para) > max_chars:
            for s in re.split(r'(?<=[。！？])', para):
                if not s: continue
                if len(buf) + len(s) > max_chars and buf:
                    chunks.append(buf); buf = s
                else:
                    buf = buf + s
        else:
            if len(buf) + len(para) + 2 > max_chars and buf:
                chunks.append(buf); buf = para
            else:
                buf = f"{buf}\n\n{para}" if buf else para
    if buf: chunks.append(buf)
    return chunks


def call_tts(text: str, voice_id: str, key: str, model: str = "s2.1-pro-free") -> bytes:
    url = "https://api.fish.audio/v1/tts"
    payload = {
        "text": text,
        "format": "mp3",
        "mp3_bitrate": 128,
        "normalize": True,
        "latency": "normal",
        "reference_id": voice_id,
    }
    # 关键: model 是 HTTP header,不是 body 字段 (鱼官方文档示例)
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "model": model,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read()


def run_whisper(mp3_path: Path, ffmpeg_path: Path) -> str | None:
    """跑 Whisper 并返回临时 SRT 内容；不在输出目录保留 ASR 文本。"""
    with tempfile.TemporaryDirectory(prefix="whisper-timing-") as directory:
        temp_dir = Path(directory)
        cmd = [
            sys.executable, "-m", "whisper",
            str(mp3_path),
            "--model", "small",
            "--language", "Chinese",
            "--output_format", "json",
            "--word_timestamps", "True",
            "--output_dir", str(temp_dir),
            "--device", "cpu",
            "--task", "transcribe",
        ]
        try:
            env = os.environ.copy()
            env["PATH"] = str(ffmpeg_path.parent) + os.pathsep + env.get("PATH", "")
            subprocess.run(cmd, timeout=900, check=True, capture_output=True, env=env)
            generated = temp_dir / f"{mp3_path.stem}.json"
            if not generated.exists():
                return None
            data = json.loads(generated.read_text(encoding='utf-8-sig'))
            words = [word for segment in data.get('segments', []) for word in segment.get('words', [])]
            return '\n\n'.join(f"{i}\n{format_srt_time(w['start'])} --> {format_srt_time(w['end'])}\n{w['word']}" for i, w in enumerate(words, 1))
        except subprocess.CalledProcessError as e:
            print(f"  [whisper ERR] {e.stderr.decode()[:200] if e.stderr else e}")
            return None
        except subprocess.TimeoutExpired:
            print("  [whisper TIMEOUT] 15min")
            return None


def get_mp3_duration(mp3_path: Path, ffprobe_path: Path) -> float | None:
    try:
        out = subprocess.check_output([
            str(ffprobe_path), "-v", "error", "-show_entries", "format=duration",
            "-of", "csv=p=0", str(mp3_path)
        ], timeout=10).strip()
        return float(out)
    except Exception:
        return None


def process_one(
    md_path: Path,
    voice_id: str,
    key: str,
    model: str,
    out_dir: Path,
    resume: bool,
    ffmpeg_path: Path,
    ffprobe_path: Path,
    strip_caption_ending_punctuation: bool,
) -> str:
    """处理一篇。返回 'done' | 'skipped' | 'failed'。"""
    code, output_stem = parse_identity(md_path)
    mp3 = out_dir / f"{output_stem}__{voice_id[:8]}_full.mp3"
    srt = mp3.with_suffix(".srt")
    report = out_dir / f"{output_stem}__{voice_id[:8]}_alignment.json"

    if not is_approved(md_path):
        print("  [WAIT] 审核状态不是‘已审核’，自动跳过，不配音")
        return "pending"

    text = extract_script(md_path).replace('**', '').replace('`', '')
    # 仅通过内容指纹验证的产物可以直接跳过，文件时间不足以证明同版本。
    if (
        resume
        and mp3.exists()
        and srt.exists()
        and report.exists()
        and verified_outputs(report, text, mp3, srt)
    ):
        return "skipped"

    chunks = split_chunks(text)
    print(f"  text: {len(text)} chars, {len(chunks)} chunks")

    # MP3 已成功而字幕缺失时，只续跑 ASR，避免重复调用 Fish Audio。
    try:
        prior = json.loads(report.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        prior = {}
    reuse_mp3 = (resume and mp3.exists()
                 and prior.get('script_sha256') == text_hash(text)
                 and prior.get('audio_sha256') == hashlib.sha256(mp3.read_bytes()).hexdigest())
    if resume and mp3.exists() and not reuse_mp3:
        print('  [REVIEW] 旧音频缺少与当前口播稿一致的内容指纹；请先核查，或用 --no-resume 明确重新生成')
        return 'failed'
    if reuse_mp3:
        print(f"  TTS: 复用已有 MP3（{mp3.stat().st_size//1024} KB），不重复调用 Fish Audio")
    else:
        mp3_parts = []
        t0 = time.time()
        for i, ch in enumerate(chunks):
            try:
                data = call_tts(ch, voice_id, key, model)
                mp3_parts.append(data)
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", errors="replace")
                print(f"  [TTS ERR chunk {i+1}] HTTP {e.code}  {body[:200]}")
                return "failed"
            except urllib.error.URLError as e:
                print(f"  [TTS ERR chunk {i+1}] NETWORK {e.reason}")
                return "failed"
        final = b"".join(mp3_parts)
        out_dir.mkdir(parents=True, exist_ok=True)
        mp3.write_bytes(final)
        report.write_text(json.dumps({'script_sha256': text_hash(text),
            'audio_sha256': hashlib.sha256(final).hexdigest()}, indent=2), encoding='utf-8')
        tts_dur = time.time() - t0
        real_dur = get_mp3_duration(mp3, ffprobe_path) or 0
        print(f"  TTS: {len(final)//1024} KB, ~{real_dur:.1f}s audio, took {tts_dur:.1f}s")

    # 跑 Whisper srt
    print(f"  Whisper small...")
    t0 = time.time()
    raw_srt_text = run_whisper(mp3, ffmpeg_path)
    if raw_srt_text:
        _, raw_confidence = align_source_times(display_script(text), parse_asr_srt(raw_srt_text))
        if raw_confidence < .90:
            print(f'  [REVIEW] 音频识别与原稿匹配度仅 {raw_confidence:.1%}，保留原字幕，需复核')
            return 'failed'
        final_srt, confidence, review = source_locked_srt(
            display_script(text),
            raw_srt_text,
            strip_ending_punctuation=strip_caption_ending_punctuation,
        )
        duration = get_mp3_duration(mp3, ffprobe_path)
        if duration is None or not valid_caption_timeline(final_srt, duration):
            print('  [REVIEW] 字幕时间倒退、重叠或与音频时长不符，保留原字幕')
            return 'failed'
        srt.write_text(final_srt, encoding="utf-8")
        report.write_text(json.dumps({
            "source": str(md_path),
            "audio": str(mp3),
            "asr_timing_source": "whisper temporary output (not retained)",
            "subtitle_text_source": "approved_script",
            "caption_ending_punctuation": "stripped" if strip_caption_ending_punctuation else "preserved",
            "alignment_confidence": round(confidence, 4),
            "review_cues": review,
            "source_mtime_ns": md_path.stat().st_mtime_ns,
            "script_sha256": text_hash(text),
            "audio_sha256": hashlib.sha256(mp3.read_bytes()).hexdigest(),
            "srt_sha256": hashlib.sha256(srt.read_bytes()).hexdigest(),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  srt: {srt.stat().st_size} bytes, alignment={confidence:.1%}, review={review or '(无)'}, took {time.time()-t0:.1f}s")
        return "done"
    return "failed"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--script-dir", default=str(SCRIPTS_DIR))
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    ap.add_argument("--voice-id", help="Fish Audio reference_id；也可用 FISH_AUDIO_REFERENCE_ID")
    ap.add_argument("--model", help="Fish Audio model header；默认 s2.1-pro-free")
    ap.add_argument("--env-file", default=str(DEFAULT_ENV_PATH), help="本地配置文件，默认仓库根目录 .env")
    ap.add_argument("--ffmpeg", help="ffmpeg 可执行文件路径；默认从 PATH 查找")
    ap.add_argument("--ffprobe", help="ffprobe 可执行文件路径；默认从 PATH 查找")
    ap.add_argument("--resume", action="store_true", default=True, help="跳过已生成的篇目（默认）")
    ap.add_argument("--no-resume", dest="resume", action="store_false")
    ap.add_argument("--only", nargs="*", help="只跑指定 A 编号（如 A002 A005）")
    ap.add_argument("--dry-run", action="store_true", help="只列计划不跑")
    ap.add_argument(
        "--keep-caption-ending-punctuation",
        action="store_true",
        help="保留每条字幕末尾标点；默认去掉句末标点，但配音原文标点仍保留",
    )
    args = ap.parse_args()

    script_dir = Path(args.script_dir)
    out_dir = Path(args.out_dir)
    file_env = load_env_file(Path(args.env_file).expanduser())
    voice_id = args.voice_id or os.environ.get("FISH_AUDIO_REFERENCE_ID") or file_env.get("FISH_AUDIO_REFERENCE_ID", "")
    model = args.model or os.environ.get("FISH_AUDIO_MODEL") or file_env.get("FISH_AUDIO_MODEL", "s2.1-pro-free")

    # 同时兼容旧式和带日期的新式文件名。
    targets: list[Path] = []
    for md in sorted(script_dir.glob("*.md")):
        if not (LEGACY_NAME_RE.match(md.stem) or DATED_NAME_RE.fullmatch(md.stem)):
            continue
        if not re.search(r"^##\s*(?:完整)?\s*口播稿", md.read_text(encoding="utf-8"), re.MULTILINE):
            continue
        if args.only:
            code, output_stem = parse_identity(md)
            if code not in args.only and output_stem not in args.only:
                continue
        targets.append(md)

    print(f"[OK] {len(targets)} 篇目标, voice_id: {voice_id[:8] + '…' if voice_id else '(未配置)'}")
    print(f"[OK] out_dir: {out_dir}")
    if args.dry_run:
        for t in targets:
            state = "已审核" if is_approved(t) else "待审核"
            print(f"  - {t.stem} [{state}]")
        return

    # 全部待审核时无需读取密钥，更不会建立 Fish Audio 网络请求。
    has_approved = any(is_approved(path) for path in targets)
    if has_approved and not voice_id:
        ap.error("已审核稿件需要 --voice-id 或 FISH_AUDIO_REFERENCE_ID")
    key = ""
    ffmpeg_path = Path(args.ffmpeg) if args.ffmpeg else Path("ffmpeg")
    ffprobe_path = Path(args.ffprobe) if args.ffprobe else Path("ffprobe")
    if has_approved:
        key = os.environ.get("FISH_AUDIO_API_KEY") or file_env.get("FISH_AUDIO_API_KEY", "")
        if not key:
            ap.error("已审核稿件需要 FISH_AUDIO_API_KEY（环境变量或 .env）")
        ffmpeg_path = resolve_binary("ffmpeg", args.ffmpeg)
        ffprobe_path = resolve_binary("ffprobe", args.ffprobe)

    done, skipped, pending, failed = [], [], [], []
    overall_t = time.time()
    for i, md in enumerate(targets, 1):
        code, _ = parse_identity(md)
        print(f"\n=== [{i}/{len(targets)}] {code}  ({md.name}) ===")
        result = process_one(
            md,
            voice_id,
            key,
            model,
            out_dir,
            args.resume,
            ffmpeg_path,
            ffprobe_path,
            not args.keep_caption_ending_punctuation,
        )
        print(f"  → {result}")
        (done if result == "done" else skipped if result == "skipped" else pending if result == "pending" else failed).append(code)

    print(f"\n=== 完成 ===")
    print(f"  done:   {len(done)} 篇")
    print(f"  skipped: {len(skipped)} 篇")
    print(f"  pending: {len(pending)} 篇  →  {pending if pending else '(无)'}")
    print(f"  failed: {len(failed)} 篇  →  {failed if failed else '(无)'}")
    print(f"  total time: {(time.time()-overall_t)/60:.1f} min")


if __name__ == "__main__":
    main()
