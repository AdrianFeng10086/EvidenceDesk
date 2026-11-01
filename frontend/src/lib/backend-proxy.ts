import type { NextRequest } from 'next/server';

/**
 * 同源代理工具：浏览器只访问 Next.js，后端地址与访问主体头在这里转发。
 * 业务逻辑与密钥都不进入前端。
 */
export const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

export function backendHeaders(req: NextRequest, extra: Record<string, string> = {}): Headers {
  const headers = new Headers(extra);
  const demoUser = req.headers.get('x-demo-user');
  if (demoUser) headers.set('x-demo-user', demoUser);
  headers.set('accept', req.headers.get('accept') ?? '*/*');
  return headers;
}

export function relayResponse(response: Response): Response {
  const headers = new Headers();
  for (const name of [
    'content-type',
    'content-disposition',
    'x-content-sha256',
    'cache-control',
  ]) {
    const value = response.headers.get(name);
    if (value) headers.set(name, value);
  }
  return new Response(response.body, {
    status: response.status,
    headers,
  });
}
