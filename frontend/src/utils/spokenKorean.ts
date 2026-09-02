/**
 * 화면에 쓴 글자를 "귀로 들을 문장"으로 바꿉니다.
 *
 * 왜 필요한가
 * -----------
 * 음성 합성기는 "3412번"을 하나의 수로 읽어 **"삼천사백십이 번"** 이 됩니다.
 * 그런데 실제 정류장 안내방송과 사람들의 말버릇은 노선번호를 자릿수로 끊어
 * **"삼사일이번"** 이라고 읽습니다. 청력이 떨어진 이용자에게 "삼천사백십이번"은
 * 화면의 `3412` 와 즉시 연결되지 않아, 정작 자기 버스를 놓치게 만듭니다.
 *
 * 그래서 노선번호만 자릿수로 끊어 읽도록 바꿉니다. 소요 시간·요금뿐 아니라
 * `12번 출구`처럼 `번`이 붙는 시설 번호도 그대로 두어야 합니다. 숫자 길이와
 * 버스 문맥을 함께 보고, M6405·N13 같은 영문 노선도 놓치지 않습니다.
 *
 * 표시용 문자열은 바꾸지 않습니다. 화면은 계속 `3412번`을 보여 줍니다.
 */

const HANGUL_DIGITS = ["공", "일", "이", "삼", "사", "오", "육", "칠", "팔", "구"];
const HANGUL_LETTERS: Record<string, string> = {
  A: "에이", B: "비", C: "씨", D: "디", E: "이", F: "에프", G: "지",
  H: "에이치", I: "아이", J: "제이", K: "케이", L: "엘", M: "엠", N: "엔",
  O: "오", P: "피", Q: "큐", R: "알", S: "에스", T: "티", U: "유",
  V: "브이", W: "더블유", X: "엑스", Y: "와이", Z: "지",
};

// `번`은 버스에만 붙지 않습니다. 특히 경로 안내에는 `12번 출구`가 자주
// 등장하므로 이런 시설 번호를 노선번호로 바꾸면 안 됩니다.
const NON_BUS_NUMBER_CONTEXT = /^(?:출구|승강장|게이트|좌석|플랫폼|문항|항목)/;
const SHORT_BUS_CONTEXT = /^(?:버스|노선|마을버스|탑승|승차|하차|(?:을|를)?\s*타|(?:에서|으로)\s*.*갈아타|(?:이|가|은|는)?\s*(?:곧|도착|출발|운행))/;

/** 숫자를 자릿수 그대로 읽습니다. "3412" → "삼사일이" */
export function spellDigits(digits: string): string {
  return [...digits].map((digit) => HANGUL_DIGITS[Number(digit)] ?? digit).join("");
}

/** 영문 접두·가지번호·지역 접미가 섞인 실제 노선 식별자를 읽습니다. */
export function spellBusNumber(busNumber: string): string {
  const parts = busNumber.match(/[A-Za-z]+|\d+|-|[가-힣]+/g) ?? [busNumber];
  return parts
    .map((part) => {
      if (/^\d+$/.test(part)) return spellDigits(part);
      if (part === "-") return "다시";
      if (/^[A-Za-z]+$/.test(part)) {
        return [...part.toUpperCase()].map((letter) => HANGUL_LETTERS[letter] ?? letter).join(" ");
      }
      return part;
    })
    .join(" ");
}

function isLikelyBusNumber(identifier: string, followingText: string): boolean {
  const context = followingText.trimStart();
  if (NON_BUS_NUMBER_CONTEXT.test(context)) return false;

  // 영문·하이픈·지역명이 붙었거나 세 자리 이상이면 그 자체로 노선 식별력이
  // 충분합니다. 한두 자리 노선은 `2번 출구`와 구분하기 위해 버스 문맥을 요구합니다.
  const digits = identifier.replace(/\D/g, "");
  const hasRouteMarker = /[A-Za-z가-힣-]/.test(identifier) || digits.length >= 3;
  return hasRouteMarker || SHORT_BUS_CONTEXT.test(context);
}

/**
 * 노선번호를 자릿수 읽기로 바꿉니다.
 *
 * `146번`, `M6405번 버스`, `30-5하남번` 같은 노선 식별자만 손댑니다.
 * 영문은 글자 이름으로, 가지번호의 하이픈은 정류장 안내와 같은 "다시"로 읽습니다.
 *
 * `2호선`, `30분`, `1,500원`, `3정거장`, `12번 출구` 같은 다른 숫자는 그대로
 * 둡니다. "삼십 분"을 "삼 공 분"으로 읽으면 오히려 알아듣기 어렵습니다.
 */
export function toSpokenKorean(text: string): string {
  return text.replace(
    // 실제 데이터에는 M6405·N13·1311B광주처럼 영문이 섞인 노선도 있습니다.
    // 앞이 글자/숫자가 아닌 위치에서 시작해야 역명 안쪽 숫자를 잘못 떼지 않습니다.
    /(^|[^0-9A-Za-z가-힣])([A-Za-z]?\d[0-9A-Za-z-]*[가-힣]{0,6})번/g,
    (match, prefix: string, routeNumber: string, offset: number, wholeText: string) => {
      const followingText = wholeText.slice(offset + match.length);
      if (!isLikelyBusNumber(routeNumber, followingText)) return match;
      return `${prefix}${spellBusNumber(routeNumber)} 번`;
    },
  );
}
