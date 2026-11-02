import type { NextRequest } from 'next/server';

import { BACKEND_URL, backendHeaders, relayResponse } from '@/lib/backend-proxy';

export const runtime = 'nodejs';

interface RouteContext {
  params: { id: string; documentId: string };
}

export async function GET(req: NextRequest, { params }: RouteContext) {
  const response = await fetch(
    `${BACKEND_URL}/api/workspaces/${encodeURIComponent(params.id)}/documents/${encodeURIComponent(
      params.documentId
    )}/delete-impact`,
    {
      headers: backendHeaders(req),
      cache: 'no-store',
    }
  );
  return relayResponse(response);
}
