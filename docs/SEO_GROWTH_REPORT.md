# AlgoMatrics — SEO, Indexing, Authority & Growth Report

**Site:** https://algomatrics.in · **Audit date:** 2026-07-10 · **Scope:** full codebase + live deployment + search footprint
**Status:** Critical code fixes are already implemented in this repo (see §4). Server-side actions (DNS, GSC, SMTP env) remain — they are listed as exact steps in §5–§6.

---

## 1. Executive summary

algomatrics.in is **not indexed by Google at all** (`site:algomatrics.in` returns zero results). This is not a penalty and not a content-quality problem — it is a cold start: the production build went live on **2026-07-09** (per the server's `Last-Modified` header), the site has never been submitted to Google Search Console, had no robots.txt or sitemap (both URLs returned the SPA's HTML with HTTP 200), no canonical host (www and apex both serve 200), and has zero external links pointing at it.

The good news: the platform itself is substantial (20 development phases, real product), the landing page copy is genuinely good, the domain is an exact match for the brand, and every blocker found is fixable. The brand SERP ("Algo Matrics", "Algomatrics") is currently occupied by similarly-named but unrelated companies (Algomatic Trading, AlgoMetrics, Algemetric) — none of which own the exact token "algomatrics", so the brand query is winnable within weeks of indexing.

A second, unrelated-looking issue shares a root cause with the SEO problem — **operational config never switched from dev defaults to production**:

- **OTP/verification e-mails are not delivered** because `EMAIL_BACKEND` defaults to `console` (e-mails are written to the API log, never sent). The domain also has **no SPF record and no DKIM**, while its DMARC policy is `p=quarantine` — so even correctly-sent mail would be spam-foldered.
- The site is invisible because nothing production-facing (robots, sitemap, GSC, canonical host, HSTS) was ever set up.

**Five actions produce ~80% of the outcome:**

1. Deploy this branch (robots.txt, sitemap.xml, full metadata/JSON-LD, OG image, security headers are all in the build now).
2. Install `deploy/nginx/edge-tls.conf.example` on the VM → canonical host, HSTS, HTTP/2.
3. Verify the domain in Google Search Console + Bing Webmaster, submit the sitemap, request indexing.
4. Set `EMAIL_BACKEND=smtp` + SMTP credentials + `APP_BASE_URL=https://algomatrics.in` in the production env; add SPF + DKIM DNS records.
5. Publish the trust/legal pages (About, Contact, Privacy, Terms, Risk Disclosure) — mandatory for a YMYL finance product and for payment-provider approval.

---

## 2. Scorecard

Scores reflect the **live deployment as audited**; "after deploy" assumes this branch is deployed and §5–§6 server steps are done. No ranking outcomes are guaranteed.

| Dimension | Today | After deploy + server steps | Main gap remaining |
|---|---|---|---|
| Technical SEO | 22/100 | 78/100 | CSR-only rendering; no prerendered public pages |
| Google Indexing Readiness | 10/100 | 85/100 | Time — Google must crawl; GSC submission required |
| Content | 30/100 | 35/100 | One page of content; no blog/docs/comparisons |
| Performance (CWV) | 72/100 | 80/100 | Route-level code splitting; landing preloads chart bundle |
| Security | 55/100 | 85/100 | CSP/HSTS rollout monitoring; secrets rotation cadence |
| Accessibility | 68/100 | 72/100 | Full axe/Lighthouse pass not yet run; icon `aria-hidden` |
| EEAT / Trust | 18/100 | 40/100 | Legal pages, company identity, author profiles — content work |
| AI Search Readiness (GEO) | 15/100 | 65/100 | Needs public docs + citable content; llms.txt/JSON-LD now in place |

---

## 3. Root cause: why the site appears for nothing

Evidence gathered 2026-07-10:

