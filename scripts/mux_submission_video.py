"""Mux the recorded live demo with timed Korean narration and create SRT captions."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
AUDIO_DIR = ARTIFACTS / "submission-audio"


def srt_time(milliseconds: int) -> str:
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1_000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{millis:03}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ffmpeg", required=True, type=Path)
    args = parser.parse_args()

    video = next((ARTIFACTS / "submission-playwright").rglob("video.webm"))
    cues = json.loads((ARTIFACTS / "submission-cues.json").read_text(encoding="utf-8"))
    manifest = json.loads((AUDIO_DIR / "manifest.json").read_text(encoding="utf-8"))
    output = ARTIFACTS / "BITBOX-Hanium-submission-demo.mp4"
    subtitles = ARTIFACTS / "BITBOX-Hanium-submission-demo.srt"

    srt_blocks = []
    for index, cue in enumerate(cues, start=1):
        start = int(cue["startMs"])
        end = start + int(cue["durationMs"])
        srt_blocks.append(
            f"{index}\n{srt_time(start)} --> {srt_time(end)}\n{cue['text']}\n"
        )
    subtitles.write_text("\n".join(srt_blocks), encoding="utf-8-sig")

    command = [str(args.ffmpeg), "-y", "-i", str(video)]
    filters = []
    labels = []
    for input_index, cue in enumerate(cues, start=1):
        audio = AUDIO_DIR / manifest[cue["id"]]["file"]
        command.extend(["-i", str(audio)])
        label = f"n{input_index}"
        delay = int(cue["startMs"])
        filters.append(f"[{input_index}:a]adelay={delay}:all=1,volume=1.0[{label}]")
        labels.append(f"[{label}]")
    filters.append(
        f"{''.join(labels)}amix=inputs={len(labels)}:duration=longest:normalize=0,"
        "alimiter=limit=0.95[aout]"
    )
    command.extend([
        "-filter_complex", ";".join(filters),
        "-map", "0:v:0",
        "-map", "[aout]",
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        str(output),
    ])
    subprocess.run(command, check=True)
    print(json.dumps({"video": str(output), "subtitles": str(subtitles)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
