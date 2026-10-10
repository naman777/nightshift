// Server-side proxy: the browser never sees the gateway token. Mutating calls (approve/reject) are authenticated here.
const BASE = process.env.GATEWAY_INTERNAL_URL ?? 'http://localhost:8000';
export const dynamic = 'force-dynamic';

// The token is attached to whatever this forwards, so only the POSTs the dashboard itself makes are let through. Without this a
// visitor could reach the gateway's webhooks and start real-model runs outside the demo launcher's rate limit.
const POST_ALLOWED = [/^demo\/launch$/, /^incidents\/[^/]+\/(approve|reject)$/];

async function forward(req: Request, ctx: { params: { path: string[] } }): Promise<Response> {
  const path = ctx.params.path.join('/');
  if (req.method !== 'GET' && !POST_ALLOWED.some((p) => p.test(path))) {
    return new Response(JSON.stringify({ detail: 'not available through the dashboard' }), { status: 403, headers: { 'Content-Type': 'application/json' } });
  }
  const url = `${BASE}/${path}${new URL(req.url).search}`;
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (process.env.NIGHTSHIFT_API_TOKEN) headers.Authorization = `Bearer ${process.env.NIGHTSHIFT_API_TOKEN}`;
  // Visitor address for the gateway's real-model rate limit: the last hop is the one the reverse proxy in front of us wrote, so a
  // client cannot forge it by sending its own X-Forwarded-For.
  const ip = req.headers.get('x-forwarded-for')?.split(',').pop()?.trim();
  if (ip) headers['X-Nightshift-Client-IP'] = ip;
  const r = await fetch(url, { method: req.method, headers, body: req.method === 'GET' ? undefined : await req.text(), cache: 'no-store' });
  return new Response(await r.text(), { status: r.status, headers: { 'Content-Type': 'application/json' } });
}

export const GET = forward;
export const POST = forward;
