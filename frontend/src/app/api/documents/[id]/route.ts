import type { NextRequest } from 'next/server';

import { BACKEND_URL, backendHeaders, relayResponse } from '@/lib/backend-proxy';

export const runtime = 'nodejs';

export async function GET(req: NextRequest, { params }: { params: { id: string } }) {
  const response = await fetch(
    `${BACKEND_URL}/api/documents/${encodeURIComponent(params.id)}`,
    {
      headers: backendHeaders(req),
      cache: 'no-store',
    }
  );
  return relayResponse(response);
}
