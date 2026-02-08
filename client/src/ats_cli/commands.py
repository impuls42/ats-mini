"""ATS-Mini CLI commands."""

import click

from ats_sdk import RpcError

from .cli import cli, output, pass_conn

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def parse_frequency(value: str) -> int:
    """Parse frequency string to Hz.

    Accepts:
        - Pure numbers: interpreted as Hz (e.g., 100000000)
        - MHz suffix: 100MHz, 100M, 100.1MHz (megahertz)
        - kHz suffix: 7200kHz, 7200k, 7200.5kHz (kilohertz)

    Returns:
        Frequency in Hz as integer.
    """
    v = value.strip().upper()
    if v.endswith("MHZ"):
        return int(float(v[:-3]) * 1_000_000)
    if v.endswith("M"):
        return int(float(v[:-1]) * 1_000_000)
    if v.endswith("KHZ"):
        return int(float(v[:-3]) * 1_000)
    if v.endswith("K"):
        return int(float(v[:-1]) * 1_000)
    return int(v)


def _get_set(conn, getter, setter, value, label):
    """Generic get/set helper for simple value commands."""
    try:
        if value is None:
            result = conn.run(getter())
            if isinstance(result, dict):
                output(result)
            else:
                output(result, label)
        else:
            result = conn.run(setter(value))
            if isinstance(result, dict):
                output(result)
            else:
                output(result, label)
    except RpcError as e:
        raise click.ClickException(str(e))
    except ConnectionError as e:
        raise click.ClickException(str(e))


# ---------------------------------------------------------------------------
# Info commands
# ---------------------------------------------------------------------------


@cli.command()
@pass_conn
def status(conn):
    """Show current radio status (band, mode, frequency, volume)."""
    result = conn.run(conn.radio.get_status())
    output(result)


@cli.command()
@pass_conn
def settings(conn):
    """Show all device settings."""
    result = conn.run(conn.radio.get_all_settings())
    output(result)


@cli.command()
@pass_conn
def capabilities(conn):
    """Show device capabilities and firmware info."""
    result = conn.run(conn.radio.get_capabilities())
    output(result)


# ---------------------------------------------------------------------------
# Volume
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("value", required=False, type=int)
@pass_conn
def volume(conn, value):
    """Get or set volume (0-63)."""
    _get_set(conn, conn.radio.get_volume, conn.radio.set_volume, value, "volume")


# ---------------------------------------------------------------------------
# Frequency
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("value", required=False, type=str)
@pass_conn
def frequency(conn, value):
    """Get or set frequency (Hz, or with suffix: 100MHz, 7200kHz).

    Examples:
        frequency              # Get current frequency
        frequency 100100000    # Set to 100.1 MHz (raw Hz)
        frequency 100.1MHz     # Set to 100.1 MHz
        frequency 7200kHz      # Set to 7.2 MHz
        frequency 7200.5k      # Set to 7200.5 kHz (SSB precision)
    """
    try:
        if value is None:
            result = conn.run(conn.radio.get_frequency())
            output(result)
        else:
            hz = parse_frequency(value)
            result = conn.run(conn.radio.set_frequency(hz))
            output(result)
    except RpcError as e:
        raise click.ClickException(str(e))
    except ValueError as e:
        raise click.ClickException(f"Invalid frequency format: {value}")


# ---------------------------------------------------------------------------
# Band
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("value", required=False)
@pass_conn
def band(conn, value):
    """Get or set band (index number or name).

    Examples: band 3, band FM, band "SW 25m"
    """
    try:
        if value is None:
            result = conn.run(conn.radio.get_band())
            output(result)
        else:
            try:
                idx = int(value)
                result = conn.run(conn.radio.set_band(idx))
            except ValueError:
                result = conn.run(conn.radio.set_band_by_name(value))
            output(result)
    except RpcError as e:
        raise click.ClickException(str(e))


# ---------------------------------------------------------------------------
# Mode
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("value", required=False, type=int)
@pass_conn
def mode(conn, value):
    """Get or set demodulation mode."""
    _get_set(conn, conn.radio.get_mode, conn.radio.set_mode, value, "mode")


# ---------------------------------------------------------------------------
# Step
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("value", required=False, type=int)
@pass_conn
def step(conn, value):
    """Get or set tuning step."""
    _get_set(conn, conn.radio.get_step, conn.radio.set_step, value, "step")


# ---------------------------------------------------------------------------
# Bandwidth
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("value", required=False, type=int)
@pass_conn
def bandwidth(conn, value):
    """Get or set filter bandwidth."""
    _get_set(
        conn, conn.radio.get_bandwidth, conn.radio.set_bandwidth, value, "bandwidth"
    )


# ---------------------------------------------------------------------------
# AGC
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("value", required=False, type=int)
@pass_conn
def agc(conn, value):
    """Get or set AGC (Automatic Gain Control)."""
    _get_set(conn, conn.radio.get_agc, conn.radio.set_agc, value, "agc")


# ---------------------------------------------------------------------------
# Squelch
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("value", required=False, type=int)
@pass_conn
def squelch(conn, value):
    """Get or set squelch level."""
    _get_set(conn, conn.radio.get_squelch, conn.radio.set_squelch, value, "squelch")


# ---------------------------------------------------------------------------
# Softmute
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("value", required=False, type=int)
@pass_conn
def softmute(conn, value):
    """Get or set soft mute level."""
    _get_set(conn, conn.radio.get_softmute, conn.radio.set_softmute, value, "softmute")


# ---------------------------------------------------------------------------
# AVC
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("value", required=False, type=int)
@pass_conn
def avc(conn, value):
    """Get or set AVC (Automatic Volume Control)."""
    _get_set(conn, conn.radio.get_avc, conn.radio.set_avc, value, "avc")


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("value", required=False, type=int)
@pass_conn
def cal(conn, value):
    """Get or set calibration offset."""
    _get_set(conn, conn.radio.get_cal, conn.radio.set_cal, value, "cal")


