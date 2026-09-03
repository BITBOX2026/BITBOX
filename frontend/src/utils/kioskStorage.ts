export const VOICE_CONSENT_KEY = "bitbox.voiceConsent.v1";
export const RECENT_DESTINATIONS_KEY = "bitbox.recentDestinations";
// 음량은 기기 설정입니다. 개인정보가 아니므로 이용자가 바뀌어도 초기화하지
// 않습니다. 시끄러운 정류장에서 한 번 키워 둔 소리가 다음 사람에게도 들려야
// 합니다. (clearRecentDestinationHistory 는 이 키를 건드리지 않습니다.)
export const SPEECH_VOLUME_KEY = "bitbox.speechVolume";

export function readKioskStorage(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function writeKioskStorage(key: string, value: string): boolean {
  try {
    localStorage.setItem(key, value);
    return true;
  } catch {
    return false;
  }
}

export function removeKioskStorage(key: string): void {
  try {
    localStorage.removeItem(key);
  } catch {
    // Storage can be disabled by browser policy; absence already matches removal.
  }
}

export function clearRecentDestinationHistory(): void {
  removeKioskStorage(RECENT_DESTINATIONS_KEY);
  window.dispatchEvent(new Event("bitbox:recent-cleared"));
}