| Check | Result | Impact |
|---|---|---|
| `site:algomatrics.in` on web search | **0 results** | Not indexed at all |
| `"algomatrics"` query | Unrelated brands (Algomatic Trading, AlgoMetrics.gr, Algemetric, AlgomatixRT) | Brand SERP occupied by name-collisions |
| Homepage first-wave HTML | `<div id="root"></div>` only; title + 1 meta | Nothing to index before JS render; social scrapers see nothing |
| `/robots.txt`, `/sitemap.xml` | HTTP 200 returning the SPA's **HTML** | No crawl directives; soft-404 signals; sitemap unusable |
| Any bogus URL (`/does-not-exist`) | HTTP 200 + HTML | Site-wide soft-404 pattern degrades crawl trust |
| `https://www.algomatrics.in` | 200, identical content, no redirect | Duplicate origin; canonical ambiguity |
| HTTPS response headers | No HSTS, no X-Content-Type-Options, no CSP; `Server: nginx/1.28.3 (Ubuntu)` exposed | Security + Best Practices scoring; version disclosure |
| HTTP protocol | HTTP/1.1 only | Minor performance loss vs h2 |
| `Last-Modified` of index.html | **Thu, 09 Jul 2026** | Domain content is ~1 day old — cold start, zero authority |
| Backlinks | None found | Nothing for crawlers to discover the site through |
| GSC / Bing Webmaster | Never verified (no evidence of tokens anywhere in repo/DNS) | Google has likely never been told the site exists |

**Conclusion:** discoverability failure = (new site) + (never submitted) + (no crawl infrastructure) + (empty server-rendered HTML) + (zero links). All five are addressed by §4–§6.

---

## 4. Implemented in this session (already in the repo)

All changes build cleanly (`npm run build` ✓) and all 17 frontend tests pass (`vitest` ✓).

| # | Change | Files |
|---|---|---|
| 1 | Full SEO `<head>`: keyworded title, description, canonical, Open Graph + Twitter cards, theme-color, icons, manifest | `frontend/index.html` |
| 2 | JSON-LD `@graph`: `Organization` (with `alternateName` "AlgoMatrics"/"Algomatrics" for entity reconciliation), `WebSite`, `SoftwareApplication` (honest `featureList`, free-tier `Offer`; **no fake ratings**) | `frontend/index.html` |
| 3 | `robots.txt` — allows public pages, disallows `/app/`, `/api/`, token-bearing auth routes; declares sitemap | `frontend/public/robots.txt` |
| 4 | `sitemap.xml` — `/`, `/register`, `/login` | `frontend/public/sitemap.xml` |
| 5 | Brand favicon (SVG "A" mark), `apple-touch-icon.png`, PWA `site.webmanifest` | `frontend/public/*` |
| 6 | Social share image 1200×630 (dark brand card with equity curve) | `frontend/public/og.png` |
| 7 | `llms.txt` for AI crawlers (GEO): factual product summary, brokers, risk model, plans | `frontend/public/llms.txt` |
| 8 | Per-route metadata component (title/description/canonical/robots), applied to Landing, Login, Register; `noindex` on the 404 page | `frontend/src/components/Seo.tsx`, page files |
| 9 | `FAQPage` JSON-LD generated from the visible landing FAQ | `frontend/src/pages/LandingPage.tsx` |
| 10 | Fixed broken public contact e-mail `hello@algomatrics.local` → `hello@algomatrics.in` | `frontend/src/pages/LandingPage.tsx` |
| 11 | Inline theme script externalized to `/theme-init.js` → enables strict `script-src 'self'` CSP | `frontend/index.html`, `frontend/public/theme-init.js` |
| 12 | Container nginx: added CSP, fixed the **header-inheritance bug** (locations with their own `add_header` were silently dropping all security headers), `Referrer-Policy` → `strict-origin-when-cross-origin`, correct `.webmanifest` MIME, gzip for XML/manifest | `deploy/nginx/nginx.conf` |
| 13 | New **edge TLS config** for the VM: HTTP→HTTPS 301, www→apex 301, HTTP/2, HSTS, proxy to app container | `deploy/nginx/edge-tls.conf.example` |
| 14 | Production e-mail guidance + defaults fixed (`no-reply@algomatrics.in`, SPF/DKIM/APP_BASE_URL checklist) | `.env.example`, `backend/src/algo_platform/config.py` |

---

## 5. OTP / verification e-mail: diagnosis and exact fix

### What the code does

Registration (`backend/src/algo_platform/modules/identity/application/auth_service.py:149`) issues a 24-hour **verification link** (not a numeric code) and sends it through the `EmailSender` port. The sender is chosen in `backend/src/algo_platform/shared/infrastructure/email.py:79`:

