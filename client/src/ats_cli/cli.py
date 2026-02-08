"""ATS-Mini CLI — click + click-repl interface for the ATS-Mini SDK."""

import asyncio
import json as _json
import shlex
import sys

import click
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import InMemoryHistory

from ats_sdk import AsyncSerialRpc, AsyncWebSocketRpc, AsyncBleRpc, Radio, RpcError


class Connection:
    """Manages a lazy, persistent connection to the radio."""

    def __init__(self, port=None, ws=None, ble=None):
        self.port = port
        self.ws = ws
        self.ble = ble
        self._transport = None
        self._radio = None
        self._loop = None

    def _get_loop(self):
        if self._loop is None or self._loop.is_closed():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
        return self._loop

    @property
    def radio(self) -> Radio:
        if self._radio is None:
            self._connect()
            assert self._radio is not None
        return self._radio

    def _connect(self):
        loop = self._get_loop()
        if self.ws:
            t = AsyncWebSocketRpc(self.ws)
        elif self.ble is not None:
            name = self.ble if self.ble else "ATS-Mini"
            t = AsyncBleRpc(name)
        elif self.port:
            t = AsyncSerialRpc(self.port)
        else:
            raise click.UsageError(
                "No transport specified. Use --port, --ws, or --ble "
                "(or set ATSMINI_PORT / ATSMINI_WS_URL / ATSMINI_BLE)."
            )
        loop.run_until_complete(t.connect())
        self._transport = t
        self._radio = Radio(t)

    def run(self, coro):
        """Run an async coroutine synchronously."""
        return self._get_loop().run_until_complete(coro)

    def close(self):
        if self._transport:
            try:
                self._get_loop().run_until_complete(self._transport.close())
            except Exception:
                pass
            self._transport = None
            self._radio = None
        if self._loop and not self._loop.is_closed():
            self._loop.close()
            self._loop = None


def output(data, label=None):
    """Print result in human-readable or JSON format."""
    use_json = click.get_current_context().find_root().params.get("use_json", False)
    if use_json:
        click.echo(_json.dumps(data, indent=2, default=str))
    elif isinstance(data, dict):
        for k, v in data.items():
            click.echo(f"{k}: {v}")
    elif label:
        click.echo(f"{label}: {data}")
    else:
        click.echo(data)


pass_conn = click.make_pass_decorator(Connection)


@click.group(invoke_without_command=True)
@click.option(
    "--port", "-p", envvar="ATSMINI_PORT", help="Serial port (e.g. /dev/ttyUSB0)"
)
@click.option(
    "--ws", envvar="ATSMINI_WS_URL", help="WebSocket URL (e.g. ws://atsmini.local/rpc)"
)
@click.option(
    "--ble",
    envvar="ATSMINI_BLE",
    is_flag=False,
    flag_value="ATS-Mini",
    default=None,
    help="BLE device name (default: ATS-Mini)",
)
@click.option("--json", "use_json", is_flag=True, help="Output as JSON")
@click.version_option(package_name="ats-cli")
@click.pass_context
def cli(ctx, port, ws, ble, use_json):
    """ATS-Mini radio control CLI.

    Run with a command for one-shot operation, or without a command to enter
    interactive REPL mode.
    """
    ctx.ensure_object(Connection)
    ctx.obj = Connection(port=port, ws=ws, ble=ble)

    if ctx.invoked_subcommand is None:
        click.echo("ATS-Mini CLI (type 'help' for commands, 'exit' to quit)")
        _repl(ctx)
        ctx.obj.close()


def _repl(group_ctx):
    """Interactive REPL using prompt_toolkit."""
    group = group_ctx.command
    commands = list(group.commands)
    completer = WordCompleter(commands + ["help", "exit", "quit"])
    session = PromptSession(history=InMemoryHistory(), completer=completer)

    while True:
        try:
            line = session.prompt("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not line:
            continue
        if line in ("exit", "quit"):
            break
        if line == "help":
            click.echo(group_ctx.get_help())
            continue

        try:
            args = shlex.split(line)
        except ValueError as e:
            click.echo(f"Parse error: {e}")
            continue

        try:
            cmd_name, cmd, args = group.resolve_command(group_ctx, args)
            if cmd is None:
                click.echo(f"Unknown command: {args[0] if args else line}")
                continue
            sub_ctx = cmd.make_context(cmd_name, list(args), parent=group_ctx)
            with sub_ctx:
                cmd.invoke(sub_ctx)
        except click.UsageError as e:
            click.echo(f"Error: {e}")
        except click.ClickException as e:
            e.show()
        except RpcError as e:
            click.echo(f"RPC error: {e}", err=True)
        except ConnectionError as e:
            click.echo(f"Connection error: {e}", err=True)
        except SystemExit:
            pass


def main():
    """Entry point."""
    try:
        cli(standalone_mode=False)
    except click.exceptions.Abort:
        pass
    except RpcError as e:
        click.echo(f"RPC error: {e}", err=True)
        sys.exit(1)
    except ConnectionError as e:
        click.echo(f"Connection error: {e}", err=True)
        sys.exit(1)
    except click.UsageError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(2)


# Import commands to register them on the cli group
from . import commands  # noqa: E402, F401
