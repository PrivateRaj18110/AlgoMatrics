# Connecting a trading device

Any machine — a VPS running strategies, an MT5 terminal, a desktop — can report
to the console with **one URL and one key**. No SDK is required: if it can send
an HTTPS POST with JSON, it can report.

## 1. Create a key

Console → **Operations → Devices → Add device**. Give it a name ("VPS Mumbai 1")
and copy the key it shows. **The key is shown once**; only a hash is stored. If
it is lost, revoke the device and create a new one.

Creating and revoking keys is an organization-management action, so it needs
the owner/admin role and two-factor authentication.

## 2. Send events

```
POST https://algomatrics.in/api/v1/ingest
X-Device-Key: amd_xxxxxxxx_...
Content-Type: application/json
```

The body may be one event, a list of events, or `{"events": [...]}`. Every event
has a `type`; `ts` (ISO-8601 or unix seconds/milliseconds) is optional and
defaults to the time the server received it.

| type        | fields                                                                                  |
|-------------|-----------------------------------------------------------------------------------------|
| `heartbeat` | `cpu`, `ram`, `disk` (percent), `latency_ms`, `version`, `metrics` (object of numbers)  |
| `trade`     | **`symbol`**, **`side`** (`buy`/`sell`), **`qty`**, **`price`**, `pnl`, `strategy`, `order_id`, `account` |
| `positions` | **`positions`**: list of `{symbol, qty, avg_price?, ltp?, pnl?}` — replaces the last list |
| `log`       | **`message`**, `level` (`debug`/`info`/`warning`/`error`/`critical`), `context` (object) |
| `alert`     | **`message`**, `severity` (`info`/`warning`/`critical`), `context` (object)             |

Bold fields are required.

### curl

```bash
curl -sS https://algomatrics.in/api/v1/ingest \
  -H "X-Device-Key: $ALGOMATRICS_DEVICE_KEY" \
  -H "Content-Type: application/json" \
  -d '{"events":[{"type":"heartbeat","cpu":23,"ram":61,"disk":48,"version":"1.4.2"}]}'
```

### Python

```python
import os, time, requests

URL = "https://algomatrics.in/api/v1/ingest"
HEADERS = {"X-Device-Key": os.environ["ALGOMATRICS_DEVICE_KEY"]}

def report(*events):
    r = requests.post(URL, json={"events": list(events)}, headers=HEADERS, timeout=10)
    r.raise_for_status()
    return r.json()          # {"accepted": 2, "by_type": {...}, "rejected": []}

report(
    {"type": "heartbeat", "cpu": 23, "ram": 61, "disk": 48},
    {"type": "trade", "symbol": "RELIANCE", "side": "buy", "qty": 10, "price": 2901.5,
     "strategy": "H30-X2"},
)
report({"type": "alert", "severity": "critical", "message": "Kill switch tripped: daily loss limit"})
```

## 3. What happens

- **Heartbeats** update the device in place: the Devices page shows it online
  (anything received in the last 3 minutes), with CPU/RAM/disk bars. Send one
  every 30–60 s.
- **Trades, logs, alerts** are stored for 30 days and listed per device.
- **Positions** replace the device's previous list.
- **Alerts** (warning/critical) and **error/critical logs** raise an in-app
  notification for the organization (at most 5 per request).

## Limits and errors

- 120 requests per minute per device — batch events (up to 500 per request,
  512 KB per body) instead of sending them one by one.
- Invalid events are rejected individually with a reason in `rejected`; valid
  events in the same request are still accepted.
- `401` = missing, malformed or revoked key. `429` = too many requests; wait
  60 s. `422` = body is not JSON or too large.
