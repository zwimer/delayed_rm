from __future__ import annotations
from collections import defaultdict
from tempfile import gettempdir
from datetime import datetime
from typing import Callable
from pathlib import Path
import subprocess
import argparse
import tempfile
import shutil
import time
import sys
import os


__version__ = "2.7.0"


#
# Config
#


log_f: Path = Path.home().resolve() / ".delayed_rm.log"
tmp_d: Path = Path(gettempdir()).resolve() / ".delayed_rm"


#
# Classes
#


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
    value: str = "cL5r0!L4hmWmonW7k^RZM*4nq7mR&yfF"


#
# Functions
#


def _eprint(e: str | BaseException) -> None:
    """
    Print e to stderr
    """
    e2: str | BaseException = e
    if isinstance(e, RMError) and isinstance(e.__cause__, BaseException):
        e2 = e.__cause__
    err: str = (
        "Error"
        if isinstance(e2, RMError) or not isinstance(e, BaseException)
        else str(type(e2)).split("'")[1].split("delayed_rm.")[-1]
    )
    print(f"{err}: {e}", file=sys.stderr)


def _mkdir(ret: Path) -> Path:
    """
    Make base/name and set permissions to 700
    """
    ret.mkdir()
    ret.chmod(0o700)
    return ret


def _prep(paths: list[Path], rf: bool) -> list[Path]:
    """
    Normalize paths, error check, and prep temp items
    :return: A normalized list of paths
    """
    # Normalize paths and error checking
    try:
        paths = [i.parent.resolve(strict=True) / i.name for i in paths]
        # pathlib.stat does not support follow_symlinks until 3.10
        if len(paths) != len({os.stat(i, follow_symlinks=False).st_ino for i in paths}):
            raise RMError("duplicate items passed")
    except (FileNotFoundError, RuntimeError) as e:
        raise RMError(e) from e
    for i in paths:
        if not rf and not i.is_symlink() and i.is_dir():
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


def delayed_rm(paths: list[Path], delay: int, rf: bool) -> bool:
    """
    Move paths to a temprary directory, delete them after delay seconds
    Log's this action to the log
    If rf, acts like rm -rf
    May raise an RMError if something goes wrong
    :returns: True on success, else False
    """
    assert tmp_d.parent.exists(), "Temp dir enclosing directory does not exist"
    assert log_f.parent.exists(), "Log file enclosing directory does not exist"
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
    edited = False
    try:
        for p in paths:
            # Select an output directory that an item of name p.name does not exist
            outd: Path
            if len(out_dirs) != len(where[p.name]):
                outd = next(iter(out_dirs - where[p.name]))
            else:
                outd = _mkdir(base / str(len(out_dirs)))
                out_dirs.add(outd)
            # Move file into the temp directory
            try:
                new: Path = outd / p.name
                try:
                    p.rename(new)
                except OSError:
                    copyf = lambda src, dst: shutil.copy2(src, dst, follow_symlinks=False)
                    if p.is_dir():
                        shutil.copytree(p, new, copy_function=copyf, symlinks=False)
                        edited = True
                        shutil.rmtree(p)
                    else:
                        copyf(p, new)
                        edited = True
                        p.unlink()
                success.append(p)
                full_where[p] = new
                where[p.name].add(outd)
            except OSError as e:
                failed.append(p)
                _eprint(e)
    except KeyboardInterrupt:
        ctrlc = True
    # Inform user of failures
    failed_plus: list[str] = [str(i) for i in failed]
    if len(failed) > 0 and not ctrlc:
        _eprint("failed to rm:\n  " + "\n  ".join(failed_plus))
    # Log result
    success_plus: list[str] = [f"{i}  --->  {full_where[i]}" for i in success]
    fmt: Callable[[list[str]], str] = lambda l: ("\n  " + "\n  ".join(l)) if l else " None"
    msg: str = (
        str(datetime.now())
        + "\n  "
        + "\n".join(
            (
                ("Interrupted by: SIGINT\n" if ctrlc else "") + f"Delay: {delay}",
                f"rf: {rf}",
                f"Storage Directory: {base}",
                f"Succeeded:{fmt(success_plus)}",
                f"Failed:{fmt(failed_plus)}",
            )
        ).replace("\n", "\n  ")
        + "\n\n"
    )
    try:
        with log_f.open("a") as f:
            f.write(msg)
    except OSError:
        print(msg)
        raise
    # Delay rm and die
    if not edited:
        shutil.rmtree(base)
    else:
        subprocess.Popen(  # pylint: disable=consider-using-with
            (sys.executable, __file__, _Secret.value, str(delay), base),
            env={_Secret.key: _Secret.value},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    return not failed and not ctrlc


def delayed_rm_raw(delay: int, log: bool, r: bool, f: bool, paths: list[Path]) -> bool:
    """
    A delayed_rm wrapper that handles CLI arguments
    :returns: True on success, else False
    """
    try:
        if log:
            if r or f or paths:
                _eprint("--log may not be used with other arguments")
                return False
            if log_f.exists():
                with log_f.open("r") as file:
                    data: str = file.read()
                print(data + f"Log file: {log_f}")
            else:
                print("Log is empty")
            return True
        if not paths:
            _eprint("nothing to remove")
        elif r != f:
            _eprint("-r and -f must be used together")
        elif delay < 0:
            _eprint("delay may not be negative")
        else:
            return delayed_rm(paths=paths, delay=delay, rf=r)
    except RMError as e:
        _eprint(e)
        return False
    return True


def main(prog: str, *args: str) -> bool:
    base: str = os.path.basename(prog)
    parser = argparse.ArgumentParser(prog=base)
    parser.add_argument("--version", action="version", version=f"{base} {__version__}")
    parser.add_argument("-d", "--delay", type=int, default=900, help="The deletion delay in seconds")
    parser.add_argument(
        "--log", action="store_true", help=f"Show {base}'s log files; may not be used with other arguments"
    )
    parser.add_argument("-r", action="store_true", help="rm -r; must use -f with this")
    parser.add_argument("-f", action="store_true", help="rm -f; must use -r with this")
    parser.add_argument("paths", type=Path, nargs="*", help="The items to delete")
    return not delayed_rm_raw(**vars(parser.parse_args(args)))


def cli() -> None:
    """
    delayed_rm CLI
    """
    sys.exit(main(*sys.argv))


#
# For daemon process
#


def _secret_cli():
    """
    This CLI is invoked on import and not will do nothing by default
    This CLI will only active if argv was intentionally configured to do so
    This entrypoint is for the spawned process to act
    """
    try:
        if len(sys.argv) == 4 and sys.argv[1] == _Secret.value:
            if os.environ.get(_Secret.key, None) == _Secret.value:
                delay = int(sys.argv[2])
                d = Path(sys.argv[3]).resolve()
                time.sleep(delay)
                shutil.rmtree(d)
                with log_f.open("a") as f:
                    f.write(f"Removing: {d}" + "\n\n")
    except Exception:
        sys.stderr = log_f.open("a")
        sys.stdout = sys.stderr
        print(f"argv: {sys.argv}", flush=True)
        raise


if __name__ == "__main__":
    _secret_cli()
