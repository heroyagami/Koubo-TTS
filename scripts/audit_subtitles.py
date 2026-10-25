"""Audit existing captions against scripts; repair legacy ASR wording with backups."""
import argparse
import hashlib
import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from mutagen.mp3 import MP3
import tts_batch as t
try:
    from opencc import OpenCC
    converter = OpenCC('t2s')
except ImportError:
    converter = None


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(root, repair=False):
    out = root / '配音字幕' / 'out'
    if not out.is_dir() or not (root / '正式稿').is_dir():
        raise ValueError('项目目录必须包含正式稿与配音字幕/out')
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    backup = root / '配音字幕' / '字幕修复备份' / stamp
    rows = []
    caption_paths = sorted(out.glob('*.srt'))
    for folder in ['preview', '临时输出']:
        caption_paths.extend(sorted((root/'配音字幕'/folder).glob('*.srt')))
    for srt in caption_paths:
        row = {'file': srt.name, 'directory': str(srt.parent)}
        try:
            if not re.match(r'(?:A\d+_|\d{8}-A\d+)', srt.name):
                row.update(status='非案例素材', note='不属于A编号案例；不修改')
                rows.append(row)
                continue
            stem = srt.stem.removesuffix('_full')
            identity = re.fullmatch(r'(.+?)(?:__|_)[a-fA-F0-9]{8}', stem)
            script_stem = identity.group(1) if identity else stem
            md = root / '正式稿' / (script_stem + '.md')
            if srt.parent.name == '临时输出':
                candidates = list((root/'配音字幕'/'临时正式稿').glob(script_stem.split('__')[0] + '_*.md'))
                if len(candidates) == 1:
                    md = candidates[0]
            if srt.parent.name == 'preview':
                candidates = list((root/'正式稿').glob(script_stem.split('__')[0] + '_*.md'))
                if len(candidates) == 1:
                    md = candidates[0]
            audio = srt.with_suffix('.mp3')
            if not md.exists() or not audio.exists():
                raise ValueError('缺少同名正式稿或音频')
            source = t.display_script(t.extract_script(md))
            original_raw = srt.read_text(encoding='utf-8-sig')
            raw = original_raw
            word_json = audio.with_suffix('.json')
            independent_json = root / '配音字幕' / '音频复核' / (audio.stem + '.json')
            if independent_json.exists():
                word_json = independent_json
            timing_source = 'existing_srt'
            if word_json.exists():
                data = json.loads(word_json.read_text(encoding='utf-8-sig'))
                if data.get('audio_sha256') and data['audio_sha256'] != digest(audio):
                    raise ValueError('保存的识别数据与当前音频指纹不一致')
                words = [w for seg in data.get('segments', []) for w in seg.get('words', [])]
                if words:
                    raw = '\n\n'.join(f"{i}\n{t.format_srt_time(w['start'])} --> {t.format_srt_time(w['end'])}\n{w['word']}" for i,w in enumerate(words,1))
                    timing_source = 'independent_audio_recheck' if word_json == independent_json else 'saved_whisper_word_timestamps'
            if converter:
                raw = converter.convert(raw)
            original_chars = t.parse_asr_srt(original_raw)
            chars = t.parse_asr_srt(raw)
            actual = ''.join(t.normalize_char(c.char) for c in original_chars)
            expected = ''.join(c for _, c in t.source_units(source))
            fixed, confidence, review = t.source_locked_srt(source, raw)
            duration = MP3(str(audio)).info.length
            end = max((c.end for c in original_chars), default=0)
            intervals = [tuple(t.parse_srt_time(x.strip()) for x in pair) for pair in re.findall(r'(\d\d:\d\d:\d\d,\d{3})\s*-->\s*(\d\d:\d\d:\d\d,\d{3})', original_raw)]
            overlaps = sum(intervals[i][0] < intervals[i-1][1]-.001 for i in range(1,len(intervals)))
            row.update(confidence=round(confidence, 4), audio_seconds=round(duration, 3),
                       subtitle_end=round(end, 3), text_matches=(actual == expected),
                       audio_sha256=digest(audio), overlaps=overlaps, timing_source=timing_source)
            safe = confidence >= .90 and abs(duration-end) <= 2 and not review
            needs_repair = actual != expected or overlaps > 0 or (timing_source != 'existing_srt' and abs(duration-end) > 2)
            if timing_source != 'existing_srt':
                safe = confidence >= .90 and abs(duration-max(c.end for c in chars)) <= 2 and not review
                if confidence < .90:
                    needs_repair = True
            safe = safe and t.valid_caption_timeline(fixed, duration)
            row['status'] = '一致' if not needs_repair else ('可修复' if safe else '需复核')
            if repair and needs_repair and safe:
                backup.mkdir(parents=True, exist_ok=True)
                shutil.copy2(srt, backup / srt.name)
                report = srt.parent / (stem + '_alignment.json')
                if report.exists():
                    shutil.copy2(report, backup / report.name)
                srt.write_text(fixed, encoding='utf-8')
                report.write_text(json.dumps(dict(source=str(md), audio=str(audio),
                    subtitle_text_source='source_script', alignment_confidence=confidence,
                    review_cues=review, source_sha256=digest(md), audio_sha256=digest(audio),
                    verification='ASR text alignment; not an independent listening review',
                    timing_source=timing_source,
                    backup=str(backup / srt.name)), ensure_ascii=False, indent=2), encoding='utf-8')
                row['status'] = '已修复'
            if not needs_repair and abs(duration-end) > 2:
                row['status'] = '需复核时长'
        except Exception as exc:
            row.update(status='需复核', error=str(exc))
        rows.append(row)
    audio_only = [p.name for p in out.glob('*.mp3') if not p.with_suffix('.srt').exists()]
    samples = []
    for audio in (root/'配音字幕'/'preview').glob('*.mp3'):
        if not audio.with_suffix('.srt').exists():
            try:
                samples.append(dict(file=audio.name, seconds=round(MP3(str(audio)).info.length,3), status='音色试听片段，无字幕'))
            except Exception as exc:
                samples.append(dict(file=audio.name, status='音频读取失败', error=str(exc)))
    audio_names = {re.split(r'(?:__|_)[a-fA-F0-9]{8}_full$', p.stem)[0] for p in out.glob('A*.mp3')}
    scripts_without_audio = [p.name for p in (root/'正式稿').glob('A*.md') if p.stem not in audio_names]
    result = dict(files=rows, auxiliary_audio_samples=samples, audio_without_srt=audio_only, scripts_without_audio=scripts_without_audio,
                  scripts_count=len(list((root/'正式稿').glob('*.md'))),
                  audio_count=len(list(out.glob('*.mp3'))))
    target = root / '配音字幕' / '字幕全量核查报告.json'
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    counts = {status: sum(r['status'] == status for r in rows) for status in sorted({r['status'] for r in rows})}
    lines = ['# 字幕全量核查报告', '', f'核查时间：{datetime.now().isoformat(timespec="seconds")}', '',
             f'本次核查：{len(rows)}份字幕及配套音频，另有{len(samples)}份无字幕音色试听片段。out目录有{result["audio_count"]}份音频。',
             f'结果：{counts}', '',
             '检查范围：稿件来源、文字一致性、SRT时间顺序/重叠、音频可读取性和总时长。',
             '自动通过仅表示文本与时间轴结构通过检查，不代表逐句试听验收。', '',
             '| 字幕 | 状态 | 原稿匹配度 | 重叠/倒退数 |', '|---|---|---:|---:|']
    lines += [f'| {r["file"]} | {r["status"]} | {r.get("confidence", "-")} | {r.get("overlaps", "-")} |' for r in rows]
    lines += ['', '## 未生成音频的稿件', '', '仅列为生产进度，不判为字幕错误。', ''] + ['- ' + name for name in scripts_without_audio]
    target.with_suffix('.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    from collections import Counter
    print(json.dumps(dict(statuses=dict(Counter(r['status'] for r in rows)),
                         audio_without_srt=audio_only,
                         review=[r for r in rows if '复核' in r['status']]), ensure_ascii=False))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('root', type=Path)
    ap.add_argument('--repair', action='store_true')
    args = ap.parse_args()
    run(args.root, args.repair)
