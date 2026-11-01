import type { NextRequest } from 'next/server';

import { BACKEND_URL, backendHeaders, relayResponse } from '@/lib/backend-proxy';

export const runtime = 'nodejs';

export async function POST(req: NextRequest, { params }: { params: { id: string } }) {
  const response = await fetch(
    `${BACKEND_URL}/api/documents/${encodeURIComponent(params.id)}/parse/retry`,
    {
      method: 'POST',
      headers: backendHeaders(req),
      signal: req.signal,
    }
  );
  return relayResponse(response);
}
