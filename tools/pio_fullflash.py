import os
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from SCons.Script import Import as _SConsImport  # type: ignore[reportMissingImports]
else:
    _SConsImport = None


def _scons_import(name: str) -> None:
    if _SConsImport is not None:
        _SConsImport(name)
        return
    try:
        Import(name)  # type: ignore[name-defined]
    except Exception:
        return


_scons_import("env")
env: Any = globals().get("env")


def _load_dotenv() -> None:
    try:
        project_dir = env.subst("$PROJECT_DIR")
    except Exception:
        project_dir = os.getcwd()
    dotenv_path = os.path.join(project_dir, ".env")
    if not os.path.exists(dotenv_path):
        return
    try:
        with open(dotenv_path, "r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except Exception:
        return


_load_dotenv()

def _quote(arg: str) -> str:
    if any(ch in arg for ch in (" ", "(", ")")):
        return f'"{arg}"'
    return arg


def _flash_freq(value) -> str:
    if value is None:
        return "80m"
    if isinstance(value, int):
        hz = value
    else:
        raw = str(value).lower().replace("l", "").strip()
        if raw.endswith("m"):
            return raw
        if raw.isdigit():
            hz = int(raw)
        else:
            return "80m"
    if hz % 1_000_000 == 0:
        return f"{hz // 1_000_000}m"
    return "80m"


def _get_esptool_path():
    platform = env.PioPlatform()
    tool_dir = platform.get_package_dir("tool-esptoolpy")
    if tool_dir:
        return os.path.join(tool_dir, "esptool.py")
    return "esptool.py"


def _get_boot_app0_path():
    boot_app0 = env.get("BOOT_APP0_BIN")
    if boot_app0 and os.path.exists(boot_app0):
        return boot_app0
    framework_dir = env.PioPlatform().get_package_dir("framework-arduinoespressif32")
    if framework_dir:
        candidate = os.path.join(framework_dir, "tools", "partitions", "boot_app0.bin")
        if os.path.exists(candidate):
            return candidate
    return "boot_app0.bin"


def _get_flash_size(board):
    return (
        board.get("upload.flash_size")
        or board.get("build.flash_size")
        or env.GetProjectOption("board_build.flash_size")
        or "8MB"
    )


def _get_prog_offset(board):
    offset = env.get("PROG_OFFSET")
    if offset:
        return offset
    try:
        return board.get("upload.offset_address")
    except KeyError:
        return "0x10000"


def _merged_path():
    return env.subst("$BUILD_DIR/firmware.merged.bin")


def _run_esptool(args):
    cmd = " ".join(_quote(str(arg)) for arg in args)
    return env.Execute(cmd)


def _get_upload_speed():
    override = os.getenv("ATSMINI_UPLOAD_SPEED") or os.getenv("UPLOAD_SPEED")
    if override:
        return str(override)
    try:
        return env.subst("$UPLOAD_SPEED")
    except Exception:
        return "115200"


def _get_upload_port() -> str:
    override = os.getenv("ATSMINI_PORT") or os.getenv("ESPTOOL_PORT")
    if override:
        return str(override)
    try:
        port = env.subst("$UPLOAD_PORT")
        if port:
            return port
    except Exception:
        pass
    try:
        autodetected = env.AutodetectUploadPort()
    except Exception:
        autodetected = None
    if isinstance(autodetected, (list, tuple)):
        return autodetected[0] if autodetected else ""
    return autodetected or ""


def _use_no_stub() -> bool:
    value = os.getenv("ATSMINI_ESPTOOL_NO_STUB") or os.getenv("ESPTOOL_NO_STUB")
    if value is None:
        return True
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _use_erase_all(no_stub: bool) -> bool:
    value = os.getenv("ATSMINI_ESPTOOL_ERASE_ALL") or os.getenv("ESPTOOL_ERASE_ALL")
    if value is None:
        return not no_stub
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def build_merged(source, target, env):
    board = env.BoardConfig()
    build_dir = env.subst("$BUILD_DIR")
    esptool = _get_esptool_path()
    merged = _merged_path()

    flash_mode = board.get("build.flash_mode", "qio")
    flash_freq = _flash_freq(board.get("build.f_flash"))
    flash_size = _get_flash_size(board)

    bootloader = os.path.join(build_dir, "bootloader.bin")
    partitions = os.path.join(build_dir, "partitions.bin")
    boot_app0 = _get_boot_app0_path()
    prog_bin = env.subst("$BUILD_DIR/${PROGNAME}.bin")
    prog_offset = _get_prog_offset(board)

    args = [
        env.subst("$PYTHONEXE"),
        esptool,
        "--chip",
        board.get("build.mcu", "esp32s3"),
        "merge_bin",
        "-o",
        merged,
        "--flash_mode",
        flash_mode,
        "--flash_size",
        flash_size,
        "--flash_freq",
        flash_freq,
        "0x0",
        bootloader,
        "0x8000",
        partitions,
        "0xe000",
        boot_app0,
        prog_offset,
        prog_bin,
    ]
    return _run_esptool(args)


def upload_fullflash(source, target, env):
    board = env.BoardConfig()
    esptool = _get_esptool_path()
    merged = _merged_path()
    upload_port = _get_upload_port()
    upload_speed = _get_upload_speed()
    no_stub = _use_no_stub()
    erase_all = _use_erase_all(no_stub)

    if not upload_port:
        message = (
            "Upload port not set. Set ATSMINI_PORT or ESPTOOL_PORT, or configure upload_port in platformio.ini."
        )
        try:
            env.Exit(1)
        finally:
            print(message)

    args = [
        env.subst("$PYTHONEXE"),
        esptool,
        "--chip",
        board.get("build.mcu", "esp32s3"),
    ]
    if no_stub:
        args.append("--no-stub")
    args += [
        "--port",
        upload_port,
        "--baud",
        upload_speed,
        "--before",
        "default_reset",
        "--after",
        "hard_reset",
        "write_flash",
    ]
    if erase_all:
        args.append("--erase-all")
    args += [
        "--flash_mode",
        "keep",
        "--flash_freq",
        "keep",
        "--flash_size",
        "keep",
        "0x0",
        merged,
    ]
    return _run_esptool(args)


env.AddTarget(
    "mergedbin",
    env.Alias("buildprog"),
    build_merged,
    "Build merged firmware binary (single file at 0x0)",
)

env.AddTarget(
    "fullflash",
    env.Alias("buildprog"),
    [build_merged, upload_fullflash],
    "Build and upload full flash image (erase + write merged bin)",
)
