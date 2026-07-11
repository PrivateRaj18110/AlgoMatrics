"""Application settings schemas."""

from typing import Literal

from pydantic import BaseModel

ThemeMode = Literal["dark", "light"]


class NotificationChannels(BaseModel):
    telegram: bool = False
    browser: bool = False
    email: bool = False


class AppSettings(BaseModel):
    """User-facing application settings."""

    workspaceName: str = "Raj Quant OS"
    theme: ThemeMode = "dark"
    refreshIntervalSec: int = 30
    baseCurrency: str = "USD"
    timezone: str = "utc"
    apiBaseUrl: str = ""
    channels: NotificationChannels = NotificationChannels()
    notifyMachineOffline: bool = True
    notifyHighResource: bool = True
    notifyBrokerDisconnect: bool = True
    notifyStrategyCrash: bool = True
    denseTables: bool = True
    heartbeatPulse: bool = True
