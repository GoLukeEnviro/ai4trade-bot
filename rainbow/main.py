from __future__ import annotations

import asyncio
import logging
import sys
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from core.whimsy import create_formatter, print_whimsy_banner
from rainbow.collectors.base import BaseCollector
from rainbow.config.settings import RainbowSettings
from rainbow.distribution import api as api_module
from rainbow.distribution.metrics import (
    ACTIVE_COLLECTORS,
    COLLECTOR_CYCLE_DURATION,
    COLLECTOR_CYCLES,
    SIGNALS_COLLECTED,
    SIGNALS_SCORED,
    WEBHOOKS_DISPATCHED,
)
from rainbow.distribution.webhooks import WebhookManager
from rainbow.evaluation.llm_evaluator import LLMEvaluator
from rainbow.market_data.bitget import BitgetClient
from rainbow.processor.scorer import RainbowScorer
from rainbow.processor.store import SignalStore

log = logging.getLogger("rainbow")

_engine: RainbowEngine | None = None


class RainbowEngine:
    """Orchestriert Collectors, Scorer, Store und Background-Tasks."""

    def __init__(self, settings: RainbowSettings) -> None:
        self.settings = settings
        self.store: SignalStore | None = None
        self.scorer: RainbowScorer | None = None
        self.webhooks: WebhookManager | None = None
        self.collectors: list[BaseCollector] = []
        self._tasks: list[asyncio.Task[None]] = []
        self._shutdown_event = asyncio.Event()

    async def initialize(self) -> None:
        """Store und Scorer initialisieren, Collectors instanziieren."""
        self.store = SignalStore(self.settings.db_path)
        await self.store.start()

        self.scorer = RainbowScorer(self.settings.scorer.weights)
        self._init_evaluator()
        self._build_collectors()

        self.webhooks = WebhookManager()
        api_module._webhook_manager = self.webhooks

        ACTIVE_COLLECTORS.set(len(self.collectors))

    def _init_evaluator(self) -> None:
        """KI-Evaluator initialisieren wenn konfiguriert."""
        evaluation_cfg = getattr(self.settings, "evaluation", None)
        if not evaluation_cfg or not getattr(evaluation_cfg, "enabled", False):
            log.info("KI-Evaluation deaktiviert")
            return
        try:
            evaluator = LLMEvaluator(
                model=getattr(evaluation_cfg, "model", "deepseek-reasoner"),
                temperature=getattr(evaluation_cfg, "temperature", 0.1),
                timeout_seconds=getattr(evaluation_cfg, "timeout_seconds", 5.0),
                threshold=getattr(evaluation_cfg, "threshold", 0.5),
                cache_ttl_seconds=getattr(evaluation_cfg, "cache_ttl_seconds", 300),
            )
            self.scorer._evaluator = evaluator
            self.scorer._evaluation_threshold = getattr(evaluation_cfg, "threshold", 0.5)
            log.info("KI-Evaluator initialisiert (model=%s)", evaluator._model)
        except Exception as exc:
            log.warning("KI-Evaluator konnte nicht initialisiert werden: %s", exc)

        log.info(
            "RainbowEngine initialisiert: %d Collector(s)",
            len(self.collectors),
        )

    def _build_collectors(self) -> None:
        """Collectors basierend auf Settings instanziieren."""
        from rainbow.collectors.news_collector import NewsCollector
        from rainbow.collectors.reddit_collector import RedditCollector
        from rainbow.collectors.ta_collector import TACollector
        from rainbow.collectors.twitter_collector import TwitterCollector

        for name, cfg in self.settings.collectors.items():
            if not cfg.enabled:
                log.info("Collector '%s' deaktiviert, uebersprungen", name)
                continue

            try:
                collector: BaseCollector
                if name == "ta":
                    provider = BitgetClient(
                        base_url=self.settings.market_data.bitget_base_url,
                    )
                    timeframes = cfg.params.get("timeframes", ["1h"])
                    collector = TACollector(
                        provider=provider,
                        assets=cfg.assets,
                        timeframes=timeframes,
                    )
                elif name == "twitter":
                    bearer_token = self.settings.twitter_bearer_token
                    if not bearer_token:
                        log.info("Collector 'twitter': RAINBOW_TWITTER_BEARER_TOKEN nicht gesetzt, deaktiviert")
                        continue
                    collector = TwitterCollector(
                        bearer_token=bearer_token,
                        assets=cfg.assets,
                        max_results=cfg.params.get("max_results", 25),
                    )
                elif name == "reddit":
                    collector = RedditCollector(
                        assets=cfg.assets,
                        subreddits=cfg.params.get("subreddits"),
                        posts_per_subreddit=cfg.params.get("posts_per_subreddit", 15),
                    )
                elif name == "news":
                    collector = NewsCollector(
                        assets=cfg.assets,
                        cryptocompare_base=self.settings.market_data.coingecko_base_url.replace(
                            "coingecko", "cryptocompare"
                        ),
                        max_articles=cfg.params.get("max_articles", 20),
                    )
                else:
                    log.warning("Unbekannter Collector-Typ: '%s'", name)
                    continue

                self.collectors.append(collector)
                api_module._collector_status[name] = "running"
                log.info("Collector '%s' registriert (Interval: %ds)", name, cfg.interval_seconds)
            except Exception as exc:
                log.error("Collector '%s' konnte nicht erstellt werden: %s", name, exc)

    async def start_background_tasks(self) -> None:
        """Background-Tasks fuer alle aktiven Collector starten."""
        for collector in self.collectors:
            cfg = self.settings.collectors.get(collector.name)
            if cfg is None:
                continue

            task = asyncio.create_task(
                _run_collector_loop(
                    collector=collector,
                    scorer=self.scorer,
                    store=self.store,
                    interval_seconds=cfg.interval_seconds,
                    shutdown_event=self._shutdown_event,
                    webhooks=self.webhooks,
                ),
                name=f"collector-{collector.name}",
            )
            self._tasks.append(task)

    async def shutdown(self) -> None:
        """Graceful Shutdown aller Background-Tasks und Ressourcen."""
        log.info("RainbowEngine Shutdown eingeleitet")
        self._shutdown_event.set()

        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        if self.store is not None:
            await self.store.stop()

        if self.webhooks is not None:
            await self.webhooks.close()

        ACTIVE_COLLECTORS.set(0)

        for name in list(api_module._collector_status):
            api_module._collector_status[name] = "stopped"

        log.info("RainbowEngine Shutdown abgeschlossen")