# ---------------------------------------------------------------------------
# Brightness
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("value", required=False, type=int)
@pass_conn
def brightness(conn, value):
    """Get or set display brightness."""
    _get_set(
        conn, conn.radio.get_brightness, conn.radio.set_brightness, value, "brightness"
    )


# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("value", required=False, type=int)
@pass_conn
def theme(conn, value):
    """Get or set display theme."""
    _get_set(conn, conn.radio.get_theme, conn.radio.set_theme, value, "theme")


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("value", required=False, type=int)
@pass_conn
def layout(conn, value):
    """Get or set UI layout."""
    _get_set(conn, conn.radio.get_ui_layout, conn.radio.set_ui_layout, value, "layout")


# ---------------------------------------------------------------------------
# Zoom
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("value", required=False, type=click.Choice(["on", "off"]))
@pass_conn
def zoom(conn, value):
    """Get or set zoom menu (on/off)."""
    try:
        if value is None:
            result = conn.run(conn.radio.get_zoom_menu())
            output("on" if result else "off", "zoom")
        else:
            result = conn.run(conn.radio.set_zoom_menu(value == "on"))
            output("on" if result else "off", "zoom")
    except RpcError as e:
        raise click.ClickException(str(e))


# ---------------------------------------------------------------------------
# Scroll direction
# ---------------------------------------------------------------------------


@cli.command("scroll")
@click.argument("value", required=False, type=int)
@pass_conn
def scroll_direction(conn, value):
    """Get or set scroll direction."""
    _get_set(
        conn,
        conn.radio.get_scroll_direction,
        conn.radio.set_scroll_direction,
        value,
        "scroll_direction",
    )


# ---------------------------------------------------------------------------
# Sleep (group)
# ---------------------------------------------------------------------------


@cli.group()
def sleep():
    """Sleep control commands."""
    pass


@sleep.command("on")
@pass_conn
def sleep_on(conn):
    """Enable sleep mode."""
    conn.run(conn.radio.sleep_on())
    click.echo("Sleep enabled.")


@sleep.command("off")
@pass_conn
def sleep_off(conn):
    """Disable sleep mode."""
    conn.run(conn.radio.sleep_off())
    click.echo("Sleep disabled.")


@sleep.command("timeout")
@click.argument("value", required=False, type=int)
@pass_conn
def sleep_timeout(conn, value):
    """Get or set sleep timeout."""
    _get_set(
        conn,
        conn.radio.get_sleep_timeout,
        conn.radio.set_sleep_timeout,
        value,
        "sleep_timeout",
    )


@sleep.command("mode")
@click.argument("value", required=False, type=int)
@pass_conn
def sleep_mode(conn, value):
    """Get or set sleep mode."""
    _get_set(
        conn, conn.radio.get_sleep_mode, conn.radio.set_sleep_mode, value, "sleep_mode"
    )


# ---------------------------------------------------------------------------
# RDS
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("value", required=False, type=int)
@pass_conn
def rds(conn, value):
    """Get or set RDS mode."""
    _get_set(conn, conn.radio.get_rds_mode, conn.radio.set_rds_mode, value, "rds_mode")


# ---------------------------------------------------------------------------
# FM region
# ---------------------------------------------------------------------------


@cli.command("fm-region")
@click.argument("value", required=False, type=int)
@pass_conn
def fm_region(conn, value):
    """Get or set FM region."""
    _get_set(
        conn, conn.radio.get_fm_region, conn.radio.set_fm_region, value, "fm_region"
    )


# ---------------------------------------------------------------------------
# UTC offset
# ---------------------------------------------------------------------------


@cli.command("utc-offset")
@click.argument("value", required=False, type=int)
@pass_conn
def utc_offset(conn, value):
    """Get or set UTC offset."""
    _get_set(
        conn, conn.radio.get_utc_offset, conn.radio.set_utc_offset, value, "utc_offset"
    )


# ---------------------------------------------------------------------------
# Connectivity modes
# ---------------------------------------------------------------------------


@cli.command("usb-mode")
@click.argument("value", required=False, type=int)
@pass_conn
def usb_mode(conn, value):
    """Get or set USB mode."""
    _get_set(conn, conn.radio.get_usb_mode, conn.radio.set_usb_mode, value, "usb_mode")


@cli.command("ble-mode")
@click.argument("value", required=False, type=int)
@pass_conn
def ble_mode(conn, value):
    """Get or set BLE mode."""
    _get_set(conn, conn.radio.get_ble_mode, conn.radio.set_ble_mode, value, "ble_mode")


@cli.command("wifi-mode")
@click.argument("value", required=False, type=int)
@pass_conn
def wifi_mode(conn, value):
    """Get or set WiFi mode."""
    _get_set(
        conn, conn.radio.get_wifi_mode, conn.radio.set_wifi_mode, value, "wifi_mode"
    )


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------


@cli.group()
def memory():
    """Memory management commands."""
    pass


@memory.command("list")
@pass_conn
def memory_list(conn):
    """List saved memories."""
    memories = conn.run(conn.radio.memory_list())
    if not memories:
        click.echo("No memories saved.")
        return
    use_json = click.get_current_context().find_root().params.get("use_json", False)
    if use_json:
        import json

        click.echo(json.dumps(memories, indent=2, default=str))
    else:
        for mem in memories:
            if isinstance(mem, dict):
                slot = mem.get("slot", "?")
                parts = [f"{k}={v}" for k, v in mem.items() if k != "slot"]
                click.echo(f"  slot {slot}: {', '.join(parts)}")
            else:
                click.echo(f"  {mem}")
