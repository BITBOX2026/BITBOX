import { useEffect, useRef, useState, type RefObject } from "react";

/** 요소의 현재 높이(px)를 관찰합니다. 화면 회전·글씨 배율 변화에도 따라옵니다. */
export function useElementHeight(ref: RefObject<HTMLElement | null>): number {
  const [height, setHeight] = useState(0);

  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const measure = () => setHeight(element.getBoundingClientRect().height);
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [ref]);

  return height;
}

/**
 * 한 페이지에 "온전히 보이는" 행 수를 계산합니다.
 *
 * 왜 필요한가
 * -----------
 * 페이지당 행 수를 5로 고정해 두면, 큰 글씨 모드처럼 행이 높아지는 상황에서
 * 5행이 영역에 들어가지 않습니다. 넘친 행은 스크롤해야 보이는데, 무인 키오스크는
 * 아무도 스크롤하지 않으므로 그 행은 **존재하지 않는 것과 같습니다.** 실제로
 * 1280x800 큰 글씨 모드에서 5행 중 4행이 최대 228px 가려졌습니다.
 *
 * 글씨를 키운 이용자에게 행을 잘라 보여 주느니, 행을 적게 담고 페이지를 넘기는
 * 편이 맞습니다. 자동 페이지 전환이 나머지를 보여 줍니다.
 *
 * 언제 다시 재는가
 * ----------------
 * 크기 변화만 보고 있으면 놓치는 순간이 있습니다. 한글 웹폰트가 늦게 도착해
 * 5행 x 68px 이 4행 x 85px 이 되면 전체 높이는 340px 로 같아서 ResizeObserver 가
 * 울리지 않습니다. 그래서 폰트 준비 완료와 다음 프레임에도 한 번씩 다시 잽니다.
 */
export function useVisibleRowCount(
  containerRef: RefObject<HTMLElement | null>,
  rowSelector: string,
  options: { max: number; min?: number; resetKey: string },
): number {
  const { max, min = 1, resetKey } = options;
  const [count, setCount] = useState(max);
  const tallestRowRef = useRef(0);

  // 데이터나 글씨 배율이 바뀌면 이전 기준 높이는 더 이상 유효하지 않습니다.
  // (행 수 변화만으로는 초기화하지 않아야 값이 한 방향으로 수렴합니다.)
  useEffect(() => {
    tallestRowRef.current = 0;
  }, [resetKey]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    let cancelled = false;

    const measure = () => {
      if (cancelled || !containerRef.current) return;
      const rows = container.querySelectorAll<HTMLElement>(rowSelector);
      if (rows.length === 0) return;
      for (const row of rows) {
        tallestRowRef.current = Math.max(
          tallestRowRef.current,
          row.getBoundingClientRect().height,
        );
      }
      const rowHeight = tallestRowRef.current;
      if (rowHeight <= 0) return;
      // +1: 소수점 반올림 때문에 마지막 한 행이 억울하게 빠지지 않게 합니다.
      const fits = Math.floor((container.clientHeight + 1) / rowHeight);
      setCount(Math.max(min, Math.min(max, fits)));
    };

    measure();
    const frame = requestAnimationFrame(measure);
    void document.fonts?.ready.then(measure).catch(() => undefined);

    const observer =
      typeof ResizeObserver === "undefined" ? null : new ResizeObserver(measure);
    observer?.observe(container);
    const rowsWrapper = container.firstElementChild;
    if (rowsWrapper) observer?.observe(rowsWrapper);

    return () => {
      cancelled = true;
      cancelAnimationFrame(frame);
      observer?.disconnect();
    };
    // `count` 가 바뀌면 행이 다시 그려지므로 한 번 더 잽니다. 기준 높이는 한
    // 방향으로만 자라므로 몇 번 안에 멈춥니다.
  }, [containerRef, rowSelector, max, min, resetKey, count]);

  return count;
}
