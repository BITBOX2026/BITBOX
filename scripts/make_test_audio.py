import argparse
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


DEFAULT_TEXT = "서울역에서 강남역 가는 버스 알려줘"


def main():
    parser = argparse.ArgumentParser(description="BITBOX 테스트용 음성 파일 생성")
    parser.add_argument(
        "--text",
        default=DEFAULT_TEXT,
        help="음성으로 변환할 문장",
    )
    parser.add_argument(
        "--output",
        default="test_audio.wav",
        help="저장할 파일명. 예: test_audio.wav 또는 test_audio.mp3",
    )
    args = parser.parse_args()

    load_dotenv()

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("[ERROR] OPENAI_API_KEY가 .env에 없습니다.")
        return

    output_path = Path(args.output)

    if output_path.suffix.lower() == ".wav":
        response_format = "wav"
    elif output_path.suffix.lower() == ".mp3":
        response_format = "mp3"
    else:
        print("[ERROR] 출력 파일 확장자는 .wav 또는 .mp3를 사용하세요.")
        return

    client = OpenAI(api_key=api_key)

    print("[INFO] 테스트 음성 생성 중...")
    print(f"[INFO] text: {args.text}")
    print(f"[INFO] output: {output_path}")

    with client.audio.speech.with_streaming_response.create(
        model="gpt-4o-mini-tts",
        voice="coral",
        input=args.text,
        instructions="한국어를 또렷하고 천천히 말하세요. 교통 안내 요청처럼 자연스럽게 읽으세요.",
        response_format=response_format,
    ) as response:
        response.stream_to_file(output_path)

    print(f"[OK] 테스트 음성 파일 생성 완료: {output_path}")


if __name__ == "__main__":
    main()