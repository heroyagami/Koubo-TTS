"""Independently transcribe existing audio into a review directory (never overwrite audio)."""
import argparse
import json
import os
import hashlib
from pathlib import Path
import imageio_ffmpeg
import torch
import whisper

ap = argparse.ArgumentParser()
ap.add_argument('root', type=Path)
ap.add_argument('codes', nargs='+')
ap.add_argument('--model', default='small')
ap.add_argument('--initial-prompt', default=None, help='仅提供术语提示，不提供整篇原稿')
ap.add_argument('--threads', type=int, default=4)
ap.add_argument('--force', action='store_true')
args = ap.parse_args()
root = args.root
target = root / '配音字幕' / '音频复核'
target.mkdir(parents=True, exist_ok=True)
# whisper launches an executable literally named ffmpeg.
import shutil
ffmpeg = target / 'ffmpeg.exe'
if not ffmpeg.exists():
    shutil.copy2(imageio_ffmpeg.get_ffmpeg_exe(), ffmpeg)
os.environ['PATH'] = str(target) + os.pathsep + os.environ.get('PATH', '')
torch.set_num_threads(args.threads)
model = whisper.load_model(args.model)
for audio in sorted((root / '配音字幕' / 'out').glob('*.mp3')):
    if not any(audio.name.startswith(code + '_') for code in args.codes):
        continue
    result_path = target / (audio.stem + '.json')
    if result_path.exists() and not args.force:
        continue
    print('TRANSCRIBE ' + audio.name, flush=True)
    data = model.transcribe(str(audio), language='zh', word_timestamps=True,
                            fp16=False, verbose=False, condition_on_previous_text=False,
                            initial_prompt=args.initial_prompt)
    data['audio_sha256'] = hashlib.sha256(audio.read_bytes()).hexdigest()
    if result_path.exists():
        shutil.copy2(result_path, result_path.with_suffix('.previous.json'))
    result_path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    print('DONE ' + audio.name, flush=True)
