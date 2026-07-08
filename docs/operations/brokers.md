# Broker integrations (Phase 8)

Every venue is an adapter behind one shared abstraction, so the trading engine
routes orders identically regardless of broker.

## The shared abstraction

`modules/trading/application/broker_port.py` defines the ports every adapter
implements:

- **`BrokerExecutionPort`** — `connect`, `disconnect`, `health`, `submit_order`,
  `cancel_order`, `replace_order`, `stream_order_updates`.
- **`BrokerAccountPort`** — `get_balances`, `get_open_orders`, `get_positions`.

Adapters normalize each venue's payloads and statuses into the domain
`OrderStatus` / `BrokerOrderAck` / `BrokerOrderUpdate` types. The `LiveRouter`
builds the right adapter from a connection's `broker_code` and its decrypted
credentials, then polls `stream_order_updates` for fills.

## Supported venues

| Code | Venue | Assets | Auth | Notes |
|---|---|---|---|---|
| `paper` | Paper | all (sim) | — | Deterministic simulator |
| `zerodha` | Zerodha Kite | Indian equity/F&O | api_key + access_token | |
| `angelone` | Angel One | Indian equity/F&O | api_key + jwt + client_code | |
| `delta` | Delta Exchange | Crypto (India) | api_key + api_secret (HMAC) | |
| `binance` | Binance | Crypto spot | api_key + api_secret (HMAC) | cancel/replace via cancelReplace |
| `interactive_brokers` | Interactive Brokers | Equity/options/futures/forex | gateway_url + account_id | Client Portal gateway; reply-confirmation flow |
| `mt5` | MetaTrader 5 | Forex/CFD | agent_url + agent_token | Via the VPS agent |

## Adding a venue

1. Implement `BrokerExecutionPort` in
   `modules/trading/infrastructure/brokers/<venue>.py` (see `binance.py` /
   `delta.py` as templates), normalizing statuses into `OrderStatus`.
2. Add the code to `BrokerCode` and a branch in `LiveRouter._build_adapter`.
3. Seed the catalog entry (code, name, capabilities, credential fields) in
   `scripts/seed.py`.
4. Add contract tests that drive the adapter through `httpx.MockTransport`
   fixtures (`tests/contract/test_broker_adapters.py`).

## Security notes

- Broker credentials are stored envelope-encrypted (KEK) and decrypted only in
  the trading engine.
- Adapters whose endpoint is user-supplied (MT5 agent, IBKR gateway) restrict
  the URL to an allowlist / HTTPS-or-loopback to prevent server-side request
  forgery. Live trading additionally requires the org setting, a verified
  connection, and a venue instrument mapping.

## Rollback

New adapters are additive branches in the router and new catalog rows; nothing
existing changes. Revert the `phase-8-brokers` branch to remove Binance/IBKR —
the other venues are unaffected. No schema change (catalog rows are seed data).