- `EMAIL_BACKEND=console` (the **default**, and the value in `.env.example`) → the e-mail is **written to the API log** (`email.console_delivery` event) and never leaves the server.
- `EMAIL_BACKEND=smtp` → real SMTP delivery via STARTTLS/TLS.

`docs/PRODUCTION_READINESS.md:146` has this exact item as an **unchecked** checklist box. Notification e-mails additionally pass through a dispatcher that deliberately swallows failures (`notification.channel_delivery_failed` warning only) — so delivery problems are invisible unless you read logs.

### Layered root cause

1. **Backend layer (certain):** production is almost certainly running `EMAIL_BACKEND=console`. No mail is generated at all. Verify instantly: `docker logs <api-container> | grep email.console_delivery` — if registration attempts show up there, this is confirmed.
2. **DNS layer (confirmed by lookup):** `algomatrics.in` has **no SPF TXT record**, **no DKIM**, **no MX**, but **does** have DMARC `p=quarantine` (GoDaddy default). Consequence: once SMTP is enabled, unauthenticated mail claiming `@algomatrics.in` will fail DMARC and be quarantined/spam-foldered. This must be fixed together with #1 or "OTP not delivered" will persist with a different cause.
3. **Config layer:** `APP_BASE_URL` defaults to a localhost URL. If the production env doesn't set it, even delivered e-mails would contain `http://localhost:8080/verify-email?...` links. Set it to `https://algomatrics.in`.

### Exact fix (30–45 min)

1. Pick a transactional provider (Amazon SES, Postmark, Brevo, or Zoho ZeptoMail — all have India-friendly free/cheap tiers). Verify the domain `algomatrics.in` there.
2. Production `.env` on the VM:
   ```env
   EMAIL_BACKEND=smtp
   EMAIL_FROM=Algo Matrics <no-reply@algomatrics.in>
   SMTP_HOST=<provider smtp host>
   SMTP_PORT=587
   SMTP_USERNAME=<provider user>
   SMTP_PASSWORD=<provider key>
   SMTP_STARTTLS=true
   APP_BASE_URL=https://algomatrics.in
   ```
   Restart the API container.
3. GoDaddy DNS for `algomatrics.in`:
   - TXT `@` → `v=spf1 include:<provider-spf> ~all`
   - DKIM CNAME(s) exactly as the provider specifies
   - Keep DMARC as-is initially; once SPF/DKIM pass, it stops hurting you
   - If you want to **receive** at `hello@algomatrics.in` (the address now published on the landing page): add the mailbox provider's MX records (e.g., Zoho Mail free tier). **Today there are no MX records — inbound mail to hello@ bounces.**
4. Validate: register a test account → e-mail arrives (check spam) → send a probe to `check@mail-tester.com` and confirm ≥9/10 (SPF pass, DKIM pass, DMARC aligned).
5. Optional hardening: registration currently awaits SMTP inline; a provider outage would 500 the register endpoint. There is an outbox scaffold (`shared/infrastructure/email_outbox.py`) — moving verification mail onto it gives retries + isolation. Priority: Medium.

---

## 6. Google indexing playbook (do in this order)

1. **Deploy this branch** (frontend rebuild + container restart). Verify:
   `curl -s https://algomatrics.in/robots.txt` → text/plain rules; `curl -s https://algomatrics.in/sitemap.xml` → XML; homepage source shows canonical/OG/JSON-LD.
2. **Install the edge config** (`deploy/nginx/edge-tls.conf.example` → `/etc/nginx/sites-available/algomatrics.in`, symlink, `nginx -t`, reload). Verify: `curl -I https://www.algomatrics.in` → `301` to apex; `curl -I https://algomatrics.in` → `strict-transport-security` header present, HTTP/2.
3. **Google Search Console:** add a **Domain property** for `algomatrics.in`; verify via the GoDaddy DNS TXT record GSC gives you. Submit `https://algomatrics.in/sitemap.xml`. Use **URL Inspection → Request Indexing** on `/` and `/register`.
4. **Bing Webmaster Tools:** "Import from GSC" (one click), or verify DNS. Bing feeds ChatGPT/Copilot answers — it matters for GEO.
5. **IndexNow:** generate a key, drop `<key>.txt` into `frontend/public/`, and ping `https://api.indexnow.org/indexnow?url=https://algomatrics.in/&key=<key>` on each deploy (one curl line in the deploy script). Covers Bing/Yandex/Seznam instantly.
6. **Entity anchors** (also your first backlinks): create/complete a **LinkedIn company page**, **GitHub organization** (link the repo → site), **Crunchbase profile**, and Google Business Profile if there's an office. These teach Google's Knowledge Graph that "Algo Matrics" = algomatrics.in, which is how you beat the name-collision brands.
7. Expect: crawl within days of GSC submission; brand-query ranking typically 1–6 weeks for an exact-match domain with entity anchors. Watch GSC **Pages** report for "Crawled – currently not indexed" (normal early; resolves as internal content and links grow).

