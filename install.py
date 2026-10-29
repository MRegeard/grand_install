# Install script for GRANDlib.
# Usage: python install.py <grandlib path> [options]

import os
import subprocess
import shutil
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from contextlib import contextmanager


class MissingGrandlibPathError(Exception):
    pass


TURTLE_URL = "https://github.com/niess/turtle.git"
GULL_URL = "https://github.com/niess/gull.git"
GULL_TAG = "286ace5"
TURTLE_VERSION = "v0.9"

FALLBACK_PYPROJECT = Path(__file__).parent / "fallback" / "pyproject.toml"


@dataclass
class Config:
    """Installation configuration class.

    This class bundles paths that are being used during the installation.
    """

    grandlib_root: Path
    root_dir: Path = field(default_factory=lambda: Path(__file__).parent)
    zig_bin: Optional[Path] = None

    def __post_init__(self):
        self.grandlib_root = Path(self.grandlib_root).expanduser().resolve()
        if not (self.grandlib_root / "grand" / "__init__.py").is_file():
            raise MissingGrandlibPathError(
                f"{self.grandlib_root} is not a Grandlib checkout (no grand/ package)."
            )
        self.root_dir = Path(self.root_dir).resolve()
        if self.zig_bin is not None:
            self.zig_bin = Path(self.zig_bin).expanduser().resolve()
        else:
            found = shutil.which("zig")
            if found is None:
                raise RuntimeError(
                    "No zig found on PATH. Activate the conda environment "
                    "or pass --zig <path>."
                )
            self.zig_bin = Path(found)

    @property
    def build_dir(self) -> Path:
        return self.root_dir / "build"

    @property
    def grand_dir(self) -> Path:
        return self.grandlib_root / "grand"


def clone_repos(cfg: Config):
    """Clone turtle and gull C libraries github repository.

    Notes
    -----
    Here we do not checkout to turtle v0.8, as done in the other installation
    method. This is because we need `png.h` in the deps directory to compile.
    We instead use version v0.9 which meets such requirement.

    Parameters
    ----------
    cfg: Config
       Install configuration.
    """
    cfg.build_dir.mkdir(parents=True, exist_ok=True)

    # Clone turtle v0.9
    turtle_dir = cfg.build_dir / "turtle"
    if not turtle_dir.exists():
        print("Cloning turtle...")
        try:
            subprocess.run(
                [
                    "git",
                    "clone",
                    "--branch",
                    TURTLE_VERSION,
                    TURTLE_URL,
                    str(turtle_dir),
                ],
                check=True,
            )
        except subprocess.CalledProcessError as e:
            shutil.rmtree(turtle_dir, ignore_errors=True)
            raise RuntimeError(f"Failed to clone turtle: {e}") from e
    else:
        print("turtle already cloned, skipping.")

    # Clone gull and checkout to commit 286ace5
    gull_dir = cfg.build_dir / "gull"
    if not gull_dir.exists():
        print("Cloning gull...")
        try:
            subprocess.run(
                [
                    "git",
                    "clone",
                    GULL_URL,
                    str(gull_dir),
                ],
                check=True,
            )
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(gull_dir),
                    "checkout",
                    GULL_TAG,
                ],
                check=True,
            )
        except subprocess.CalledProcessError as e:
            shutil.rmtree(gull_dir, ignore_errors=True)
            raise RuntimeError(f"Failed to clone gull: {e}") from e
    else:
        print("gull already cloned, skipping.")


def build_c_libs(cfg: Config):
    """Build the C libraries.

    Invoke the Zig compiler to build the C libraries using the build script
    located at `src/build.zig`.

    Notes
    -----
    Zig targets the current OS version by default, which may differ from cffi's
    deployment target, causing linker warnings. These are harmless for static
    linking and can be ignored.

    Parameters
    ----------
    cfg: Config
       Install configuration.
    """
    print("Building C libraries with Zig...")
    subprocess.run(
        [
            cfg.zig_bin,
            "build",
            "-Doptimize=ReleaseFast",
            "--prefix",
            str(cfg.build_dir),
        ],
        cwd=str(cfg.root_dir),
        check=True,
    )


