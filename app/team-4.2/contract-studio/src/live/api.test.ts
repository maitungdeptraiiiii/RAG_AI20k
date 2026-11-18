import { test } from "node:test";
import assert from "node:assert/strict";
import { stream } from "./api";

test("POST SSE handles split UTF-8, CRLF and terminal result", async () => {
  const original = globalThis.fetch;
  const bytes = new TextEncoder().encode(
    'data: {"type":"stage","label":"Tiếng Việt"}\r\n\r\ndata: {"type":"done"}\n\n',
  );
  globalThis.fetch = async () =>
    new Response(
      new ReadableStream({
        start(c) {
          for (let i = 0; i < bytes.length; i += 3)
            c.enqueue(bytes.slice(i, i + 3));
          c.close();
        },
      }),
      { headers: { "Content-Type": "text/event-stream" } },
    );
  try {
    const events: any[] = [];
    await stream("/test", {}, (e) => events.push(e));
    assert.equal(events[0].label, "Tiếng Việt");
    assert.equal(events[1].type, "done");
  } finally {
    globalThis.fetch = original;
  }
});

test("a truncated SSE response cannot silently become completed", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async () =>
    new Response('data: {"type":"stage"}\n\n', {
      headers: { "Content-Type": "text/event-stream" },
    });
  try {
    await assert.rejects(
      stream("/test", {}, () => {}),
      /gián đoạn/,
    );
  } finally {
    globalThis.fetch = original;
  }
});
