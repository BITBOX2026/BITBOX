import { describe, expect, it } from "vitest";
import { parseApiResponse } from "./client";

function jsonResponse(status: number, body: unknown, requestId = "abc123def456"): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", "x-request-id": requestId },
  });
}

describe("parseApiResponse 오류 문구", () => {
  it("FastAPI 422 의 객체 배열 detail 을 화면에 그대로 노출하지 않는다", async () => {
    // 422 는 detail 이 객체 배열입니다. 문자열로 그대로 쓰면 이용자에게
    // "[object Object]" 가 보입니다. 고령 이용자에게는 특히 이해할 수 없는 문구입니다.
    const response = jsonResponse(422, {
      detail: [
        { type: "string_too_long", loc: ["body", "destination"], msg: "String should have at most 100 characters" },
      ],
    });

    await expect(parseApiResponse(response, "장소 검색에 실패했습니다.")).rejects.toThrow(
      /장소 검색에 실패했습니다\. \(422\) \(문의 코드: abc123def456\)/
    );
    await expect(
      parseApiResponse(jsonResponse(422, { detail: [{ msg: "x" }] }), "요청에 실패했습니다.")
    ).rejects.not.toThrow(/\[object Object\]/);
  });

  it("서버가 사람이 읽을 수 있는 문자열 detail 을 주면 그대로 보여 준다", async () => {
    const response = jsonResponse(502, { detail: "장소 검색 서비스를 사용할 수 없습니다." });
    await expect(parseApiResponse(response, "장소 검색에 실패했습니다.")).rejects.toThrow(
      "장소 검색 서비스를 사용할 수 없습니다. (문의 코드: abc123def456)"
    );
  });

  it("정상 응답은 그대로 반환한다", async () => {
    const payload = await parseApiResponse<{ suggestions: unknown[] }>(
      jsonResponse(200, { suggestions: [] }),
      "실패"
    );
    expect(payload).toEqual({ suggestions: [] });
  });
});
