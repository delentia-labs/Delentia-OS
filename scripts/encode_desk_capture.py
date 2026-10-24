"""Encode actual Desk frames at their recorded timing; never synthesize UI frames."""
import argparse
import json
import math
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    result = json.loads((args.capture / 'result.json').read_text())
    if result.get('passed') is not True or result.get('page_errors') or not result.get('frames'):
        parser.error('a completed, passing capture with no page errors is required')
    frames = result['frames']
    lines = ['ffconcat version 1.0']
    for i, frame in enumerate(frames):
        name = frame['file']
        if not name.startswith('frame-') or not name.endswith('.png') or not name[6:-4].isdigit():
            parser.error('unexpected capture filename')
        if not (args.capture / name).is_file():
            parser.error('missing captured frame')
        duration = frames[i + 1]['seconds'] - frame['seconds'] if i + 1 < len(frames) else 0.6
        if not math.isfinite(duration) or duration <= 0:
            parser.error('invalid capture timestamps')
        lines.extend([f"file '{name}'", f'duration {duration}'])
    lines.append(f"file '{frames[-1]['file']}'")
    concat = args.capture / 'frames.ffconcat'
    concat.write_text('\n'.join(lines) + '\n')
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-safe', '0', '-i', str(concat),
                    '-vf', "fps=20,drawbox=x=0:y=0:w=iw:h=28:color=black@0.85:t=fill,drawtext=text='REAL GUI | SYNTHETIC DATA | NO MODEL GENERATION':fontcolor=white:fontsize=15:x=12:y=6",
                    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(args.output)], check=True)


if __name__ == '__main__':
    main()
