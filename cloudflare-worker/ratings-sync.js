// ratings-sync.js — Cloudflare Worker
//
// Receives the ratings JSON straight from the site (any device, any browser)
// and commits it to GitHub as a new file under data/ratings/. The next time
// you run `actualizar.sh` / `actualizar_site.sh` locally, a `git pull` fetches
// that commit and the existing `importar-ratings` step picks the file up —
// closing the loop with zero manual export/import for the person rating.
//
// This file exists so the Worker's logic is versioned in the repo, but
// Cloudflare doesn't read it from here — you deploy it by pasting the
// contents into the Cloudflare dashboard's Worker editor (or `wrangler
// deploy`, if you have Node/wrangler installed). See README.md in this
// folder for exact steps, including the two things you must configure
// yourself: the GITHUB_TOKEN secret and the RATINGS_KV namespace binding.

const GITHUB_OWNER = 'adanttmm';
const GITHUB_REPO = 'nutricion';
const GITHUB_BRANCH = 'master';
const ALLOWED_ORIGIN = 'https://adanttmm.github.io';
const MAX_BODY_BYTES = 200 * 1024;   // a week of ratings is a few KB; generous headroom
const DAILY_WRITE_CAP = 100;         // global cap across all users; resets at UTC midnight

function corsHeaders(origin) {
  return {
    'Access-Control-Allow-Origin': origin === ALLOWED_ORIGIN ? origin : 'null',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Max-Age': '86400',
  };
}

function b64EncodeUtf8(str) {
  return btoa(unescape(encodeURIComponent(str)));
}

export default {
  async fetch(request, env) {
    const origin = request.headers.get('Origin') || '';
    const headers = corsHeaders(origin);

    if (request.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers });
    }
    if (request.method !== 'POST') {
      return new Response('Method not allowed', { status: 405, headers });
    }
    if (origin !== ALLOWED_ORIGIN) {
      return new Response('Forbidden origin', { status: 403, headers });
    }

    const bodyText = await request.text();
    if (!bodyText || bodyText.length > MAX_BODY_BYTES) {
      return new Response('Empty or oversized payload', { status: 413, headers });
    }

    let ratings;
    try {
      ratings = JSON.parse(bodyText);
    } catch (e) {
      return new Response('Invalid JSON', { status: 400, headers });
    }
    if (typeof ratings !== 'object' || ratings === null || Array.isArray(ratings)) {
      return new Response('Expected a JSON object', { status: 400, headers });
    }

    // Global daily write cap — simple KV counter, resets by UTC date key.
    const dayKey = new Date().toISOString().slice(0, 10);
    const counterKey = 'writes:' + dayKey;
    const current = parseInt((await env.RATINGS_KV.get(counterKey)) || '0', 10);
    if (current >= DAILY_WRITE_CAP) {
      return new Response('Daily write cap reached — try again tomorrow', { status: 429, headers });
    }

    // Build a unique, path-safe filename server-side — never trust a client-supplied path.
    const stamp = new Date().toISOString().replace(/[-:]/g, '').replace(/\..+/, '').replace('T', '_');
    const path = `data/ratings/ratings_${stamp}_web.json`;

    const ghResp = await fetch(
      `https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}/contents/${path}`,
      {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${env.GITHUB_TOKEN}`,
          'Accept': 'application/vnd.github+json',
          'X-GitHub-Api-Version': '2022-11-28',
          'User-Agent': 'nutricion-ratings-sync-worker',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          message: `ratings: auto-sync from site (${stamp})`,
          content: b64EncodeUtf8(JSON.stringify(ratings, null, 2)),
          branch: GITHUB_BRANCH,
        }),
      }
    );

    if (!ghResp.ok) {
      const errText = await ghResp.text();
      return new Response('GitHub write failed: ' + errText, { status: 502, headers });
    }

    await env.RATINGS_KV.put(counterKey, String(current + 1), { expirationTtl: 172800 });

    return new Response(JSON.stringify({ ok: true, path }), {
      status: 200,
      headers: { ...headers, 'Content-Type': 'application/json' },
    });
  },
};
