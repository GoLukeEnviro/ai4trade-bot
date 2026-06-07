import config
from exchanges.base import ExchangeClient
from exchanges.bitget_rest import BitgetRestClient


def create_exchange(provider: str = None) -> ExchangeClient:
    name = (provider or config.EXCHANGE_PROVIDER or "bitget").lower()
    if name == "bitget":
        return BitgetRestClient()
    raise ValueError(f"Unbekannter Exchange-Provider: {name}")
