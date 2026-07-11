# Go-live checklist: Google indexing + e-mail delivery

The in-repo work for SEO (meta/OG tags, JSON-LD, robots.txt, sitemap.xml,
canonical URLs, CSP fixes, edge TLS config — see
[SEO_GROWTH_REPORT.md](../SEO_GROWTH_REPORT.md)) and for e-mail (SMTP backend,
console fallback) is **done and deployed**. What remains are account/DNS
actions that only the site owner can perform. Do them in this order.

## 1. Get algomatrics.in indexed by Google

The site currently has **zero pages indexed** because it has never been
verified in Google Search Console — Google has no reason to crawl a brand-new
domain quickly on its own.

1. **Verify the domain in Google Search Console** — <https://search.google.com/search-console>
   - Choose *Domain* property → `algomatrics.in`.
   - GSC shows a TXT record (`google-site-verification=…`); add it at
     GoDaddy → DNS → Records → Add → TXT, host `@`.
   - Verification usually completes within minutes of the DNS record propagating.
2. **Submit the sitemap**: GSC → Sitemaps → enter `https://algomatrics.in/sitemap.xml`.
3. **Request indexing for the key pages**: GSC → URL Inspection → paste
   `https://algomatrics.in/` → *Request indexing*. Repeat for the register page.
4. **Bing** (free traffic, 2 minutes): <https://www.bing.com/webmasters> can
   import the verified GSC property directly, including the sitemap.
5. **Expectations** — indexing typically takes days to a few weeks for a new
   domain. Ranking "on top" for competitive queries (e.g. *algo trading
   platform India*) additionally needs content and backlinks over months:
   the highest-leverage next steps are a blog/docs section targeting long-tail
   queries ("Zerodha algo trading API", "Flattrade API python") and listings
   on relevant directories (Product Hunt, IndiaHacks, trading forums).
   Everything technical (meta, structured data, sitemap, HTTPS, CSP) is
   already in place.

## 2. Make verification e-mails actually deliver

`EMAIL_BACKEND=console` (the current production setting) only prints
verification links to the API container logs — no mail ever leaves the
server. To deliver real mail:

1. **Pick a transactional provider** with a free tier — Brevo (300/day) or
   Resend (100/day) are the fastest to set up. Verify the sending domain
   `algomatrics.in` with the provider.
2. **Add the DNS records the provider gives you at GoDaddy** — an SPF TXT
   record and DKIM CNAME/TXT records. This step is mandatory: the domain has
   `DMARC p=quarantine`, so mail without SPF/DKIM alignment goes to spam or
   is dropped.
3. **Configure the VM** — edit `~/AlgoMatrics/.env` and set **all** of:
   ```bash
   EMAIL_BACKEND=smtp
   SMTP_HOST=<provider smtp host>        # REQUIRED — api crash-loops without it
   SMTP_PORT=587
   SMTP_USERNAME=<provider username>
   SMTP_PASSWORD=<provider password/key>
   SMTP_STARTTLS=true
   EMAIL_FROM=Algo Matrics <no-reply@algomatrics.in>
   APP_BASE_URL=https://algomatrics.in   # links inside the e-mails
   ```
   Then: `sudo docker compose -f deploy/compose/docker-compose.yml up -d --force-recreate api`
   > ⚠️ Setting `EMAIL_BACKEND=smtp` **without** `SMTP_HOST` makes the API
   > refuse to boot (this caused the 2026-07-10 outage).
4. **Test before telling users**:
   ```bash
   sudo docker compose -f deploy/compose/docker-compose.yml exec api \
       python scripts/send_test_email.py your@address.com
   ```
   Check it arrives in the inbox (not spam). Then register a throwaway
   account in the UI and confirm the verification mail arrives.
5. Optional: add an MX record + mailbox/forwarding for `hello@algomatrics.in`
   at GoDaddy so replies/support mail work.
