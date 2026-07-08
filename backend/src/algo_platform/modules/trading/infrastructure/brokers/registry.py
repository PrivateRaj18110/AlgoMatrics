from collections.abc import Callable

from algo_platform.modules.trading.application.broker_port import BrokerExecutionPort

BrokerFactory = Callable[[], BrokerExecutionPort]


class BrokerAdapterRegistry:
    def __init__(self) -> None:
        self._factories: dict[str, BrokerFactory] = {}

    def register(self, broker_type: str, factory: BrokerFactory) -> None:
        if broker_type in self._factories:
            raise ValueError(f"adapter already registered: {broker_type}")
        self._factories[broker_type] = factory

    def create(self, broker_type: str) -> BrokerExecutionPort:
        try:
            return self._factories[broker_type]()
        except KeyError as error:
            raise ValueError(f"unsupported broker: {broker_type}") from error
