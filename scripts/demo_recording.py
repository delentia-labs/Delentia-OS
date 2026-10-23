"""Record real PTY output and render Unicode text without clipping Thai marks.

Optional local tools: Pillow with libraqm, pyte, ffmpeg, Noto Sans Thai.
The video is a shaped terminal replay, not a desktop capture or model evaluation.
"""
from __future__ import annotations

import argparse
import codecs
import errno
import json
import math
import os
from pathlib import Path
import select
import subprocess
import time
import unicodedata


def decode_chunks(chunks: list[bytes]) -> str:
    """Same incremental decoder as capture; incomplete/invalid UTF-8 fails loudly."""
    decoder = codecs.getincrementaldecoder("utf-8")("strict")
    return "".join(decoder.decode(chunk) for chunk in chunks) + decoder.decode(b"", final=True)


def record(output: Path, command: list[str], columns: int = 120, rows: int = 40) -> int:
    import fcntl
    import pty
    import struct
    import termios

    output.mkdir(parents=True, exist_ok=False)
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", rows, columns, 0, 0))
    env = {**os.environ, "TERM": "xterm-256color", "COLUMNS": str(columns), "LINES": str(rows),
           "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}
    child = subprocess.Popen(command, stdin=slave, stdout=slave, stderr=slave, env=env, start_new_session=True)
    os.close(slave)
    start = time.monotonic()
    decoder = codecs.getincrementaldecoder("utf-8")("strict")
    try:
        with (output / "session.cast").open("w", encoding="utf-8") as cast, \
                (output / "transcript.txt").open("w", encoding="utf-8") as transcript, \
                (output / "pty-output.bin").open("wb") as raw:
            cast.write(json.dumps({"version": 2, "width": columns, "height": rows,
                                   "timestamp": int(time.time()), "title": "SCRIPTED real PTY capture",
                                   "env": {"TERM": env["TERM"]}}) + "\n")
            def emit(text: str) -> None:
                if text:
                    cast.write(json.dumps([round(time.monotonic() - start, 4), "o", text], ensure_ascii=False) + "\n")
                    cast.flush()
                    transcript.write(text)
            while True:
                if select.select([master], [], [], 0.25)[0]:
                    try:
                        chunk = os.read(master, 65536)
                    except OSError as exc:
                        if exc.errno == errno.EIO:
                            break
                        raise
                    if not chunk:
                        break
                    raw.write(chunk)
                    emit(decoder.decode(chunk))
                elif child.poll() is not None:
                    break
            emit(decoder.decode(b"", final=True))
    finally:
        os.close(master)
        if child.poll() is None:
            child.terminate()
    code = child.wait()
    (output / "capture.json").write_text(json.dumps({"command": command, "exit_code": code,
        "duration_seconds": time.monotonic() - start, "utf8_decoder": "incremental-strict",
        "label": "SCRIPTED model; actual PTY output"}, indent=2), encoding="utf-8")
    return code


def text_runs(line: dict, columns: int) -> list[tuple[int, str, bool]]:
    """Keep Thai clusters together; draw on the full canvas, never cell-sized tiles."""
    runs = []
    for x in range(columns):
        text = line[x].data
        thai = any("\u0e00" <= c <= "\u0e7f" for c in text)
        if runs and runs[-1][2] == thai:
            start, prior, _ = runs[-1]
            runs[-1] = (start, prior + text, thai)
        else:
            runs.append((x, text, thai))
    return runs


def unicode_screen(columns: int, rows: int):
    import pyte
    from wcwidth import wcwidth

    class UnicodeScreen(pyte.Screen):
        def draw(self, text: str) -> None:
            # pyte 0.8 stops the ENTIRE text chunk on zero-width Thai marks
            # with canonical combining class 0 (e.g. U+0E31, U+0E35).
            # Category M, not combining-class!=0, identifies these marks.
            for char in text:
                if wcwidth(char) == 0 and unicodedata.category(char).startswith("M"):
                    x, y = self.cursor.x - 1, self.cursor.y
                    if x < 0 and y:
                        x, y = self.columns - 1, y - 1
                    if x >= 0:
                        cell = self.buffer[y][x]
                        self.buffer[y][x] = cell._replace(data=unicodedata.normalize("NFC", cell.data + char))
                        self.dirty.add(y)
                else:
                    super().draw(char)
    return UnicodeScreen(columns, rows)


def render(cast_path: Path, output: Path, fps: int = 5) -> None:
    import pyte
    from PIL import Image, ImageDraw, ImageFont, features

    if not features.check_feature("raqm"):
        raise RuntimeError("Pillow libraqm is required for Thai shaping; do not fall back to per-cell glyphs")
    lines = cast_path.read_text(encoding="utf-8").splitlines()
    header, events = json.loads(lines[0]), [json.loads(x) for x in lines[1:]]
    if not events or any("\ufffd" in e[2] for e in events if e[1] == "o"):
        raise ValueError("missing output or replacement characters in source capture; re-record first")
    columns, rows = header["width"], header["height"]
    cw, ch, top = 14, 32, 94
    width, height = columns * cw, rows * ch + top
    fonts = [ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 20),
             ImageFont.truetype("/usr/share/fonts/truetype/noto/NotoSansThai-Regular.ttf", 20,
                                layout_engine=ImageFont.Layout.RAQM)]
    label = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
    screen, index = unicode_screen(columns, rows), 0
    stream = pyte.Stream(screen)
    duration = events[-1][0] + 4
    frames = math.ceil(duration * fps)
    child = subprocess.Popen(["ffmpeg", "-hide_banner", "-loglevel", "error", "-n", "-f", "rawvideo",
        "-pixel_format", "rgb24", "-video_size", f"{width}x{height}", "-framerate", str(fps), "-i", "pipe:0",
        "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", str(output)], stdin=subprocess.PIPE)
    seen_thai = set()
    try:
        for frame in range(frames):
            while index < len(events) and events[index][0] <= frame / fps:
                if events[index][1] == "o":
                    stream.feed(events[index][2])
                index += 1
            canvas = Image.new("RGB", (width, height), "#0b1220")
            draw = ImageDraw.Draw(canvas)
            draw.text((16, 9), "SCRIPTED model | real CLI, tools, SQLite | no paid API", font=label, fill="#fde68a")
            draw.text((16, 43), "Unicode-shaped terminal replay | original timing | experimental", font=label, fill="#93c5fd")
            for y in range(rows):
                runs = text_runs(screen.buffer[y], columns)
                for x, text, thai in runs:
                    if text.strip():
                        draw.text((x * cw, top + y * ch), text, font=fonts[int(thai)], fill="#e5e7eb")
                    if thai and text not in seen_thai:
                        seen_thai.add(text)
                        canvas_path = output.with_name(output.stem + "-thai-frame.png")
                        # Save after the complete frame below.
                if any(r[2] for r in runs):
                    canvas_path = output.with_name(output.stem + "-thai-frame.png")
            if any("\u0e00" <= c <= "\u0e7f" for row in screen.display for c in row):
                canvas.save(canvas_path)
            child.stdin.write(canvas.tobytes())
    finally:
        child.stdin.close()
    if child.wait() != 0:
        raise RuntimeError("ffmpeg failed")
    output.with_suffix(".json").write_text(json.dumps({"cast": str(cast_path), "fps": fps,
        "frames": frames, "duration_seconds": frames / fps, "thai_runs_seen": sorted(seen_thai),
        "rendering": "whole Thai runs, RAQM, no per-cell clipping; monochrome shaped replay",
        "source_replacement_characters": 0}, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    capture = commands.add_parser("record")
    capture.add_argument("--output", type=Path, required=True)
    capture.add_argument("command", nargs=argparse.REMAINDER)
    movie = commands.add_parser("render")
    movie.add_argument("cast", type=Path)
    movie.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.action == "record":
        command = args.command[1:] if args.command[:1] == ["--"] else args.command
        if not command:
            parser.error("a command is required")
        return record(args.output, command)
    render(args.cast, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
