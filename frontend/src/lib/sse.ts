import type { StreamEvent } from './types/stream-events';

/**
 * 解析 text/event-stream 响应体，按 SSE 的 "event:" / "data:" 字段切分，
 * 逐条 yield 已解析的事件。调用方通过 abortSignal 控制停止。
 */
export async function* parseSseStream(
  body: ReadableStream<Uint8Array>,
  abortSignal: AbortSignal
): AsyncGenerator<StreamEvent, void> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  const onAbort = () => {
    reader.cancel().catch(() => undefined);
  };
  abortSignal.addEventListener('abort', onAbort);

  try {
    while (true) {
      if (abortSignal.aborted) return;

      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const chunks = buffer.split('\n\n');
      buffer = chunks.pop() ?? '';

      for (const chunk of chunks) {
        const event = parseChunk(chunk);
        if (event) yield event;
      }
    }
  } finally {
    abortSignal.removeEventListener('abort', onAbort);
  }
}

function parseChunk(chunk: string): StreamEvent | null {
  let dataLine: string | null = null;
  for (const line of chunk.split('\n')) {
    if (line.startsWith('data:')) {
      dataLine = line.slice(5).trim();
    }
  }
  if (!dataLine) return null;

  try {
    return JSON.parse(dataLine) as StreamEvent;
  } catch {
    return null;
  }
}
