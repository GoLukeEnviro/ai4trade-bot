import logging
import time

log = logging.getLogger(__name__)


class HealthCheck:
    def __init__(self, repository=None, exchange=None, ai4trade_client=None):
        self._repository = repository
        self._exchange = exchange
        self._ai4trade_client = ai4trade_client
        self._start_time = time.monotonic()

    def check(self) -> dict:
        """
        Full health check. Returns dict with status and component results.
        Status is "healthy" only if ALL checks pass.
        """
        results = {
            "status": "healthy",
            "uptime_seconds": round(time.monotonic() - self._start_time, 1),
            "components": {},
        }

        results["components"]["database"] = self._check_db()
        results["components"]["exchange"] = self._check_exchange()
        results["components"]["ai4trade_api"] = self._check_ai4trade()

        if any(c.get("status") != "healthy" for c in results["components"].values()):
            results["status"] = "unhealthy"

        return results

    def _check_db(self) -> dict:
        if self._repository is None:
            return {"status": "healthy", "note": "no repository configured"}
        try:
            self._repository.get_state("_health_check", default="ok")
            return {"status": "healthy"}
        except Exception as e:
            log.warning(f"DB Health-Check fehlgeschlagen: {e}")
            return {"status": "unhealthy", "error": str(e)}

    def _check_exchange(self) -> dict:
        if self._exchange is None:
            return {"status": "healthy", "note": "no exchange configured"}
        try:
            self._exchange.get_price("BTCUSDT")
            return {"status": "healthy"}
        except Exception as e:
            log.warning(f"Exchange Health-Check fehlgeschlagen: {e}")
            return {"status": "unhealthy", "error": str(e)}

    def _check_ai4trade(self) -> dict:
        if self._ai4trade_client is None:
            return {"status": "healthy", "note": "no client configured"}
        try:
            self._ai4trade_client.get_me()
            return {"status": "healthy"}
        except Exception as e:
            log.warning(f"AI4Trade Health-Check fehlgeschlagen: {e}")
            return {"status": "unhealthy", "error": str(e)}
