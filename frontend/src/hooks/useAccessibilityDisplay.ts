import { useEffect, useState } from "react";

const STORAGE_KEY = "bitbox.largeTextMode";

function readInitial(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === "on";
  } catch {
    return false;
  }
}

/**
 * 큰 글씨·고대비 표시 모드를 전역(<html data-a11y="large">)에 적용하고
 * localStorage에 기억합니다. 고령자·저시력 사용자를 위한 화면 배려입니다.
 */
export function useAccessibilityDisplay(): [boolean, () => void] {
  const [largeText, setLargeText] = useState(readInitial);

  useEffect(() => {
    document.documentElement.toggleAttribute("data-a11y-large", largeText);
    try {
      localStorage.setItem(STORAGE_KEY, largeText ? "on" : "off");
    } catch {
      // localStorage 접근 불가 시 세션 내 상태만 유지
    }
  }, [largeText]);

  const toggle = () => setLargeText((current) => !current);

  return [largeText, toggle];
}
