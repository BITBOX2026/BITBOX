import { requestTextRoute, type RouteDestination, type TransitResponse } from "./client";

export function findRoute(
  destination: RouteDestination,
  origin?: string,
  signal?: AbortSignal,
): Promise<TransitResponse> {
  return requestTextRoute(
    { ...destination, name: destination.name.trim() },
    origin?.trim(),
    signal,
  );
}