---

## 7. Remaining issues & opportunities (prioritized)

Only defensible, evidence-based items are listed — no padding to hit a round number.

### Critical (this week)

| Issue | Root cause | Fix | Effort |
|---|---|---|---|
| Production env still on dev defaults (email, base URL) | `.env` never productionized | §5 | 1h |
| No SPF/DKIM/MX on domain | DNS never configured | §5.3 | 30m |
| Not in GSC/Bing | Never submitted | §6 | 1h |
| No canonical host / HSTS / h2 on live edge | Host nginx minimal config | §6.2 | 30m |
| No legal/trust pages (Privacy, Terms, Risk Disclosure, Refunds, About, Contact) | Not built | Build 6 static routes; footer links; add to sitemap. **YMYL finance sites are held to elevated EEAT standards; payment providers (Razorpay) also require these pages.** | 1–2d |

### High (this month)

| Issue | Fix | Effort |
|---|---|---|
| Public pages are client-rendered only — first-wave HTML is empty; non-Google crawlers and AI scrapers see nothing | Prerender the public routes. Pragmatic path: `vite-prerender-plugin` or a puppeteer post-build snapshot of `/`, `/login`, `/register` into static HTML served by nginx. Strategic path (if a blog/docs are coming): move the marketing site to Astro/Next SSG on the apex, keep the console SPA under `/app` | 1–3d |
| Landing page preloads the 397 KB charts chunk it never renders | Route-level `React.lazy` splitting so `/` ships react+index only (~135 KB gzip). Improves LCP/INP on the page Google actually scores | 0.5–1d |
| Soft-404 for unknown routes (200 + index.html) | Acceptable for SPAs (Google detects soft-404s), but after prerendering add a real 404 for non-app paths at nginx | 2h |
| Pricing section renders only from API (`usePlans`) | Ship static fallback plan data so pricing is visible if the API hiccups during render | 2h |
| No analytics / no CWV field data | Add a privacy-friendly analytics (Plausible/Umami self-hosted keeps CSP `connect-src 'self'` intact if proxied) + GSC CWV monitoring | 0.5d |
| `X-Frame-Options DENY` but no `frame-ancestors` before this branch; verify CSP rollout | Deploy new nginx.conf; watch console for CSP violations for a week before tightening further | 1h |

### Medium (quarter)

- Blog + docs infrastructure (SSG, RSS feed, per-post JSON-LD `Article` + author profiles). The `docs/` directory already contains real architecture/runbook material — publishable with editing.
- Comparison/alternative pages (see keyword map) — highest commercial intent.
- `BreadcrumbList` schema once multi-level public pages exist.
- Status page (uptime) — trust signal for a trading platform.
- Accessibility pass: `aria-hidden` on decorative SVGs, focus states audit, full Lighthouse/axe run, form error `aria-live`.
- Move verification e-mail onto the outbox with retries (§5.5).
- OG image per future content page (template exists in the scratchpad script).

---

## 8. Keyword strategy

**Priority logic:** win the brand first (weeks), then long-tail India-specific and integration keywords (months), then head terms (year+). Intent: I=informational, C=commercial, T=transactional, N=navigational.

| Cluster | Example keywords | Intent | Competition | Target page |
|---|---|---|---|---|
| Brand | algomatrics, algo matrics, algomatrics platform/login | N | None (win in weeks) | `/`, entity anchors |
| India algo platform | algo trading platform india, SEBI algo trading rules 2026, best algo trading software india | C/I | Med-High (Tradetron, AlgoTest, uTrade) | Landing + solution pages |
| Broker integrations | kite connect python, angel one smartapi tutorial, delta exchange api, mt5 automation vps | I/C | Low-Med — **best early opportunity**: developers searching these convert well | Docs + tutorials |
| Backtesting | backtest nifty strategy python, backtesting vs paper trading, walk-forward analysis | I | Med | Blog cluster G |
| Risk | kill switch algo trading, position sizing rules, max drawdown limits | I | Low | Blog cluster H |
| Options India | banknifty algo strategy, nifty options backtest, straddle automation | I/C | Med | Blog cluster K |
| Head terms | algorithmic trading, quant trading platform, automated trading software | C | Very high (year-1 goal: page 2–3) | Whole-site authority |

