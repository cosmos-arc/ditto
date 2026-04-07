"""CLI ingest 命令组."""

from __future__ import annotations

import typer

from ditto_interfaces.cli.commands.ingest.capital import app as capital_app
from ditto_interfaces.cli.commands.ingest.fundamental import app as fundamental_app
from ditto_interfaces.cli.commands.ingest.macro import app as macro_app
from ditto_interfaces.cli.commands.ingest.market import app as market_app
from ditto_interfaces.cli.commands.ingest.metadata import app as metadata_app

app = typer.Typer(help="摄取数据")

app.add_typer(metadata_app, name="metadata")
app.add_typer(market_app, name="market")
app.add_typer(fundamental_app, name="fundamental")
app.add_typer(capital_app, name="capital")
app.add_typer(macro_app, name="macro")

__all__ = ["app"]
