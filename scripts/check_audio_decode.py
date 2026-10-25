"""Decode every production, temporary and preview MP3 without changing audio."""
import argparse
import json
import subprocess
from pathlib import Path
import imageio_ffmpeg

ap = argparse.ArgumentParser()
ap.add_argument('root', type=Path)
args = ap.parse_args()
base = args.root / '配音字幕'
rows = []
for folder in ['out', 'preview', '临时输出']:
    for audio in sorted((base/folder).glob('*.mp3')):
        result = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-v', 'error', '-i',
                                 str(audio), '-f', 'null', '-'],
                                capture_output=True, timeout=120)
        stderr = result.stderr.decode('utf-8', errors='replace').strip()
        rows.append(dict(file=str(audio), returncode=result.returncode,
                         status='通过' if result.returncode == 0 and not stderr else '需复核',
                         decoder_messages=stderr[:3000]))
report = base / '音频解码检查.json'
report.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(dict(total=len(rows), passed=sum(r['status']=='通过' for r in rows),
                      issues=[r for r in rows if r['status']!='通过']), ensure_ascii=False))