---

## 9. Content ecosystem — 200+ ideas in topical clusters

Publish order: 2 posts/week minimum; every post links to one money page and two sibling posts. Authors must have real bios (EEAT).

**A. Algo trading in India — fundamentals (12):** What is algo trading (India-specific); Is algo trading legal in India; SEBI's retail algo framework explained; Algo vs manual trading returns evidence; How much capital do you need; Algo trading taxation in India; Choosing your first strategy type; Latency reality for retail; Common myths; First 90 days checklist; Costs breakdown (broker+platform+data); Discretionary-to-systematic transition guide.

**B. SEBI & compliance (10):** SEBI algo circular timeline; Exchange approval for retail algos; Broker API compliance duties; Audit-trail requirements; Risk controls SEBI expects; Order-tagging rules; What "algo ban" headlines actually mean; Compliance checklist for API traders; Static IP & 2FA broker rules; SEBI vs US regulation comparison.

**C. Zerodha Kite Connect (12):** Complete Kite Connect Python guide; Auth/token refresh flow; Order placement patterns; WebSocket market data; Historical data limits & workarounds; Rate limits explained; Common errors decoded; Kite Connect vs Algo Matrics managed connection; Paper-testing a Kite strategy safely; Kill switch on Kite; Multi-account patterns; Cost analysis.

**D. Angel One SmartAPI (10):** SmartAPI Python quickstart; Auth & TOTP setup; Order types mapped; SmartAPI vs Kite Connect; WebSocket streams; Historical candles; Error handling; Free API economics; Common pitfalls; Managed integration guide.

**E. Delta Exchange & crypto (10):** Delta API guide; Perpetual futures algos 101; Funding-rate strategies; Crypto vs equity microstructure; 24/7 risk management; Basis trading; Crypto backtest data pitfalls; INR settlement mechanics; Position limits; Volatility regime filters.

**F. MetaTrader 5 (10):** MT5 automation via VPS agent; MT5 Python integration; EA vs platform-managed strategies; Broker latency comparison; MT5 risk settings; Forex session filters; Slippage measurement; MT5-to-multi-broker migration; Copy-trading vs algo; MT5 backtest vs platform backtest fidelity.

**G. Backtesting (12):** Backtesting guide for Indian markets; Survivorship bias; Look-ahead bias; Realistic slippage & fees modeling; Walk-forward analysis; Overfitting detection; In/out-of-sample splits; Monte Carlo on equity curves; Data quality for NSE; Backtest→paper→live pipeline; Metrics that matter (Sharpe/Sortino/MAR); Why deterministic fills matter.

**H. Risk management (12):** Position sizing methods compared; Kelly criterion practical limits; Hierarchical risk limits (platform/account/strategy); Kill-switch design; Fail-closed vs fail-open; Max daily loss rules; Correlation risk across strategies; Leverage rules for retail; Drawdown recovery math; Pre-trade checks list; Circuit breakers on NSE; Risk report anatomy.

**I. Python & SDK tutorials (12):** Write your first strategy with the SDK; SMA crossover walkthrough; RSI mean-reversion walkthrough; Momentum breakout walkthrough; Custom indicators; Multi-timeframe strategies; Event-driven vs vectorized; State management in live strategies; Logging/observability for strategies; Testing strategies with pytest; Sandboxing & why uploads are reviewed; From Jupyter notebook to production.

**J. Strategy deep-dives (12):** Moving-average systems on Nifty (evidence); Mean reversion in Indian large-caps; Momentum across NSE sectors; Opening range breakout; VWAP execution; Pairs trading feasibility for retail; Volatility breakout; Trend filters that reduce whipsaws; Seasonality on Indian indices; Expiry-day effects; Gap statistics; When strategies stop working (regime change).

