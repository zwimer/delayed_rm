from collections.abc import Callable
from collections import defaultdict
from tempfile import gettempdir
from datetime import datetime
from pathlib import Path
from os import environ
import subprocess
import argparse
import tempfile
import shutil
import math
import time
import sys

# Constants
__version__ = "3.0.1"
_UNSAFE_FLAG = "unsafe-rmtree"
log_f: Path = Path.home().resolve() / ".delayed_rm.log"
tmp_d: Path = Path(gettempdir()).resolve() / ".delayed_rm"

# Classes


class RMError(Exception):
    """
    A custom class meant to be raised for 'expected' errors
    Raising this should lead to the cli program exiting
    """


class _Secret:
    """
    Contains a string needed to activate the secret CLI
    Users should *not* use this, it is an internal class!
    """

    key: str = "DELAYED_RM_SECRET_CLI"
    value: str = "--:://'cL5r0!L4hmWmonW7k^RZM*4nq7mR&yfF"


#
# Functions
#


def _size(p: Path) -> str:
    """Get file size as a human-readable string; follows symlinks"""
    s = p.stat().st_size
    lg = int(math.log(s, 1000))
    si = " KMGT"[lg].replace(" ", "")
    return f"{round(s/(1000**lg))} {si}B"


def _efmt(e: Exception) -> str:
    """Format e as a printable error string"""
    cause: BaseException = e.__cause__ if isinstance(e, RMError) and e.__cause__ is not None else e
    name = "Error" if isinstance(cause, RMError) else cause.__class__.__name__
    if not isinstance(e, shutil.Error):
        return f"{name}: {str(e)}"
    try:  # This is almost certainly from copytree it's the only thing that can raise this?
        body = "\n".join(str(i[2]) for i in e.args[0])  # str is just in case
    except IndexError:  # Just in case, but shouldn't be possible
        body = str(e)
    return f"{name}: {body}"


def _print_stderr(x) -> None:
    """Print x to stderr"""
    print(x, file=sys.stderr, flush=True)


def _print_exc(e: Exception) -> None:
    """Print an error to stderr"""
    _print_stderr(_efmt(e))


def _mkdir(ret: Path) -> Path:
    """Make base/name and set permissions to 700"""
    ret.mkdir(mode=0o700)
    return ret


def _prep(paths: list[Path], rf: bool) -> list[Path]:
    """
    Normalize paths, error check, and prep temp items
    :return: A normalized list of paths
    """
    # Normalize paths and error checking
    try:
        paths = [i.parent.resolve(strict=True) / i.name for i in paths]
        if len(paths) != len({i.stat(follow_symlinks=False).st_ino for i in paths}):
            raise RMError("duplicate or hardlinked items passed")
    except (FileNotFoundError, RuntimeError) as e:
        raise RMError(e) from e
    for i in paths:
        if not rf and i.is_dir() and not i.is_symlink():
            raise RMError(f"{i} is a directory. -rf required!")
        if tmp_d == i:
            raise RMError(f"Will not delete {tmp_d}")
        if tmp_d in i.parents:
            raise RMError(f"Will not delete items within {tmp_d}")
    # Prep temp items
    log_f.touch()
    if log_f.is_symlink() or not log_f.is_file():
        raise RMError(f"{log_f} is not a file.")
    try:
        tmp_d.mkdir(exist_ok=True)
    except (OSError, FileExistsError) as e:
        raise RMError(f"Could not create directory and set permissions on {tmp_d}") from e
    return paths


def _rmtree(d: Path) -> str:
    """rmtree that ignores errors and returns them as a string"""
    err = []
    shutil.rmtree(d, onexc=lambda *x: err.append(x[2]))
    return "\n".join(_efmt(i) for i in err)


def safety_check(unsafe_ok: bool) -> None:
    """Check if this program is safe to run; raise if not or warn if unsafe_ok is True"""
    if getattr(shutil.rmtree, "avoids_symlink_attacks", False):
        return
    if not unsafe_ok:
        raise RuntimeError(
            "This program cannot safely be run.\n"
            "  This platform does not support fd-based dir access functions\n"
            "  This makes rmtree vulnerable to TOCTOU attacks.\n"
            f"  Pass --{_UNSAFE_FLAG} to bypass this"
        )
    _print_stderr("WARNING: Bypassing the rmtree safety check is STRONGLY discouraged")


