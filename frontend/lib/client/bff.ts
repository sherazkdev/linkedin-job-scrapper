export async function bffJson<T>(url: string, init?: RequestInit): Promise<{ data?: T; error?: string; status: number }> {
  const res = await fetch(url, { ...init, credentials: "same-origin" });
  if (res.status === 204) return { status: 204 };
  let body: Record<string, unknown> = {};
  try {
    body = (await res.json()) as Record<string, unknown>;
  } catch {
    body = { error: "Invalid response" };
  }
  if (!res.ok) {
    const detail = body.detail;
    const err =
      typeof body.error === "string"
        ? body.error
        : typeof detail === "string"
          ? detail
          : "Request failed";
    return { status: res.status, error: err };
  }
  return { status: res.status, data: body as T };
}