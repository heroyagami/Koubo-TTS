"""Migrate caption punctuation without changing words, cue boundaries or audio."""
import argparse
import hashlib
import json
import re
import shutil
from datetime import datetime
from pathlib import Path

import tts_batch as t


TIME_RE = re.compile(r'\d\d:\d\d:\d\d,\d{3}\s*-->\s*\d\d:\d\d:\d\d,\d{3}')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def norm(text):
    return ''.join(c for _, c in t.source_units(text))


def migrate_srt(raw, source=None):
    # Keep separators, newlines, cue IDs and timing lines byte-for-byte.
    pieces = re.split(r'(\r?\n[ \t]*\r?\n)', raw)
    cues = []
    for index in range(0, len(pieces), 2):
        lines = pieces[index].splitlines(keepends=True)
        ti = next((i for i, line in enumerate(lines) if TIME_RE.search(line)), None)
        if ti is None:
            continue
        payload = [i for i in range(ti+1, len(lines)) if lines[i].strip()]
        if payload:
            cues.append((index, lines, payload))
    source = t.display_script(source) if source else ''
    units = t.source_units(source)
    exact = bool(source) and norm(source) == ''.join(norm(''.join(lines[i] for i in payload)) for _, lines, payload in cues)
    cursor = 0
    restored = 0
    for index, lines, payload in cues:
        count = len(norm(''.join(lines[i] for i in payload)))
        last = payload[-1]
        original = lines[last].rstrip('\r\n')
        newline = lines[last][len(original):]
        text = original.rstrip()
        suffix_space = original[len(text):]
        before = text
        if exact and count:
            last_pos = units[cursor+count-1][0]
            next_pos = units[cursor+count][0] if cursor+count < len(units) else len(source)
            gap = re.split(r'[\r\n]', source[last_pos+1:next_pos])[0]
            suffix = re.match(r'''[，,。．.？！?!：:；;…—]*[」』”’）)\]】》〉"']*''', gap).group()
            lexical = [i for i, c in enumerate(text) if t.normalize_char(c)]
            if suffix and lexical:
                text = text[:lexical[-1]+1] + suffix
        cursor += count
        text = t.caption_display_text(text)
        if any(c in text for c in '？！?!') and not any(c in before for c in '？！?!'):
            restored += 1
        lines[last] = text + suffix_space + newline
        pieces[index] = ''.join(lines)
    fixed = ''.join(pieces)
    if TIME_RE.findall(raw) != TIME_RE.findall(fixed) or norm(raw) != norm(fixed):
        raise ValueError('拒绝修改：字幕文字或时间轴发生变化')
    return fixed, dict(source_exact_match=exact, restored_expressive_cues=restored, cue_count=len(cues))


def find_source(root, srt):
    stem = re.sub(r'(?:__|_)[a-fA-F0-9]{8}_full$', '', srt.stem)
    source = root / '正式稿' / (stem + '.md')
    if srt.parent.name in ('preview', '临时输出'):
        code = srt.stem.split('__')[0]
        folder = root/'正式稿' if srt.parent.name == 'preview' else root/'配音字幕'/'临时正式稿'
        matches = list(folder.glob(code + '_*.md'))
        if len(matches) == 1:
            source = matches[0]
    return source


def run(root, apply=False):
    base = root / '配音字幕'
    if not base.is_dir():
        raise ValueError('项目必须包含配音字幕目录')
    backup = base/'字幕标点备份'/datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    rows = []
    for folder in ('out', 'preview', '临时输出'):
        for path in sorted((base/folder).glob('*.srt')):
            original = path.read_bytes()
            bom = original.startswith(b'\xef\xbb\xbf')
            raw = original.decode('utf-8-sig')
            md = find_source(root, path)
            try:
                source = t.extract_script(md) if md.is_file() else None
            except ValueError:
                source = None
            fixed, stats = migrate_srt(raw, source)
            encoded = (b'\xef\xbb\xbf' if bom else b'') + fixed.encode('utf-8')
            changed = encoded != original
            row = dict(file=str(path), source=str(md) if source else None, changed=changed, **stats)
            if apply and changed:
                saved = backup / folder / path.name
                saved.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, saved)
                path.write_bytes(encoded)
                row['backup'] = str(saved)
            # Preserve review decisions; only refresh an existing valid SRT fingerprint.
            report_stem = path.stem.removesuffix('_full') + '_alignment.json'
            report = path.parent / report_stem
            if apply and source and stats['source_exact_match'] and report.exists():
                data = json.loads(report.read_text(encoding='utf-8-sig'))
                if data.get('caption_punctuation_policy') != t.caption_punctuation_policy() or changed:
                    saved_report = backup / folder / report.name
                    saved_report.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(report, saved_report)
                    if data.get('srt_sha256') == sha(original):
                        data['srt_sha256'] = sha(encoded)
                    data['caption_punctuation_policy'] = t.caption_punctuation_policy()
                    data['caption_ending_punctuation'] = 'comma_period_omitted'
                    report.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
            rows.append(row)
    result = dict(applied=apply, policy=t.caption_punctuation_policy(), files=rows,
                  changed=sum(r['changed'] for r in rows), checked=len(rows),
                  restored_expressive_cues=sum(r['restored_expressive_cues'] for r in rows),
                  backup=str(backup) if apply else None,
                  unchanged='audio, words, SRT cue IDs and timestamps; previous audio-review flags retained')
    if apply:
        (base/'字幕标点更新报告.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k != 'files'}, ensure_ascii=False))
    return result


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('root', type=Path)
    ap.add_argument('--apply', action='store_true', help='备份后更新；默认仅预览')
    args = ap.parse_args()
    run(args.root, args.apply)
