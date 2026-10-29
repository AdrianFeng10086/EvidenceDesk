import { NextRequest } from 'next/server';

/**
 * 同源代理：转发到 FastAPI 的 /api/chat/stream。
 * 不含业务逻辑，仅转发请求体与 SSE 响应流（遵循 docs/architecture.md 的代理原则）。
 * 密钥只存在 FastAPI 服务端，这里不接触任何 API Key。
 */

export const runtime = 'nodejs';

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

export async function POST(req: NextRequest) {
  const body = await req.text();

  const backendResponse = await fetch(`${BACKEND_URL}/api/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body,
    signal: req.signal,
  });

  if (!backendResponse.body) {
    return new Response(JSON.stringify({ error: '后端未返回流式响应' }), {
      status: 502,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  return new Response(backendResponse.body, {
    status: backendResponse.status,
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      Connection: 'keep-alive',
    },
  });
}
