from typing import Callable, List, Dict, Set, Any
from collections import defaultdict
from tempfile import gettempdir
from datetime import datetime
from pathlib import Path
import subprocess
import argparse
import tempfile
import shutil
import time
import sys
import os


__version__ = "2.2.3"


#
# Config
#


log_f: Path = Path.home() / ".delayed_rm.log"
tmp_d: Path = Path(gettempdir()) / ".delayed_rm"


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


def eprint(msg: Any) -> None:
    """
    Print msg to stderr
    """
    print(f"Error: {msg}", file=sys.stderr)


def mkdir(ret: Path) -> Path:
    """
    Make base/name and set permissions to 700
    """
    ret.mkdir()
    ret.chmod(0o700)
    return ret


def validate_paths(paths: List[Path], rf: bool) -> bool:
    """
    Verify paths and that they can be removed with rf set as it is
    """
    if len(paths) != len(set(paths)):
        eprint("duplicate items passed")
        return False
    for i in paths:
        if not i.exists() and not i.is_symlink():
            eprint(f"{i} does not exist")
            return False
        elif not rf and i.is_dir():
            eprint(f"{i} is a directory. -rf required!")
            return False
    return True


def delayed_rm(paths: List[Path], delay: int, rf: bool) -> bool:
    """
    Move paths to a temprary directory, delete them after delay seconds
    Log's this action to the log
    If rf, acts like rm -rf
    """
    assert tmp_d.parent.exists(), "Temp dir enclosing directory does not exist"
    assert log_f.parent.exists(), "Log file enclosing directory does not exist"
    paths = [ i.absolute() for i in paths ]
    if not validate_paths(paths, rf):
        return False
    # Prepare output locations
    log_f.touch()
    tmp_d.mkdir(exist_ok=True)
    base = Path(tempfile.mkdtemp(dir=tmp_d))
    base.chmod(0o700)
    # Init data structures
    success: List[Path] = []
    failed: List[Path] = []
    out_dirs: Set[Path] = { mkdir(base / "0") }
    where: Dict[str, Set[Path]] = defaultdict(set)
    full_where: Dict[Path, Path] = {}
    # Delete files
    for p in paths:
        # Select an output directory that an item of name p.name does not exist
        outd: Path
        if len(out_dirs) != len(where[p.name]):
            outd = next(iter(out_dirs - where[p.name]))
        else:
            outd = mkdir(base / str(len(out_dirs)))
            out_dirs.add(outd)
        # Move file into the temp directory
        try:
            new: Path = outd / p.name
            try:
                p.rename(new)
            except OSError:
                if p.is_dir():
                    shutil.copytree(p, new)
                    shutil.rmtree(p)
                else:
                    shutil.copy2(p, new)
                    p.unlink()
            full_where[p] = new
            where[p.name].add(outd)
            success.append(p)
        except OSError as e:
            failed.append(p)
            eprint(e)
    # Inform user of failures
    failed_plus: List[str] = [str(i) for i in failed]
    if len(failed) > 0:
        eprint("Error: failed to rm:\n" + "\n".join(failed_plus))
    # Log result
    success_plus: List[str] = [f"{i}  --->  {full_where[i]}" for i in success]
    fmt: Callable[[List[str]], str] = lambda l: ("\n  " + "\n  ".join(l)) if l else " None"
    msg: str = str(datetime.now()) + "\n  " + "\n".join((
        f"Delay: {delay}",
        f"rf: {rf}",
        f"Storage Directory: {base}",
        f"Succeeded:{fmt(success_plus)}",
        f"Failed:{fmt(failed_plus)}",
    )).replace("\n", "\n  ") + "\n\n"
    with log_f.open("a") as f:
        f.write(msg)
    # Delay rm and die
    if not success:
        shutil.rmtree(base)
    else:
        subprocess.Popen(  # pylint: disable=consider-using-with
            (sys.executable, __file__, _Secret.value, str(delay), base),
            env = { _Secret.key: _Secret.value },
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    return not failed


def delayed_rm_raw(delay: int, log: bool, r: bool, f: bool, paths: List[Path]) -> bool:
    """
    Handles argument verification before invoking delayed_rm properly
    """
    if log:
        if r or f or paths:
            eprint("--log may not be used with other arguments")
            return False
        if log_f.exists():
            with log_f.open("r") as file:
                data: str = file.read()
            print(data + f"Log file: {log_f}")
        else:
            print("Log is empty")
        return True
    if not paths:
        eprint("nothing to remove")
    elif r != f:
        eprint("-r and -f must be used together")
    elif delay < 0:
        eprint("delay may not be negative")
    else:
        return delayed_rm(paths=paths, delay=delay, rf=r)
    return False


def main(prog: str, *args: str) -> bool:
    base: str = os.path.basename(prog)
    parser = argparse.ArgumentParser(prog=base)
    parser.add_argument("--version", action="version", version=f"{base} {__version__}")
    parser.add_argument("-d", "--delay", type=int, default=900, help="The deletion delay in seconds")
    parser.add_argument("--log", action="store_true", help=f"Show {base}'s log files; may not be used with other arguments")
    parser.add_argument("-r", action="store_true", help="rm -r; must use -f with this")
    parser.add_argument("-f", action="store_true", help="rm -f; must use -r with this")
    parser.add_argument("paths", type=Path, nargs="*", help="The items to delete")
    return delayed_rm_raw(**vars(parser.parse_args(args)))


def cli() -> None:
    """
    delayed_rm CLI
    """
    with open("/tmp/qqq", "a") as f:
        f.write("normal: " + str(sys.argv) + "\n")
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
    with open("/tmp/qqq", "a") as f:
        f.write("secret: " + str(sys.argv) + "\n")
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
