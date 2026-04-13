export const runtime = "nodejs";

export async function POST(req: Request) {
  const body = await req.text();
  const upstream = await fetch(`${process.env.API_URL}/research`, {
    method: "POST",
    body,
    headers: { "content-type": "application/json" },
  });
  return new Response(upstream.body, {
    headers: {
      "content-type": "text/event-stream",
      "cache-control": "no-cache",
      connection: "keep-alive",
    },
  });
}
