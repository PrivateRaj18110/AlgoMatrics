import { beforeEach, describe, expect, it, vi } from "vitest";

import { api, connectAuthBridge } from "@/lib/api";

describe("api client auth", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => [],
      }),
    );
    connectAuthBridge({
      getAccessToken: () => "jwt-access",
      getOrgId: () => "org-1",
      onTokens: () => undefined,
      onAuthLost: () => undefined,
    });
  });

  it("sends the main JWT and org header, never an ops ingest token", async () => {
    await api("/operations/machines");
    const [url, init] = vi.mocked(fetch).mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/v1/operations/machines");
    const headers = init.headers as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer jwt-access");
    expect(headers["X-Org-Id"]).toBe("org-1");
    expect(JSON.stringify(headers)).not.toContain("RAJ_AGENT");
    expect(JSON.stringify(headers)).not.toContain("X-Raj-Agent-Token");
    expect(JSON.stringify(headers)).not.toContain("VITE_OPS");
  });
});
