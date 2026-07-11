"""Connection verification against real venue APIs.

Each verifier performs the cheapest authenticated read the venue offers
(profile/health) and normalizes the outcome. Credentials never leave this
process and are never logged.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Protocol
from urllib.parse import urlsplit

import httpx

from algo_platform.modules.brokerage.domain.brokers import BrokerCode

_TIMEOUT = httpx.Timeout(15.0)

KITE_BASE = "https://api.kite.trade"
ANGEL_BASE = "https://apiconnect.angelone.in"
DELTA_BASE = "https://api.india.delta.exchange"
FLATTRADE_BASE = "https://piconnect.flattrade.in/PiConnectTP"


@dataclass(frozen=True, slots=True)
class VerificationResult:
    ok: bool
    external_account_id: str = ""
    message: str = ""
    base_currency: str = "INR"


class BrokerVerifier(Protocol):
    async def verify(self, credentials: dict[str, str]) -> VerificationResult: ...


class PaperVerifier:
    """The paper venue is platform-internal; verification checks the config."""

    async def verify(self, credentials: dict[str, str]) -> VerificationResult:
        raw_balance = credentials.get("starting_balance", "1000000")
        try:
            balance = Decimal(raw_balance)
        except InvalidOperation:
            return VerificationResult(ok=False, message="starting balance must be a number")
        if balance <= 0 or balance > Decimal("1000000000"):
            return VerificationResult(
                ok=False, message="starting balance must be between 1 and 1,000,000,000"
            )
        currency = (credentials.get("base_currency") or "INR").upper()
        if len(currency) != 3:
            return VerificationResult(ok=False, message="base currency must be a 3-letter code")
        return VerificationResult(
            ok=True,
            external_account_id="paper-simulator",
            message="paper trading account ready",
            base_currency=currency,
        )


class ZerodhaVerifier:
    """Kite Connect: GET /user/profile with `token api_key:access_token`."""

    async def verify(self, credentials: dict[str, str]) -> VerificationResult:
        api_key = credentials.get("api_key", "")
        access_token = credentials.get("access_token", "")
        headers = {
            "X-Kite-Version": "3",
            "Authorization": f"token {api_key}:{access_token}",
        }
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                response = await client.get(f"{KITE_BASE}/user/profile", headers=headers)
        except httpx.HTTPError as error:
            return VerificationResult(ok=False, message=f"network error: {type(error).__name__}")
        if response.status_code == 200:
            data = response.json().get("data", {})
            return VerificationResult(
                ok=True,
                external_account_id=str(data.get("user_id", "")),
                message="Kite profile fetched",
                base_currency="INR",
            )
        if response.status_code in {401, 403}:
            return VerificationResult(ok=False, message="Kite rejected the credentials")
        return VerificationResult(ok=False, message=f"Kite returned HTTP {response.status_code}")


class AngelOneVerifier:
    """Angel One SmartAPI: GET user profile with a session JWT + API key."""

    async def verify(self, credentials: dict[str, str]) -> VerificationResult:
        jwt_token = credentials.get("jwt_token", "")
        api_key = credentials.get("api_key", "")
        client_code = credentials.get("client_code", "")
        headers = {
            "Authorization": f"Bearer {jwt_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-UserType": "USER",
            "X-SourceID": "WEB",
            "X-ClientLocalIP": "127.0.0.1",
            "X-ClientPublicIP": "127.0.0.1",
            "X-MACAddress": "00:00:00:00:00:00",
            "X-PrivateKey": api_key,
        }
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                response = await client.get(
                    f"{ANGEL_BASE}/rest/secure/angelbroking/user/v1/getProfile",
                    headers=headers,
                )
        except httpx.HTTPError as error:
            return VerificationResult(ok=False, message=f"network error: {type(error).__name__}")
        if response.status_code == 200:
            body = response.json()
            if body.get("status") is True:
                data = body.get("data") or {}
                return VerificationResult(
                    ok=True,
                    external_account_id=str(data.get("clientcode", client_code)),
                    message="SmartAPI profile fetched",
                    base_currency="INR",
                )
            return VerificationResult(
                ok=False, message=str(body.get("message", "SmartAPI rejected the session"))
            )
        return VerificationResult(
            ok=False, message=f"SmartAPI returned HTTP {response.status_code}"
        )


class FlattradeVerifier:
    """Flattrade (Noren REST): POST UserDetails with jData/jKey envelope."""

    async def verify(self, credentials: dict[str, str]) -> VerificationResult:
        client_code = credentials.get("client_code", "")
        session_token = credentials.get("session_token", "")
        jdata = f'{{"uid":"{client_code}","actid":"{client_code}"}}'
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                response = await client.post(
                    f"{FLATTRADE_BASE}/UserDetails",
                    content=f"jData={jdata}&jKey={session_token}",
                    headers={"Content-Type": "text/plain"},
                )
        except httpx.HTTPError as error:
            return VerificationResult(ok=False, message=f"network error: {type(error).__name__}")
        if response.status_code == 200:
            body = response.json()
            if body.get("stat") == "Ok":
                return VerificationResult(
                    ok=True,
                    external_account_id=str(body.get("actid", client_code)),
                    message="Flattrade profile fetched",
                    base_currency="INR",
                )
            return VerificationResult(
                ok=False, message=str(body.get("emsg", "Flattrade rejected the session"))
            )
        return VerificationResult(
            ok=False, message=f"Flattrade returned HTTP {response.status_code}"
        )


class DeltaVerifier:
    """Delta Exchange: signed GET /v2/profile (HMAC-SHA256 of method+ts+path)."""

    async def verify(self, credentials: dict[str, str]) -> VerificationResult:
        api_key = credentials.get("api_key", "")
        api_secret = credentials.get("api_secret", "")
        path = "/v2/profile"
        timestamp = str(int(time.time()))
        signature_payload = f"GET{timestamp}{path}"
        signature = hmac.new(
            api_secret.encode("utf-8"), signature_payload.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        headers = {
            "api-key": api_key,
            "timestamp": timestamp,
            "signature": signature,
            "Accept": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                response = await client.get(f"{DELTA_BASE}{path}", headers=headers)
        except httpx.HTTPError as error:
            return VerificationResult(ok=False, message=f"network error: {type(error).__name__}")
        if response.status_code == 200:
            body = response.json().get("result", {})
            return VerificationResult(
                ok=True,
                external_account_id=str(body.get("email", body.get("id", ""))),
                message="Delta profile fetched",
                base_currency="USD",
            )
        if response.status_code in {401, 403}:
            return VerificationResult(ok=False, message="Delta rejected the credentials")
        return VerificationResult(ok=False, message=f"Delta returned HTTP {response.status_code}")


class Mt5AgentVerifier:
    """MT5 runs on a Windows VPS agent; verification pings the agent's health API."""

    def __init__(
        self,
        *,
        allowed_hosts: frozenset[str] | None = None,
        require_https: bool = False,
    ) -> None:
        self._allowed_hosts = allowed_hosts
        self._require_https = require_https

    async def verify(self, credentials: dict[str, str]) -> VerificationResult:
        agent_url = credentials.get("agent_url", "").rstrip("/")
        agent_token = credentials.get("agent_token", "")
        parsed = urlsplit(agent_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username:
            return VerificationResult(ok=False, message="agent URL must be http(s)")
        if self._require_https and parsed.scheme != "https":
            return VerificationResult(ok=False, message="agent URL must use HTTPS")
        hostname = parsed.hostname.lower()
        if self._allowed_hosts is not None and hostname not in self._allowed_hosts:
            return VerificationResult(
                ok=False,
                message="agent host is not in the platform allowlist",
            )
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                response = await client.get(
                    f"{agent_url}/health",
                    headers={"Authorization": f"Bearer {agent_token}"},
                )
        except httpx.HTTPError as error:
            return VerificationResult(
                ok=False, message=f"agent unreachable: {type(error).__name__}"
            )
        if response.status_code == 200:
            body = response.json()
            terminal = bool(body.get("terminal_connected", False))
            account = str(body.get("account", credentials.get("mt5_login", "")))
            if not terminal:
                return VerificationResult(
                    ok=False, message="agent is up but the MT5 terminal is not connected"
                )
            return VerificationResult(
                ok=True,
                external_account_id=account,
                message="MT5 agent healthy",
                base_currency=str(body.get("currency", "USD")),
            )
        if response.status_code in {401, 403}:
            return VerificationResult(ok=False, message="agent rejected the token")
        return VerificationResult(ok=False, message=f"agent returned HTTP {response.status_code}")


def build_verifier_registry(
    *,
    mt5_allowed_hosts: list[str] | None = None,
    mt5_require_https: bool = False,
) -> dict[str, BrokerVerifier]:
    allowed = (
        frozenset(host.strip().lower() for host in mt5_allowed_hosts if host.strip())
        if mt5_allowed_hosts is not None
        else None
    )
    return {
        BrokerCode.PAPER.value: PaperVerifier(),
        BrokerCode.ZERODHA.value: ZerodhaVerifier(),
        BrokerCode.ANGELONE.value: AngelOneVerifier(),
        BrokerCode.FLATTRADE.value: FlattradeVerifier(),
        BrokerCode.DELTA.value: DeltaVerifier(),
        BrokerCode.MT5.value: Mt5AgentVerifier(
            allowed_hosts=allowed,
            require_https=mt5_require_https,
        ),
    }
