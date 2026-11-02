import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, session } from "../api";

afterEach(() => vi.restoreAllMocks());

describe("api client", () => {
  it("attaches bearer token and org header", async () => {
    const f = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: true }), { status: 200 }));
    vi.stubGlobal("fetch", f);
    session.setToken("tok");
    session.setOrg("org-1");
    await api("/tasks");
    const [, init] = f.mock.calls[0];
    expect(init.headers.Authorization).toBe("Bearer tok");
    expect(init.headers["X-Org-Id"]).toBe("org-1");
  });
  it("surfaces structured API errors", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: { code: "plan_limit_reached", message: "Limit", details: { metric: "ai_messages" } } }), { status: 402 })));
    await expect(api("/conversations")).rejects.toMatchObject({ status: 402, code: "plan_limit_reached" });
    await expect(api("/conversations")).rejects.toBeInstanceOf(ApiError);
  });
  it("refreshes once on 401 then retries", async () => {
    const f = vi.fn()
      .mockResolvedValueOnce(new Response("{}", { status: 401 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ access_token: "new" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ok: 1 }), { status: 200 }));
    vi.stubGlobal("fetch", f);
    await expect(api("/tasks")).resolves.toEqual({ ok: 1 });
    expect(f.mock.calls[1][0]).toBe("/api/auth/refresh");
    expect(f.mock.calls[2][1].headers.Authorization).toBe("Bearer new");
  });
});
