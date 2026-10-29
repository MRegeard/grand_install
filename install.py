# Install script for GRANDlib.
# Usage: python install.py <grandlib path> [options]

import subprocess
import sysconfig
import shutil
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
import os


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
    aires_bin: Optional[Path] = None
    download_data: bool = True

    def __post_init__(self):
        self.grandlib_root = Path(self.grandlib_root).expanduser().resolve()
        if not (self.grandlib_root / "grand" / "__init__.py").is_file():
            raise MissingGrandlibPathError(
                f"{self.grandlib_root} is not a GRANDlib checkout (no grand/ package)."
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
        if self.aires_bin is not None:
            self.aires_bin = Path(self.aires_bin).expanduser().resolve()

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
    `build.zig` located at the root of this repository.

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


def build_python_ext(cfg: Config):
    """Build the Python C extension.

    cffi generates the C source of the extension, and Zig compiles and links it.

    Parameters
    ----------
    cfg: Config
        Install configuration.
    """
    import build_ext

    print("Building Python C extension with cffi and Zig...")
    module = build_ext.build(
        build_dir=cfg.build_dir,
        src_dir=cfg.grandlib_root / "src",
        out_dir=cfg.grand_dir,
        zig_bin=cfg.zig_bin,
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


def add_grandlib_root_to_path(cfg: Config):
    """Make top-level GRANDlib modules (e.g. sim2root) importable, like PYTHONPATH in env/setup.sh."""
    site_packages = Path(sysconfig.get_path("purelib"))
    pth = site_packages / "grandlib_root.pth"
    pth.write_text(f"{cfg.grandlib_root}\n")
    print(f"Added {cfg.grandlib_root} to the Python path ({pth})")


def set_conda_env_vars(cfg: Config):
    """Store GRANDlib's environment variables in the active conda environment."""
    prefix = os.environ.get("CONDA_PREFIX")
    conda = os.environ.get("CONDA_EXE", "conda")
    if prefix is None:
        print("Warning: not a conda environment; skipping environment variables.")
        return

    env_vars = [f"GRAND_ROOT={cfg.grandlib_root}"]
    if cfg.aires_bin is not None:
        env_vars.append(f"AIRESBINDIR={cfg.aires_bin}")

    subprocess.run(
        [conda, "env", "config", "vars", "set", "-p", prefix, *env_vars],
        check=True,
    )
    print("Environment variables set; re-activate the environment to apply them:\n")
    print(f"\tconda deactivate && conda activate {Path(prefix).name}\n")


def download_data(cfg: Config):
    """Download the GRAND data model (about 1GB), if not already up to date."""
    script = cfg.grandlib_root / "data" / "download_data_grand.py"
    if not script.is_file():
        print(f"Warning: {script} not found; skipping the data download.")
        return

    print("Downloading the GRAND data model (about 1GB, skipped if up to date)...")
    try:
        subprocess.run([sys.executable, str(script)], check=True)
    except subprocess.CalledProcessError:
        print(
            "Warning: the data download failed. GRANDlib is installed, but the "
            "detector, noise and topography data are missing. Retry with:\n"
            f"\tpython {script}"
        )


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
        raise MissingGrandlibPathError("missing <grandlib path> argument")
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

    aires_bin = None
    if "--aires" in args:
        i = args.index("--aires")
        if i + 1 >= len(args):
            usage()
            sys.exit("error: --aires requires a path")
        aires_bin = args[i + 1]
    download_data = "--no-download-data" not in args

    return Config(
        grandlib_root=args[0],
        zig_bin=zig_bin,
        aires_bin=aires_bin,
        download_data=download_data,
    )


def usage():
    """Print usage."""
    options = [
        ("--zig [path]", "Use specific Zig binary located at [path]"),
        ("-h, --help", "Show this help message"),
        ("--aires [path]", "Set AIRESBINDIR to the AIRES bin directory at [path]"),
        ("--no-download-data", "Do not download the GRAND data model (about 1 GB)"),
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
        add_grandlib_root_to_path(cfg)
    except Exception:
        print("Error encountered!")
        cleanup(cfg)
        raise
    cleanup(cfg)
    set_conda_env_vars(cfg)
    if cfg.download_data:
        download_data(cfg)
    print("=== Done ===")


if __name__ == "__main__":
    main()
