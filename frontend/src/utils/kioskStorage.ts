export const VOICE_CONSENT_KEY = "bitbox.voiceConsent.v1";
export const RECENT_DESTINATIONS_KEY = "bitbox.recentDestinations";

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
