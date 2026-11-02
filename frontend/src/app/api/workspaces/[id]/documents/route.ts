import type { NextRequest } from 'next/server';

import {
  BACKEND_URL,
  backendHeaders,
  relayResponse,
} from '@/lib/backend-proxy';

export const runtime = 'nodejs';

interface RouteContext {
  params: { id: string };
}

export async function GET(req: NextRequest, { params }: RouteContext) {
  const response = await fetch(
    `${BACKEND_URL}/api/workspaces/${encodeURIComponent(params.id)}/documents${req.nextUrl.search}`,
    {
      headers: backendHeaders(req),
      cache: 'no-store',
    }
  );
  return relayResponse(response);
}

export async function POST(req: NextRequest, { params }: RouteContext) {
  const body = await req.arrayBuffer();
  const response = await fetch(
    `${BACKEND_URL}/api/workspaces/${encodeURIComponent(params.id)}/documents`,
    {
      method: 'POST',
      headers: backendHeaders(req, {
        'content-type': req.headers.get('content-type') ?? 'application/octet-stream',
      }),
      body,
      signal: req.signal,
    }
  );
  return relayResponse(response);
}
