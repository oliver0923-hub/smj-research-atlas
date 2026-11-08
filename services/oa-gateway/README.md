# DOI-restricted OA document gateway

Production: https://smj-oa-gateway-oliver.oliver0923.chatgpt.site

`POST /api/document` with JSON `{ "doi": "10.1002/smj.3340" }` and the Atlas origin. No caller URLs, tokens or arbitrary content. GET `/api/health` reports deployed version and persistent quota availability.

Build: `node scripts/build.mjs`. Tests: `node --test tests/*.test.mjs`. The emitted `dist/` follows the Sites Worker manifest contract; `.openai/hosting.json` identifies the dedicated service. D1 binding `DB` and migrations are required; requests fail closed without the quota store. Deploy this source through the Sites source/save/deploy workflow; GitHub frontend CI does not redeploy this independently hosted backend. No R2 storage, PDF persistence or user credentials.

See ../../docs/ON_DEMAND_ONE_PAPER.md for quotas, security boundaries, actual retrieval outcomes and limitations.
