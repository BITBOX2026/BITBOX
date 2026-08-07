import { requestTextRoute, type TransitResponse } from "./client";

export function findRoute(
  destination: string,
  origin?: string,
): Promise<TransitResponse> {
  return requestTextRoute(destination.trim(), origin?.trim());
}
