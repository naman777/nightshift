// Server-side proxy: the browser never sees the gateway token. Mutating calls (approve/reject) are authenticated here.
const BASE = process.env.GATEWAY_INTERNAL_URL ?? 'http://localhost:8000';
export const dynamic = 'force-dynamic';

async function forward(req: Request, ctx: { params: { path: string[] } }): Promise<Response> {
  const url = `${BASE}/${ctx.params.path.join('/')}${new URL(req.url).search}`;
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (process.env.NIGHTSHIFT_API_TOKEN) headers.Authorization = `Bearer ${process.env.NIGHTSHIFT_API_TOKEN}`;
  const r = await fetch(url, { method: req.method, headers, body: req.method === 'GET' ? undefined : await req.text(), cache: 'no-store' });
  return new Response(await r.text(), { status: r.status, headers: { 'Content-Type': 'application/json' } });
}

export const GET = forward;
export const POST = forward;
