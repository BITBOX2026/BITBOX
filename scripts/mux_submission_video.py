"""Mux the recorded live demo with timed Korean narration and create SRT captions."""

from __future__ import annotations

import argparse
import json

# 이 스크립트는 개발자가 손으로 실행하는 제출 영상 편집 도구입니다. 서버 코드가
# 아니며 어떤 요청 경로에서도 호출되지 않습니다. ffmpeg 는 리스트 인수로만 넘기고
# (shell=False 가 기본이라 셸 해석이 없습니다) 인수는 고정 플래그, 저장소 안의
# artifacts 경로, int() 로 강제 변환한 숫자뿐입니다.
import subprocess  # nosec B404
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

    # rglob 순서는 보장되지 않습니다. 이전 녹화가 남아 있으면 next() 가 엉뚱한
    # 영상을 집어 나레이션 타이밍과 어긋난 제출본이 만들어집니다. 가장 최근 파일을
    # 명시적으로 고르고, 아예 없으면 조용히 넘어가지 않고 멈춥니다.
    recordings = sorted(
        (ARTIFACTS / "submission-playwright").rglob("video.webm"),
        key=lambda path: path.stat().st_mtime,
    )
    if not recordings:
        raise SystemExit(
            "녹화 결과가 없습니다. 먼저 npm run e2e:submission 으로 영상을 만드십시오."
        )
    video = recordings[-1]
    if len(recordings) > 1:
        print(f"경고: 녹화본 {len(recordings)}개 중 최신본을 사용합니다 -> {video}")
    cues = json.loads((ARTIFACTS / "submission-cues.json").read_text(encoding="utf-8"))
    manifest = json.loads((AUDIO_DIR / "manifest.json").read_text(encoding="utf-8"))
    output = ARTIFACTS / "BITBOX-Hanium-submission-demo.mp4"
    subtitles = ARTIFACTS / "BITBOX-Hanium-submission-demo.srt"

    # 녹화는 브라우저 창이 열리는 순간 시작되지만 첫 자막은 앱이 그려진 뒤에야
    # 나옵니다. 개발 서버가 차가우면 그 사이가 십수 초까지 벌어져 제출본이 무음
    # 화면으로 시작합니다. 첫 큐 직전까지를 잘라내고 모든 시각을 같은 크기만큼
    # 앞당겨, 결과물이 녹화 당시 로딩 속도에 좌우되지 않게 합니다.
    lead_in_ms = max(0, min(int(cue["startMs"]) for cue in cues) - 500)

    srt_blocks = []
    for index, cue in enumerate(cues, start=1):
        start = int(cue["startMs"]) - lead_in_ms
        end = start + int(cue["durationMs"])
        srt_blocks.append(
            f"{index}\n{srt_time(start)} --> {srt_time(end)}\n{cue['text']}\n"
        )
    subtitles.write_text("\n".join(srt_blocks), encoding="utf-8-sig")

    command = [str(args.ffmpeg), "-y"]
    if lead_in_ms:
        print(f"영상 앞 {lead_in_ms / 1000:.1f}초(자막 시작 전 로딩 구간)를 잘라냅니다.")
        command.extend(["-ss", f"{lead_in_ms / 1000:.3f}"])
    command.extend(["-i", str(video)])
    filters = []
    labels = []
    for input_index, cue in enumerate(cues, start=1):
        audio = AUDIO_DIR / manifest[cue["id"]]["file"]
        command.extend(["-i", str(audio)])
        label = f"n{input_index}"
        delay = int(cue["startMs"]) - lead_in_ms
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
    # command 는 리스트이므로 shell=False(기본)로 실행되어 셸 해석이 없습니다.
    # ffmpeg 경로는 실행자가 --ffmpeg 로 직접 지정하고, 나머지 인수는 고정 플래그와
    # 저장소 artifacts 안의 파일 경로입니다.
    subprocess.run(command, check=True)  # nosec B603
    print(json.dumps({"video": str(output), "subtitles": str(subtitles)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
