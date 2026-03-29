"""
langsight monitor — continuous background monitoring with alerting.

Polls all configured MCP servers on a configurable interval, evaluates
results through the alert engine, and fires Slack/webhook notifications
on state transitions.

Runs until Ctrl-C.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import click
import structlog
from rich.console import Console
from rich.table import Table

from langsight.alerts import slack as slack_module
from langsight.alerts import webhook as webhook_module
from langsight.alerts.engine import AlertEngine
from langsight.cli._storage import try_open_storage
from langsight.config import LangSightConfig, Settings, load_config
from langsight.health.checker import HealthChecker
from langsight.models import HealthCheckResult, ServerStatus

logger = structlog.get_logger()
console = Console()

_STATUS_STYLE = {
    ServerStatus.UP: "[green]✓ up[/green]",
    ServerStatus.DEGRADED: "[yellow]⚠ degraded[/yellow]",
    ServerStatus.DOWN: "[red]✗ down[/red]",
    ServerStatus.STALE: "[dim]~ stale[/dim]",
    ServerStatus.UNKNOWN: "[dim]? unknown[/dim]",
}

DEFAULT_INTERVAL = 30


@click.command("monitor")
@click.option(
    "--config",
    "config_path",
    type=click.Path(path_type=Path),
    default=None,
    help="Path to .langsight.yaml (auto-discovered if not set).",
)
@click.option(
    "--interval",
    "-i",
    type=int,
    default=None,
    help=f"Health check interval in seconds (default: {DEFAULT_INTERVAL}).",
)
@click.option(
    "--once",
    is_flag=True,
    help="Run a single check cycle and exit (useful for cron/CI).",
)
def monitor(
    config_path: Path | None,
    interval: int | None,
    once: bool,
) -> None:
    """Continuously monitor MCP servers and alert on state changes.

    Polls servers on a configurable interval, fires Slack/webhook alerts
    on DOWN, DEGRADED, and recovery transitions.
    """
    config = load_config(config_path)
    settings = Settings()

    if not config.servers:
        console.print("[yellow]No MCP servers configured.[/yellow]")
        console.print("Run [bold]langsight init[/bold] to get started.")
        sys.exit(1)

    check_interval = interval or settings.health_check_interval_seconds or DEFAULT_INTERVAL

    try:
        asyncio.run(_monitor_loop(config, settings, check_interval, once))
    except KeyboardInterrupt:
        console.print("\n[dim]Monitor stopped.[/dim]")


async def _monitor_loop(
    config: LangSightConfig,
    settings: Settings,
    interval: int,
    once: bool,
) -> None:
    alert_engine = AlertEngine(
        consecutive_failures_threshold=config.alerts.consecutive_failures,
        latency_spike_multiplier=config.alerts.latency_spike_multiplier,
    )

    storage = await try_open_storage(config)
    try:
        checker = HealthChecker(storage=storage, project_id=config.project_id)

        # Seed alert baselines from recent health history (avoids false alarms after restart)
        if storage:
            for server in config.servers:
                history = await storage.get_health_history(server.name, limit=10)
                if history:
                    alert_engine.seed_from_history(list(reversed(history)))

        cycle = 0

        while True:
            cycle += 1
            logger.info("monitor.cycle_start", cycle=cycle, servers=len(config.servers))

            results = await checker.check_many(config.servers)
            alerts = alert_engine.evaluate_many(results)

            _display_cycle(results, cycle, interval)

            if alerts:
                await _deliver_alerts(alerts, config, settings, storage)

            if once:
                break

            await asyncio.sleep(interval)
    finally:
        if storage:
            await storage.close()


async def _deliver_alerts(alerts, config, settings: Settings, storage=None) -> None:  # type: ignore[no-untyped-def]
    """Deliver fired alerts via configured channels.

    Webhook URL priority (mirrors the API's _load_alert_config):
      1. DB value saved via the dashboard Settings → Notifications UI
      2. .langsight.yaml alerts.slack_webhook
      3. LANGSIGHT_SLACK_WEBHOOK env var
    """
    # 1. DB — set via dashboard UI (POST /api/alerts/config)
    slack_url: str | None = None
    if storage and hasattr(storage, "get_alert_config"):
        try:
            db_cfg = await storage.get_alert_config()
            slack_url = (db_cfg or {}).get("slack_webhook") or None
        except Exception:  # noqa: BLE001
            pass  # fail-open — don't block alerting if DB is unreachable

    # 2. YAML
    if not slack_url:
        slack_url = config.alerts.slack_webhook or None

    # 3. Env var (settings.slack_webhook == LANGSIGHT_SLACK_WEBHOOK)
    if not slack_url:
        slack_url = settings.slack_webhook or None

    webhook_url = None  # future: config.alerts.webhook_url

    for alert in alerts:
        console.print(f"[bold]Alert:[/bold] {alert.severity.value.upper()} — {alert.title}")

    if slack_url:
        sent = await slack_module.send_alerts(slack_url, alerts)
        logger.info("monitor.slack_sent", count=sent, total=len(alerts))

    if webhook_url:
        sent = await webhook_module.send_alerts(webhook_url, alerts)
        logger.info("monitor.webhook_sent", count=sent, total=len(alerts))


def _display_cycle(
    results: list[HealthCheckResult],
    cycle: int,
    interval: int,
) -> None:
    table = Table(
        title=f"[dim]Cycle #{cycle} — next in {interval}s[/dim]",
        show_header=True,
        header_style="bold",
        border_style="dim",
    )
    table.add_column("Server", style="bold", min_width=18)
    table.add_column("Status", min_width=14)
    table.add_column("Latency", justify="right", min_width=9)
    table.add_column("Tools", justify="right", min_width=6)
    table.add_column("Info", style="dim")

    for r in results:
        info = r.error or ""
        table.add_row(
            r.server_name,
            _STATUS_STYLE.get(r.status, r.status.value),
            f"{r.latency_ms:.0f}ms" if r.latency_ms else "—",
            str(r.tools_count) if r.tools_count else "—",
            info[:60],
        )

    console.print(table)
