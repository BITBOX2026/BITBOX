import { requestTextRoute, type TransitResponse } from "./client";

export type TransportMode = "bus" | "subway" | "transit";

export function findRoute(
  destination: string,
  origin?: string,
  transportMode: TransportMode = "bus",
): Promise<TransitResponse> {
  return requestTextRoute(destination.trim(), origin?.trim(), transportMode);
}