async def _run_collector_loop(
    collector: BaseCollector,
    scorer: RainbowScorer,
    store: SignalStore,
    interval_seconds: int,
    shutdown_event: asyncio.Event,
    webhooks: WebhookManager | None = None,
) -> None:
    """Endlosschleife: sammeln, bewerten, speichern, webhooks dispatchen. Graceful degradation bei Fehlern."""
    log.info("Collector-Loop gestartet: '%s' (Interval: %ds)", collector.name, interval_seconds)

    while not shutdown_event.is_set():
        try:
            with COLLECTOR_CYCLE_DURATION.labels(collector=collector.name).time():
                signals = await collector.collect()
            if signals:
                for sig in signals:
                    SIGNALS_COLLECTED.labels(collector=collector.name, asset=sig.asset).inc()
                scored = await scorer.score_and_evaluate(signals)
                for sig in scored:
                    SIGNALS_SCORED.labels(asset=sig.asset).inc()
                    await store.save(sig)
                if webhooks:
                    for sig in scored:
                        try:
                            await webhooks.dispatch(sig)
                            WEBHOOKS_DISPATCHED.labels(status="success").inc()
                        except Exception:
                            WEBHOOKS_DISPATCHED.labels(status="failure").inc()
                log.info(
                    "Collector '%s': %d Signal(e) verarbeitet",
                    collector.name,
                    len(scored),
                )
            COLLECTOR_CYCLES.labels(collector=collector.name, status="success").inc()
        except Exception as exc:
            COLLECTOR_CYCLES.labels(collector=collector.name, status="error").inc()
            log.error(
                "Collector '%s' Fehler: %s",
                collector.name,
                exc,
                exc_info=True,
            )
            api_module._collector_status[collector.name] = "error"

        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=interval_seconds)
        except asyncio.TimeoutError:
            api_module._collector_status[collector.name] = "running"
        except asyncio.CancelledError:
            break


def setup_logging(level: str = "INFO", fmt: str = "text") -> None:
    """Logging fuer Rainbow konfigurieren."""
    root = logging.getLogger("rainbow")
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    if root.handlers:
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(root.level)
    handler.setFormatter(create_formatter(fmt))

    root.addHandler(handler)


def create_engine(settings: RainbowSettings) -> FastAPI:
    """Engine erstellen und konfigurierte FastAPI-App zurueckgeben."""
    engine = RainbowEngine(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await engine.initialize()
        api_module._store = engine.store
        api_module._settings = engine.settings
        api_module._engine = engine
        await engine.start_background_tasks()
        log.info("Rainbow Intelligence Engine gestartet")
        yield
        await engine.shutdown()

    app = api_module.create_app(
        store=None,
        settings=settings,
        engine=engine,
    )
    app.router.lifespan_context = lifespan

    return app


def create_app() -> FastAPI:
    """Factory function for uvicorn --factory mode (no arguments)."""
    from pathlib import Path

    config_path = Path("rainbow/config.yaml")
    settings = RainbowSettings.from_yaml(config_path)
    return create_engine(settings)


def main() -> None:
    """Entry point: Settings laden, Logging konfigurieren, Server starten."""
    from pathlib import Path

    config_path = Path("rainbow/config.yaml")
    settings = RainbowSettings.from_yaml(config_path)

    print_whimsy_banner("Rainbow Intelligence Engine", "Signal-Storytelling in Farbe")
    setup_logging(level=settings.log_level, fmt=settings.log_format)

    app = create_engine(settings)

    uvicorn.run(
        app,
        host=settings.api.host,
        port=settings.api.port,
        log_config=None,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
