"""
Round 73: how well does the local Whisper hear Thai, and does a bigger model help? Real human speech with reference transcripts: Google FLEURS Thai (test split), the first N clips in the file's order
(no selection by difficulty). Metric: character error rate (CER) after removing spaces and punctuation (Thai is written without spaces, so word error rate is meaningless), computed with a plain edit
distance. The same call voice.py makes (openai-whisper, local, `language="th"`, fp16 off). Models tiny / base / small must already be in ~/.cache/whisper (voice.py never downloads).

Criteria written before the run: report CER per model with the number of clips and the median seconds per clip; a model counts as "usable for Thai voice notes" if its CER is at most 0.30
(about one character in three wrong still leaves most notes understandable; above that a misheard instruction is likely). No adoption rule beyond reporting: the default stays `tiny` until the Architect decides.

    python research/whisper_thai_eval_r73.py --data C:\\Users\\whale\\speech_eval --clips 30 --models tiny,base,small --out research/whisper_thai_eval_r73.json
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import tarfile
import time
import unicodedata
from pathlib import Path
from typing import Dict, List


def normalise(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    return "".join(ch for ch in text if not (ch.isspace() or unicodedata.category(ch).startswith("P") or unicodedata.category(ch).startswith("S")))


def edit_distance(a: str, b: str) -> int:
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


def load_clips(data: Path, n: int) -> List[Dict[str, str]]:
    rows = []
    with open(data / "data" / "th_th" / "test.tsv", encoding="utf-8") as handle:
        for line in handle:
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 4:
                rows.append({"file": parts[1], "reference": parts[3]})
            if len(rows) >= n:
                break
    wanted = {r["file"] for r in rows}
    out_dir = data / "clips"
    out_dir.mkdir(exist_ok=True)
    have = {p.name for p in out_dir.glob("*.wav")}
    if not wanted <= have:
        with tarfile.open(data / "data" / "th_th" / "audio" / "test.tar.gz", "r:gz") as tar:
            for member in tar:
                name = os.path.basename(member.name)
                if name in wanted and name not in have:
                    (out_dir / name).write_bytes(tar.extractfile(member).read())            # type: ignore[union-attr]
                    have.add(name)
                    if wanted <= have:
                        break
    return [{**r, "path": str(out_dir / r["file"])} for r in rows if (out_dir / r["file"]).exists()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--clips", type=int, default=30)
    ap.add_argument("--models", default="tiny,base,small")
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    import whisper
    clips = load_clips(Path(args.data), args.clips)
    print(f"{len(clips)} clips", flush=True)
    report: Dict[str, object] = {"dataset": "google/fleurs th_th test, first clips in file order", "clips": len(clips), "models": {}}
    cache = os.path.join(os.path.expanduser("~"), ".cache", "whisper")
    for name in args.models.split(","):
        model = whisper.load_model(name, download_root=cache)
        errors = chars = 0
        seconds: List[float] = []
        worst = []
        for clip in clips:
            started = time.perf_counter()
            heard = model.transcribe(clip["path"], language="th", fp16=False, verbose=None)["text"]
            seconds.append(time.perf_counter() - started)
            ref, hyp = normalise(clip["reference"]), normalise(heard)
            d = edit_distance(ref, hyp)
            errors += d
            chars += len(ref)
            worst.append((round(d / max(1, len(ref)), 2), clip["file"]))
        cer = errors / max(1, chars)
        report["models"][name] = {"cer": round(cer, 3), "median_seconds_per_clip": round(statistics.median(seconds), 1), "usable_cer_at_most_0.30": cer <= 0.30, "worst_clips": sorted(worst, reverse=True)[:3]}
        print(name, report["models"][name], flush=True)
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
