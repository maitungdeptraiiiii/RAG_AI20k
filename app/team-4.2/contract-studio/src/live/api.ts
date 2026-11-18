export async function request(path: string, init?: RequestInit) {
  const response = await fetch(path, init);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
  return data;
}

// POST SSE uses data.type, unlike the source UI's Gemini event names. Keep
// partial UTF-8 and frame boundaries intact and require a terminal event.
export async function stream(
  path: string,
  init: RequestInit,
  onEvent: (event: any) => void,
) {
  const response = await fetch(path, init);
  if (
    !response.ok ||
    !response.headers.get("content-type")?.includes("text/event-stream")
  ) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.error || `HTTP ${response.status}`);
  }
  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "",
    terminal = false;
  try {
    while (true) {
      const { done, value } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      const frames = buffer.split(/\r?\n\r?\n/);
      buffer = frames.pop() || "";
      if (done && buffer.trim()) frames.push(buffer);
      for (const frame of frames) {
        const raw = frame
          .split(/\r?\n/)
          .filter((l) => l.startsWith("data:"))
          .map((l) => l.slice(5).trimStart())
          .join("\n");
        if (!raw) continue;
        const event = JSON.parse(raw);
        if (event.type === "error")
          throw new Error(event.error || "Không xử lý được yêu cầu");
        onEvent(event);
        if (event.type === "done") terminal = true;
      }
      if (done) break;
    }
    if (!terminal)
      throw new Error(
        "Kết nối bị gián đoạn. Hãy mở lại kết quả trước khi chạy lại.",
      );
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}

export const jsonBody = (data: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(data),
});
