import time
from unittest.mock import MagicMock

from core.health import HealthCheck


class TestHealthCheck:
    def test_all_healthy_with_no_deps(self):
        hc = HealthCheck()
        result = hc.check()
        assert result["status"] == "healthy"
        assert result["uptime_seconds"] >= 0
        assert all(c["status"] == "healthy" for c in result["components"].values())

    def test_db_healthy(self):
        repo = MagicMock()
        repo.get_state.return_value = "ok"
        hc = HealthCheck(repository=repo)
        result = hc.check()
        assert result["components"]["database"]["status"] == "healthy"
        repo.get_state.assert_called_once_with("_health_check", default="ok")

    def test_db_unhealthy(self):
        repo = MagicMock()
        repo.get_state.side_effect = Exception("connection lost")
        hc = HealthCheck(repository=repo)
        result = hc.check()
        assert result["components"]["database"]["status"] == "unhealthy"
        assert "connection lost" in result["components"]["database"]["error"]

    def test_exchange_healthy(self):
        exchange = MagicMock()
        exchange.get_price.return_value = 42000.0
        hc = HealthCheck(exchange=exchange)
        result = hc.check()
        assert result["components"]["exchange"]["status"] == "healthy"
        exchange.get_price.assert_called_once_with("BTCUSDT")

    def test_exchange_unhealthy(self):
        exchange = MagicMock()
        exchange.get_price.side_effect = Exception("timeout")
        hc = HealthCheck(exchange=exchange)
        result = hc.check()
        assert result["components"]["exchange"]["status"] == "unhealthy"
        assert "timeout" in result["components"]["exchange"]["error"]

    def test_ai4trade_healthy(self):
        client = MagicMock()
        client.get_me.return_value = {"id": "agent-1"}
        hc = HealthCheck(ai4trade_client=client)
        result = hc.check()
        assert result["components"]["ai4trade_api"]["status"] == "healthy"
        client.get_me.assert_called_once()

    def test_ai4trade_unhealthy(self):
        client = MagicMock()
        client.get_me.side_effect = Exception("token expired")
        hc = HealthCheck(ai4trade_client=client)
        result = hc.check()
        assert result["components"]["ai4trade_api"]["status"] == "unhealthy"
        assert "token expired" in result["components"]["ai4trade_api"]["error"]

    def test_uptime_increases(self):
        hc = HealthCheck()
        t1 = hc.check()["uptime_seconds"]
        time.sleep(0.1)
        t2 = hc.check()["uptime_seconds"]
        assert t2 >= t1

    def test_one_unhealthy_makes_overall_unhealthy(self):
        repo = MagicMock()
        repo.get_state.side_effect = Exception("db down")
        exchange = MagicMock()
        exchange.get_price.return_value = 42000.0
        client = MagicMock()
        client.get_me.return_value = {"id": "agent-1"}
        hc = HealthCheck(repository=repo, exchange=exchange, ai4trade_client=client)
        result = hc.check()
        assert result["status"] == "unhealthy"
        assert result["components"]["database"]["status"] == "unhealthy"
        assert result["components"]["exchange"]["status"] == "healthy"
        assert result["components"]["ai4trade_api"]["status"] == "healthy"
