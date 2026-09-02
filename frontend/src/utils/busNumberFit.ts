/**
 * 노선번호를 한 줄에 담기는 크기로 맞춥니다.
 *
 * 왜 필요한가
 * -----------
 * 예전에는 `break-all` 로 넘침을 막았습니다. 가로로는 넘치지 않지만 대신 글자를
 * **세로로 쪼갭니다.** 큰 글씨 모드의 좁은 화면에서 "3500" 이 "350" / "0" 두 줄로
 * 나뉘어, 고령 이용자가 3500번을 350번으로 잘못 읽을 수 있었습니다. 버스를 잘못
 * 타는 것은 이 제품에서 가장 피해야 할 실패입니다.
 *
 * 어떻게 하는가
 * -------------
 * 칸의 폭에 비례하는 컨테이너 질의 단위(`cqi`)로 글자 크기를 정합니다. 1cqi 는
 * 컨테이너 콘텐츠 폭의 1% 이므로, 글자 수로 나누면 폭에 딱 맞는 크기가 나옵니다.
 * 자바스크립트 측정이나 리렌더 없이 브라우저가 직접 계산하므로 화면 크기·글씨
 * 배율이 무엇이든 한 줄이 보장됩니다. `max` 값이 있어 넓은 화면에서 과하게
 * 커지지도 않습니다.
 */

/** 한글은 전각(약 1em), 숫자·영문·기호는 약 0.6em 폭을 차지합니다. */
export function busNumberWidthUnits(busNumber: string): number {
  const units = [...busNumber].reduce(
    (total, character) => total + (/[가-힣ㄱ-ㅎㅏ-ㅣ]/.test(character) ? 1 : 0.6),
    0,
  );
  // 빈 문자열이 0으로 나뉘어 Infinity 가 되지 않게 막습니다.
  return Math.max(units, 1);
}

/**
 * `font-size` 로 바로 쓸 수 있는 값을 만듭니다.
 *
 * @param busNumber 표시할 노선번호
 * @param maxRem    넓은 칸에서 허용할 최대 크기(rem)
 */
export function busNumberFontSize(busNumber: string, maxRem: number): string {
  // 92%: 자간과 반올림 오차를 흡수하는 여유입니다. 100%로 두면 글꼴에 따라
  // 마지막 글자가 1~2px 넘쳐 잘립니다.
  const available = 92 / busNumberWidthUnits(busNumber);
  return `min(${maxRem}rem, ${available.toFixed(2)}cqi)`;
}