**K. Options & derivatives (12):** BankNifty algo strategy guide; Nifty options backtesting; Automated straddles/strangles; Delta hedging automation; Options Greeks for algo traders; IV rank filters; Weekly expiry playbook; Margin math for options algos; Spread execution quality; Event-day risk (budget/RBI); Options data sources; Payoff analytics.

**L. Paper trading (8):** Paper trading guide; How long to paper trade before live; Deterministic fills explained; Paper vs live divergence sources; Simulated slippage models; Metrics to graduate to live; Paper trading psychology; Free paper trading setup on Algo Matrics.

**M. Comparisons & alternatives (12):** Algo Matrics vs Tradetron; vs AlgoTest; vs Streak; vs uTrade Algos; vs AlgoBulls; vs QuantConnect (global); vs building it yourself (DIY stack cost analysis); vs Excel/Sheets trading; Best algo platforms India (honest roundup); Best backtesting tools India; Multi-broker platforms compared; Open-source vs SaaS algo stacks. *(Comparisons must be factual and current — this is both the highest-converting and the most EEAT-sensitive cluster.)*

**N. Glossary (15):** Definitional pages (~400 words + schema): Algorithmic trading; Backtesting; Paper trading; Slippage; Order management system; Execution engine; Kill switch; Drawdown; Sharpe ratio; Walk-forward analysis; Market scanner; OCO orders; Bracket orders; Latency; Multi-tenancy (in trading SaaS). Interlink heavily — glossaries earn AI-answer citations (GEO).

**O. Execution & microstructure (10):** Market vs limit in algos; Order slicing basics; NSE order-matching mechanics; Best execution measurement; Partial fills handling; Requote/rejection handling; Smart order routing (multi-broker); Execution analytics dashboard tour; Latency budgets by strategy type; Order audit trails.

**P. Quant research (10):** Feature engineering for Indian equities; Data vendors for NSE compared; Corporate-actions adjustment; Regime detection methods; ML for trading — hype vs evidence; Backtest statistics validity; Portfolio construction for strategy sets; Strategy capacity estimation; Research→production workflow; Reproducibility in quant research.

**Q. Product & engineering blog (10):** Architecture of a multi-tenant trading platform; How our risk engine fails closed; Deterministic paper-fill engine design; Envelope encryption for broker keys; WebSocket P&L at scale; Sandboxing user Python; Event-sourced audit logs; Zero-downtime deploys for trading systems; Building the strategy marketplace; Postmortem culture. *(These earn Hacker News / dev-community links — your strongest realistic backlink channel.)*

**R. Question-based long-tail / FAQ (15+):** Can I automate Zerodha without coding; Is API trading safe; How to get Kite Connect API key; Angel One SmartAPI free?; What happens if my algo loses internet; Can algos trade MCX; How to stop an algo instantly; Minimum capital for BankNifty algo; Is backtest profit realistic; Do I need a VPS; How are algo profits taxed; Can I run multiple strategies on one account; What is a good Sharpe for retail; Why did my order get rejected; How do trading platforms keep API keys safe.

**Total: ~204 ideas across 18 clusters.**

---

## 10. Competitor landscape

| Competitor | Type | Strengths | Your differentiation |
|---|---|---|---|
| Tradetron | Direct (India) | Huge template marketplace, brand, backlinks | Real Python SDK + deterministic backtests vs no-code condition builder; cleaner risk model |
| AlgoTest | Direct (India) | Free options backtesting, strong SEO on "backtest" terms | Live multi-broker execution + risk engine, not just backtests |
| Streak (Zerodha) | Direct (India) | Zerodha distribution | Multi-broker (not locked to one), crypto + MT5 reach |
| uTrade Algos / AlgoBulls | Direct (India) | Funded, content-heavy | Engineering transparency, self-serve dev experience |
| QuantConnect | Global | Massive docs/community — the GEO benchmark | India-first: SEBI context, Indian brokers, INR pricing |
| Name-collision set (Algomatic Trading, AlgoMetrics, Algemetric, AlgomatixRT) | Brand SERP squatters (unintentional) | Currently outrank you for your own name | Exact-match domain + entity anchors + GSC → displaceable |

**Structural insight:** every strong Indian competitor wins via either distribution (Streak) or content volume (AlgoTest, Tradetron). Nobody in the India niche publishes serious engineering content (cluster Q) — that lane is open and it compounds into backlinks that marketing content can't earn.

