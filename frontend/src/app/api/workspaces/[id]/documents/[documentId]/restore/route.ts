import type { NextRequest } from 'next/server';

import { BACKEND_URL, backendHeaders, relayResponse } from '@/lib/backend-proxy';

export const runtime = 'nodejs';

interface RouteContext {
  params: { id: string; documentId: string };
}

export async function POST(req: NextRequest, { params }: RouteContext) {
  const response = await fetch(
    `${BACKEND_URL}/api/workspaces/${encodeURIComponent(params.id)}/documents/${encodeURIComponent(
      params.documentId
    )}/restore`,
    {
      method: 'POST',
      headers: backendHeaders(req),
      signal: req.signal,
    }
  );
  return relayResponse(response);
}
