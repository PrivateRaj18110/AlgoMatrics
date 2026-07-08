# Secrets management (Phase 2)

The platform resolves sensitive material — JWT signing keys, the broker
credential KEK, and payment-provider secrets — through a pluggable
`SecretsProvider`. Selecting a backend never changes the security model of the
consumers; it only changes where the value comes from.

## Model

```
consumer (JwtService, CredentialCipher, payment providers)
      │
      ▼
SecretsResolver ──▶ SecretsProvider (env | aws | encrypted)
      │                     │
      └── fallback ─────────┘  (missing/failed managed secret → .env/settings)
```

- `shared/infrastructure/secrets/provider.py` — port + resolver + factory.
- The resolver consults the managed backend first and **always falls back** to
  the pre-existing settings loader. A backend outage or a missing key can never
  break a deployment that already worked on `.env`.

### Canonical secret names

Managed backends key their values by these names:

| Name | Consumer |
|------|----------|
| `jwt_private_key`, `jwt_public_key` | JWT signing/verification |
| `broker_credential_kek` | broker credential envelope encryption (base64) |
| `razorpay_key_secret`, `razorpay_webhook_secret` | Razorpay |
| `stripe_secret_key`, `stripe_webhook_secret` | Stripe |

## Backends

### `env` (default)

No change from prior behaviour. Optionally override a single secret without
touching `.env` by setting `ALGO_SECRET_<NAME>` (e.g.
`ALGO_SECRET_STRIPE_SECRET_KEY`). Blank values are treated as unset.

### `aws` — AWS Secrets Manager

```
SECRETS_BACKEND=aws
AWS_SECRETS_ID=algo-matrics/prod      # a single JSON document keyed by the names above
AWS_REGION=ap-south-1
SECRETS_CACHE_TTL_SECONDS=300
```

Requires the `aws` extra (`uv sync --extra aws` / `pip install '.[aws]'`).
Values are cached for the TTL; **rotation is picked up automatically** on the
next fetch after expiry. During a transient Secrets Manager outage the last
good values are served.

### `encrypted` — local development

Keep real credentials in the working tree as a Fernet-encrypted document while
the key stays out of the repo.

```bash
# 1. generate a key; store it outside the repo (env var or key file)
python -m algo_platform.scripts.secrets_cli keygen
export SECRETS_ENCRYPTION_KEY=<generated>

# 2. write a plaintext JSON document (gitignored) and encrypt it
cat > secrets.plain.json <<'JSON'
{ "stripe_secret_key": "sk_test_...", "broker_credential_kek": "base64==" }
JSON
python -m algo_platform.scripts.secrets_cli encrypt \
  --in secrets.plain.json --out var/secrets.enc

# 3. point the app at it
#    SECRETS_BACKEND=encrypted
#    SECRETS_ENCRYPTED_FILE=var/secrets.enc
#    SECRETS_ENCRYPTION_KEY_FILE=/path/outside/repo/secrets-key
```

`secrets.enc` is safe to share (it is ciphertext); the key is not. `.gitignore`
blocks `secrets.plain.json` and key files as a safety net.

## Never in logs

`configure_logging` installs a redaction processor that masks any structured-log
field whose key looks like a secret (`password`, `secret`, `token`,
`authorization`, `api_key`, `private_key`, `kek`, `credential`, `passphrase`),
recursing into nested structures. This is defence in depth — code should still
avoid logging secret values in the first place.

## Rollback

Fully additive and reversible:

- **Instant revert:** set `SECRETS_BACKEND=env`. The app resolves secrets exactly
  as it did before Phase 2; no managed backend is contacted.
- **Code revert:** the work is isolated to the `phase-2-secrets` branch and
  involves no database migration or API-contract change, so `git revert` of the
  slice commits is safe at any time.
- The log-redaction processor is safe to keep even after a revert of the rest.