def delayed_rm(paths: list[Path], delay: int, rf: bool, unsafe: bool = False) -> bool:
    """
    Move paths to a temporary directory, delete them after delay seconds
    Log's this action to the log
    If rf, acts like rm -rf
    May raise an RMError if something goes wrong
    If unsafe is False and rmtree cannot safely be used, an error will be raised
    :returns: True on success, else False
    """
    if not paths:
        return True
    safety_check(unsafe)
    if not tmp_d.parent.exists():
        raise RuntimeError("Temp dir enclosing directory does not exist")
    if not log_f.parent.exists():
        raise RuntimeError("Log file enclosing directory does not exist")
    # Prep
    paths = _prep(paths, rf)
    base = Path(tempfile.mkdtemp(dir=tmp_d))
    base.chmod(0o700)
    # Init data structures
    success: list[Path] = []
    failed: list[Path] = []
    out_dirs: set[Path] = {_mkdir(base / "0")}
    where: dict[str, set[Path]] = defaultdict(set)
    full_where: dict[Path, Path] = {}
    # Delete files
    ctrlc = False
    any_edited = False
    try:
        for p in paths:
            edited = False
            # Select the first output directory that doesn't have something named p.name in it
            if len(out_dirs) != len(where[p.name]):
                out_d: Path = next(iter(out_dirs - where[p.name]))
            else:
                out_d = _mkdir(base / str(len(out_dirs)))
                out_dirs.add(out_d)
            # Move file into the temp directory
            new: Path = out_d / p.name
            try:
                _copytree = False
                try:
                    p.rename(new)
                    edited = True
                except OSError:
                    copy3 = lambda src, dst: shutil.copy2(src, dst, follow_symlinks=False)
                    if p.is_dir() and not p.is_symlink():
                        _copytree = True
                        shutil.copytree(p, new, copy_function=copy3, symlinks=True)
                        edited = True
                        shutil.rmtree(p)
                    else:
                        copy3(p, new)
                        p.unlink()
                        edited = True
                success.append(p)
                full_where[p] = new
                where[p.name].add(out_d)
            except OSError as e:
                failed.append(p)
                _print_exc(e)
                if edited:
                    _print_stderr(f"WARNING: Contents of {p} may have been PARTIALLY delayed_rm'd")
                    continue
                if _copytree:
                    if output := _rmtree(new):
                        _print_stderr(output)
                    continue
                new.unlink()
            finally:
                any_edited |= edited
    except KeyboardInterrupt:
        ctrlc = True
    # Inform user of failures
    failed_plus: list[str] = [str(i) for i in failed]
    if len(failed) > 0 and not ctrlc:
        _print_exc(OSError("failed to rm:\n  " + "\n  ".join(failed_plus)))
    # Log result
    success_plus: list[str] = [f"{i}  --->  {full_where[i]}" for i in success]
    fmt: Callable[[list[str]], str] = lambda l: ("\n  " + "\n  ".join(l)) if l else " False"
    lines = (
        f"{datetime.now()}{'\nInterrupted by: SIGINT' if ctrlc else ''}",
        f"Delay: {delay}",
        f"rf: {rf}",
        f"Storage Directory: {base}",
        f"Succeeded:{fmt(success_plus)}",
        f"Failed:{fmt(failed_plus)}",
    )
    msg = "\n".join(lines).replace("\n", "\n  ") + "\n\n"
    try:
        with log_f.open("a") as f:
            f.write(msg)
    except OSError:
        _print_stderr(msg)
        raise
    # Delay rm and die
    if not any_edited:
        shutil.rmtree(base)
    else:
        subprocess.Popen(  # pylint: disable=consider-using-with # nosec B603
            (sys.executable, __file__, _Secret.value, str(delay), base),
            env={_Secret.key: _Secret.value},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    return not failed and not ctrlc


def delayed_rm_raw(delay: int, log: bool, r: bool, f: bool, paths: list[Path], unsafe: bool = False) -> bool:
    """
    A delayed_rm wrapper that handles CLI arguments
    :returns: True on success, else False
    """
    try:
        if log:
            if r or f or paths:
                _print_exc(ValueError("--log may not be used with other arguments"))
                return False
            print(f"{log_f.read_text()}Log file ({_size(log_f)}): {log_f}" if log_f.exists() else "Log is empty")
            return True
        if not paths:
            _print_exc(ValueError("nothing to remove; try --help"))
        elif r != f:
            _print_exc(ValueError("-r and -f must be used together"))
        elif delay < 0:
            _print_exc(ValueError("delay may not be negative"))
        else:
            return delayed_rm(paths=paths, delay=delay, rf=r, unsafe=unsafe)
    except RMError as e:
        _print_exc(e)
        return False
    return True


def cli() -> None:
    """
    delayed_rm CLI
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", action="version", version=f"{parser.prog} {__version__}")
    parser.add_argument("--delay", "--ttl", type=int, default=900, help="The deletion delay in seconds")
    parser.add_argument(
        "--log", action="store_true", help=f"Show {parser.prog}'s log files; may not be used with other arguments"
    )
    parser.add_argument("-r", action="store_true", help="rm -r; must use -f with this")
    parser.add_argument("-f", action="store_true", help="rm -f; must use -r with this")
    parser.add_argument("paths", type=Path, nargs="*", help="The items to delete")
    parser.add_argument(f"--{_UNSAFE_FLAG}", dest="unsafe", action="store_true", help=argparse.SUPPRESS)
    sys.exit(not delayed_rm_raw(**vars(parser.parse_args())))


#
# For daemon process
#


def _secret_cli() -> None:
    """
    This CLI is invoked on import and not will do nothing by default
    This CLI will only activate if argv was intentionally configured to do so
    This entrypoint is for the spawned process to act
    """
    if len(sys.argv) > 1 and sys.argv[1] == "--force-cli":
        del sys.argv[1]
        cli()
    try:
        if len(sys.argv) != 4 or sys.argv[1] != _Secret.value or environ.get(_Secret.key, None) != _Secret.value:
            _print_stderr(
                "This script should be run by invoking the cli() function.\n"
                "Pass --force-cli as the first argument to bypass this restriction.",
            )
            sys.exit(1)
        d = Path(sys.argv[3]).resolve()
        time.sleep(int(sys.argv[2]))
        with log_f.open("a") as f:
            if not d.exists(follow_symlinks=False):
                f.write(f"Directory {d} does not exist, nothing to do\n\n")
                return
            f.write(f"Removing: {d}")
            if errs := _rmtree(d):
                f.write(errs)
            f.write("\n\n")
    except Exception:
        sys.stderr = log_f.open("a")
        sys.stdout = sys.stderr
        _print_stderr(f"argv: {sys.argv}")
        raise


if __name__ == "__main__":
    _secret_cli()