@contextmanager
def temp_environ(**overrides: str):
    """Temporarily set environment variables, restoring them afterwards.

    Parameters
    ----------
    overrides: str
        Environment variable to override. Expected by keyword arguments call:
        `ENV_NAME = "env_value"`.
    """
    saved = {k: os.environ.get(k) for k in overrides}
    os.environ.update(overrides)
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def build_python_ext(cfg: Config):
    """Build the python C extension in-process with cffi.

    Parameters
    ----------
    cfg: Config
        Install configuration
    """
    import build_ext

    print("Building Python extension with cffi...")
    with temp_environ(LDFLAGS="", CFLAGS="", CXXFLAGS=""):
        module = build_ext.build(
            build_dir=cfg.build_dir,
            src_dir=cfg.grandlib_root / "src",
            zig_bin=cfg.zig_bin,
            out_dir=cfg.grand_dir,
        )
    print(f"Built {module}")


def ensure_pyproject(cfg: Config) -> Optional[Path]:
    """Copy the fallback pyproject.toml into the checkout if it has no packaging.

    Parameters
    ----------
    cfg: Config
        Install configuration.

    Returns
    -------
    path: Optional[Path]
        Returns the path of the copied file, or None if nothing was copied.
    """
    root = cfg.grandlib_root
    if (root / "pyproject.toml").is_file() or (root / "setup.py").is_file():
        return None
    print(
        "Warning: this GRANDlib branch has no pyproject.toml; using the fallback "
        f"from {FALLBACK_PYPROJECT}. It may not match this branch exactly."
    )
    target = root / "pyproject.toml"
    shutil.copy(FALLBACK_PYPROJECT, target)
    return target


def install_package(cfg: Config):
    """Install GRANDlib as a python library.

    Parameters
    ----------
    cfg: Config
       Install configuration.
    """
    print("Installing grand package...")
    copied = ensure_pyproject(cfg)
    try:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "-e",
                str(cfg.grandlib_root),
            ],
            cwd=str(cfg.root_dir),
            check=True,
        )
    finally:
        if copied is not None:
            copied.unlink(missing_ok=True)


def cleanup(cfg: Config):
    """Cleanup build artefacts.

    Parameters
    ----------
    cfg: Config
       Install configuration.
    """
    print("Cleaning up build artifacts...")
    shutil.rmtree(cfg.build_dir, ignore_errors=True)
    shutil.rmtree(cfg.root_dir / ".zig-cache", ignore_errors=True)
    print("Cleaning done.")


def check_args(argv):
    """Trim command line arguments if necessary.

    Parameters
    ----------
    argv: list of str
        The command line arguments.
    """
    if len(argv) <= 1:
        usage()
        raise MissingGrandlibPathError("Missing <grandlib path> argument.")
    return argv[1:]


def parse_args(args) -> Config:
    """Parse the command line arguments and set config flags if necessary.

    Parameters
    ----------
    args: list of str
        Command line arguments, python script name trimmed.

    Returns
    -------
    cfg: Config
        Install configuration.
    """
    if "--help" in args or "-h" in args:
        usage()
        sys.exit(0)

    zig_bin = None
    if "--zig" in args:
        i = args.index("--zig")
        if i + 1 >= len(args):
            usage()
            sys.exit("error: --zig requires a path")
        zig_bin = args[i + 1]

    return Config(
        grandlib_root=args[0],
        zig_bin=zig_bin,
    )


def usage():
    """Print usage."""
    options = [
        ("--zig [path]", "Use specific Zig binary located at [path]"),
        ("-h, --help", "Show this help message"),
    ]
    print("info: Usage: python install.py <grandlib path> [options]\n")
    print("Options:")
    for name, desc in options:
        print(f"  {name:<28}{desc}")


def main():
    args = check_args(sys.argv)
    cfg = parse_args(args)
    print("=== Installing GRANDlib ===")
    try:
        clone_repos(cfg)
        build_c_libs(cfg)
        build_python_ext(cfg)
        install_package(cfg)
    except Exception:
        print("Error encountered!")
        cleanup(cfg)
        raise
    cleanup(cfg)
    print("=== Done ===")


if __name__ == "__main__":
    main()
