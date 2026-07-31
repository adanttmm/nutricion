# Ratings sync — Cloudflare Worker

Lets IOB (or anyone) rate dishes on their own phone and have it land in this
repo automatically, so the next `actualizar.sh` / `actualizar_site.sh` run
picks it up — no manual export/share step.

```
phone (any browser)
  → POST ratings JSON → Cloudflare Worker (holds the GitHub token)
  → GitHub Contents API → new file at data/ratings/ratings_<timestamp>_web.json, committed to master
  → next `actualizar.sh` run: `git pull` fetches it, `importar-ratings` imports it
```

No server to maintain — it's a small function that runs on Cloudflare's free tier.

## One-time setup (~10 minutes, all done in the browser)

### 1. Create a GitHub token (the Worker's only credential)

1. Go to https://github.com/settings/personal-access-tokens/new
2. **Repository access** → "Only select repositories" → choose `adanttmm/nutricion`
3. **Permissions** → **Repository permissions** → **Contents** → set to **Read and write**. Leave every other permission at "No access".
4. Generate the token and copy it — you won't see it again. You'll paste it into Cloudflare in step 4.

### 2. Create a Cloudflare account + Worker

1. Sign up free at https://dash.cloudflare.com/sign-up (no credit card needed for this).
2. In the dashboard: **Workers & Pages** → **Create** → **Workers** → **Create Worker**. Give it any name, e.g. `nutricion-ratings-sync`.
3. Once created, click **Edit code** (the "Quick edit" editor).
4. Delete the placeholder code and paste in the full contents of [`ratings-sync.js`](./ratings-sync.js) from this folder.
5. Click **Save and deploy**. Note the URL it gives you — something like `https://nutricion-ratings-sync.<your-subdomain>.workers.dev`. You'll need this URL later.

### 3. Create the KV namespace (used for the daily write-cap counter)

1. In the Cloudflare dashboard: **Workers & Pages** → **KV** → **Create a namespace**. Name it `RATINGS_KV`.
2. Go back to your Worker → **Settings** → **Variables** → **KV Namespace Bindings** → **Add binding**.
   - Variable name: `RATINGS_KV` (must match exactly — this is what `env.RATINGS_KV` in the code refers to)
   - KV namespace: the one you just created

### 4. Add the GitHub token as a secret

1. Still in your Worker's **Settings** → **Variables** → **Environment Variables** (or "Secrets", depending on dashboard version) → **Add variable**.
2. Name: `GITHUB_TOKEN`. Value: paste the token from step 1. Make sure it's added as **encrypted/secret**, not plaintext.
3. Save — this redeploys the Worker with the secret available as `env.GITHUB_TOKEN`.

### 5. Tell me the Worker URL

Once deployed, send me the `https://....workers.dev` URL from step 2.5 and I'll wire it into the site (one constant in `skills/site_builder.py`) and rebuild.

## Testing it

After it's wired in, open the live site, rate a dish, and check:
- https://github.com/adanttmm/nutricion/commits/master — a new commit "ratings: auto-sync from site (...)" should appear within a few seconds.
- Run `bash actualizar.sh` (or just `git pull`) locally — the new `data/ratings/ratings_..._web.json` file should show up, and `importar-ratings` should report it.

## Notes on the security model

- The endpoint only accepts requests whose `Origin` header is exactly `https://adanttmm.github.io` — this stops random scripts/pages elsewhere from calling it via a normal browser fetch. It does **not** stop someone with the URL from calling it directly with curl (CORS is enforced by browsers, not servers) — that's an inherent limit of "no login" endpoints, which is why the GitHub token is scoped to *only* this repo's contents, and why there's a hard daily write cap (100/day) as a backstop regardless of who's calling it.
- Worst case if the endpoint is abused: junk JSON files appear under `data/ratings/` (capped at 100/day). `importar-ratings` already validates the file is parseable JSON before doing anything with it, and nothing it does is destructive — it can't overwrite existing files or touch anything outside `data/ratings/`.
- If you ever want to shut this off: revoke the GitHub token (github.com/settings/tokens) or delete/pause the Worker — either one stops it immediately.
