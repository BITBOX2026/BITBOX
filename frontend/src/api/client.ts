import type { BusOption, RouteDetail } from "../types/bus";

export type UploadVoiceResponse = {
  success: boolean;
  text?: string | null;
  intent?: string | null;
  destination?: string | null;
  destination_text?: string | null;
  bus_number?: string | null;
  arrival_time?: string | null;
  arrival_time_2?: string | null;
  first_bus_time?: string | null;
  message: string;
  buses: Array<BusOption & {
    totalMin?: number;
    steps?: RouteDetail["steps"];
    routeDetail?: RouteDetail & Record<string, unknown>;
  }>;
  audio_base64?: string | null;
  request_id?: string | null;
};

const DEFAULT_API_BASE_URL = "http://3.144.238.75:8000";

export function getApiBaseUrl(): string {
  return (import.meta.env.VITE_API_BASE_URL || DEFAULT_API_BASE_URL).replace(/\/+$/, "");
}

function getAuthHeaders(): HeadersInit {
  const token = import.meta.env.VITE_API_AUTH_TOKEN;
  return token ? { "x-bitbox-token": token } : {};
}

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  Object.entries(getAuthHeaders()).forEach(([key, value]) => headers.set(key, value));

  return fetch(`${getApiBaseUrl()}${path}`, {
    ...init,
    headers,
  });
}

export async function uploadVoiceAudio(blob: Blob): Promise<UploadVoiceResponse> {
  const formData = new FormData();
  formData.append("file", blob, "recording.webm");

  const response = await apiFetch("/api/upload", {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    throw new Error(`Server responded with ${response.status}`);
  }

  return response.json();
}