---

## 11. EEAT & trust (YMYL — this site handles money)

Minimum bar (week 1–2): About page with the real legal entity name and founders; Contact page (working e-mail — requires MX fix from §5 — and expected response time); Privacy Policy; Terms of Service; **Risk Disclosure** ("capital at risk", no assured-returns language anywhere, SEBI-context disclaimer); Refund/Cancellation policy (Razorpay requirement); Security page (envelope encryption of broker keys, RBAC, audit logs — the platform genuinely has these; say so).
Next tier: author bios with credentials on every article; a public changelog; status/uptime page; genuine user testimonials (never fabricated — prohibited and detectable); case studies with real numbers and permission.

## 12. AI search / GEO

Done in this branch: JSON-LD entity graph, `alternateName` variants, `llms.txt`, FAQPage schema, semantic HTML. Next: publish the docs publicly (AI engines cite documentation heavily); keep a stable URL structure; add `Article` + `author` schema to blog posts; seed authentic presence in the communities LLMs cite (Stack Overflow answers on Kite Connect/SmartAPI questions, GitHub discussions); glossary cluster N is the highest-yield GEO asset. Track referrals from chatgpt.com/perplexity.ai/gemini in analytics.

## 13. Backlink plan (white-hat only)

In rough order of effort-to-value for this product: (1) GitHub org + any open-sourced SDK/examples repo — dev backlinks compound; (2) engineering-blog posts submitted to Hacker News / r/algotrading / IndieHackers (genuine participation, not drive-by links); (3) Product Hunt launch once trust pages + onboarding are solid (aim month 2–3); (4) Indian startup directories (YourStory, Inc42 listings), Crunchbase, F6S; (5) guest posts / podcasts in the Indian fintech-dev niche; (6) broker developer-community presence (Kite Connect forum is high-traffic and on-topic); (7) college quant/fintech club workshops (universities link freely and carry authority). **Never:** purchased links, PBNs, link exchanges, fake reviews.

## 14. Roadmap

**24 hours:** deploy branch → install edge config → GSC + Bing verification → submit sitemap → request indexing → SMTP env + SPF/DKIM DNS → verify OTP e-mail end-to-end.
**Week 1:** legal/trust pages live + in sitemap; MX for hello@; analytics + CWV monitoring; IndexNow in deploy script; LinkedIn/GitHub/Crunchbase entity anchors; monitor GSC coverage daily.
**30 days:** route-level code splitting; prerender public routes (or commit to the SSG marketing-site split); first 8 content pieces (2×A, 1×C, 1×D, 2×N, 1×M, 1×Q); publish docs; accessibility pass; Lighthouse ≥95 on `/`.
**90 days:** 25–30 published pieces across clusters; all comparison pages; Product Hunt launch; first engineering post on HN; status page; GSC review — expect brand queries won and first long-tail impressions.
**6 months:** 60+ pieces; broker-integration tutorials ranking (cluster C/D are winnable); backlinks from 20+ referring domains; AI-engine citations appearing for glossary/docs; evaluate hreflang only if a non-Indian audience materializes.
**12 months:** topical authority in "India algo trading" cluster; head terms ("algo trading platform india") page 1–2 target; 150+ indexed quality pages; organic signups as the primary acquisition channel. *(Directional targets, not guarantees.)*

## 15. Measurement

Weekly: GSC impressions/clicks (brand vs non-brand), coverage errors, CWV field data, referring domains (GSC links report), signup conversions by landing page, AI-referral sessions. North-star: **organic registrations/week**. Guardrails: zero manual actions, zero soft-404 growth, e-mail delivery rate >98%.

---

## Appendix A — validation commands

```bash
curl -s https://algomatrics.in/robots.txt          # expect text rules, not HTML
curl -s https://algomatrics.in/sitemap.xml | head  # expect XML
curl -I https://www.algomatrics.in                 # expect 301 → apex
curl -I https://algomatrics.in                     # expect HSTS, h2, security headers
docker logs <api> | grep email.console_delivery    # must be EMPTY after SMTP switch
nslookup -type=TXT algomatrics.in                  # expect v=spf1 record
```
Rich results test: https://search.google.com/test/rich-results on `/` (expect Organization, SoftwareApplication, FAQPage).
Mail: send to check@mail-tester.com → ≥9/10.
