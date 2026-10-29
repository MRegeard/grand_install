# Install script for GRANDlib.
# Usage: python install.py <grandlib path> [options]

import os
import subprocess
import shutil
import sys
import platform
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Self
import urllib.request
import tarfile
import re
from contextlib import contextmanager


class InvalidVersion(Exception):
    pass


class MissingGrandlibPathError(Exception):
    pass


@dataclass(order=True)
class Version:
    """Software version.

    This class store software version. Largely inspired by Zig `std.SemanticVersion`.

    Notes
    -----
    For now the pre-release and build specific tags are not supported.

    Parameters
    ----------
    major: int
        Major version number.
    minor: int
        Minor version number.
    patch: int
        Patch version number.
    """

    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, input_str: str) -> Self:
        """Parse the version from a string.

        Parameters
        ----------
        input_str: str
            String containing the version to be parsed.
        """
        required = re.split(r"[+\-]", input_str)
        required = required[0]

        # Parse required major, minor and patch numbers.
        ver_split = required.split(".")
        if len(ver_split) != 3:
            raise InvalidVersion(
                f"Expected version format to be `Major.minor.patch`, got {
                    required}."
            )
        kwargs = {}
        kwargs["major"] = int(ver_split[0])
        kwargs["minor"] = int(ver_split[1])
        kwargs["patch"] = int(ver_split[2])
        return cls(**kwargs)

    def __str__(self):
        """String representation."""
        s = f"{self.major}.{self.minor}.{self.patch}"
        return s


@dataclass
class Range:
    """Version range.

    Parameters
    ----------
    min: Version
        Minimum version.
    max: Verison
        Maximum version.
    """

    min: Version
    max: Version

    def includes_version(self: Self, ver: Version) -> bool:
        return self.min <= ver < self.max


TURTLE_URL = "https://github.com/niess/turtle.git"
GULL_URL = "https://github.com/niess/gull.git"
GULL_TAG = "286ace5"
TURTLE_VERSION = "v0.9"

ZIG_VERSION_RANGE = Range(min=Version.parse(
    "0.16.0"), max=Version.parse("0.17.0"))
ZIG_DL_URL = "https://ziglang.org/download/"
ZIG_VERSION = "0.16.0"

FALLBACK_PYPROJECT = Path(__file__).parent / "fallback" / "pyproject.toml"


@dataclass
class Config:
    """Installation configuration class.

    This class bundles paths that are being used during the installation.
    """

    grandlib_root: Path
    root_dir: Path = field(default_factory=lambda: Path(__file__).parent)
    zig_bin: Optional[Path] = None
    download: bool = True

    def __post_init__(self):
        self.grandlib_root = Path(self.grandlib_root).expanduser().resolve()
        if not (self.grandlib_root / "grand" / "__init__.py").is_file():
            raise MissingGrandlibPathError(
                f"{self.grandlib_root} is not a Grandlib checkout (no pyptoject.toml)."
            )
        self.root_dir = Path(self.root_dir).resolve()
        if self.zig_bin is not None:
            self.zig_bin = Path(self.zig_bin).expanduser().resolve()

    @property
    def build_dir(self) -> Path:
        return self.root_dir / "build"

    @property
    def grand_dir(self) -> Path:
        return self.grandlib_root / "grand"

    @property
    def zig_path(self) -> Path:
        return self.root_dir / ".zig"


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


def install_zig(cfg: Config):
    """Install the Zig compiler.

    Check if a Zig compiler is installed and if the version mathced

    Parameters
    ----------
    cfg: Config
       Install configuration.
    """
    system = platform.system()
    machine = platform.machine()

    # Check if zig is already available
    zig_bin = cfg.zig_bin
    if zig_bin is None:
        found = shutil.which("zig")
        zig_bin = Path(found) if found is not None else None

    if zig_bin is not None:
        print(f"Found zig executable at {zig_bin}...")
        version = (
            subprocess.run([zig_bin, "version"],
                           check=True, capture_output=True)
            .stdout.decode()
            .strip()
        )
        print(f"Zig version: {version}")
        if ZIG_VERSION_RANGE.includes_version(Version.parse(version)):
            print(f"Zig version {version} matches the requirement.")
            cfg.zig_bin = zig_bin
            return
        print(
            f"""Found zig version: {version}, but requires zig version
            between {ZIG_VERSION_RANGE.min} and {ZIG_VERSION_RANGE.max}..."""
        )

    if cfg.download is False:
        raise RuntimeError(
            f"No Zig {ZIG_VERSION_RANGE.min}–{
                ZIG_VERSION_RANGE.max} found and "
            "--no-download was given. Use --zig <path> or allow the download."
        )

    # If no Zig compiler is found in the PATH or is its version does match,
    # check if there is a Zig version in the .zig folder of the root dir
    local = find_local_zig(cfg.zig_path)
    if local is not None:
        cfg.zig_bin = local
        print(f"Using previously downloaded Zig at {cfg.zig_bin}")
        return

    # Otherwise, download Zig
    arch = "aarch64" if machine in ("arm64", "aarch64") else "x86_64"
    if system == "Darwin":
        url = f"{ZIG_DL_URL}{
            ZIG_VERSION}/zig-{arch}-macos-{ZIG_VERSION}.tar.xz"
    elif system == "Linux":
        url = f"{ZIG_DL_URL}{
            ZIG_VERSION}/zig-{arch}-linux-{ZIG_VERSION}.tar.xz"
    elif system == "Windows":
        arch = "aarch64" if machine == "ARM64" else "x86_64"
        url = f"{ZIG_DL_URL}{ZIG_VERSION}/zig-{arch}-windows-{ZIG_VERSION}.zip"
    else:
        raise RuntimeError(f"Please install Zig manually from {ZIG_DL_URL}")

    cfg.zig_path.mkdir(exist_ok=True)
    print(f"Downloading Zig from {url}...")
    if system == "Windows":
        tarball = cfg.zig_path / "zig.zip"
    else:
        tarball = cfg.zig_path / "zig.tar.xz"
    urllib.request.urlretrieve(url, str(tarball))

    verify_zig_signature(cfg, tarball, url)

    print("Extracting Zig...")
    if system == "Windows":
        import zipfile

        with zipfile.ZipFile(str(tarball)) as zf:
            zf.extractall(str(cfg.zig_path))
    else:
        with tarfile.open(str(tarball)) as tar:
            if hasattr(tarfile, "data_filter"):
                tar.extractall(str(cfg.zig_path), filter="data")
            else:
                tar.extractall(str(cfg.zig_path))
    tarball.unlink()

    cfg.zig_bin = find_local_zig(cfg.zig_path)
    if cfg.zig_bin is None:
        raise RuntimeError(f"Zig extracted to {
                           cfg.zig_path} but no binary was found.")
    print(f"Zig installed at {cfg.zig_bin}")


def find_local_zig(zig_path: Path) -> Optional[Path]:
    name = "zig.exe" if platform.system() == "Windows" else "zig"
    return next(zig_path.glob(f"zig-*/{name}"), None)


def verify_zig_signature(cfg: Config, tarball: Path, url: str):
    """Verify Zig compiler signature to avoid corrupted data.

    Parameters
    ----------
    cfg: Config
       Install configuration.
    tarball: Path
        The tarball to check.
    url: str
       The base url to fetch the signature.
    """
    import minisign

    ZIG_PUBLIC_KEY = "RWSGOq2NVecA2UPNdBUZykf1CCb147pkmdtYxgb3Ti+JO/wCYvhbAb/U"

    sig_url = url + ".minisig"
    sig_file = tarball.parent / (tarball.name + ".minisig")
    print(f"Downloading signature from {sig_url}...")
    urllib.request.urlretrieve(sig_url, str(sig_file))

    print("Verifying signature...")
    try:
        pk = minisign.PublicKey.from_base64(ZIG_PUBLIC_KEY)
        with open(tarball, "rb") as f:
            data = f.read()
        with open(sig_file, "rb") as f:
            sig = minisign.Signature.from_bytes(f.read())
        pk.verify(data, sig)
        print("Signature verified successfully.")
    except Exception as e:
        tarball.unlink(missing_ok=True)
        raise RuntimeError(
            f"Zig signature verification failed: {e}\n"
            "The download may be corrupted or tampered with."
        ) from e
    finally:
        sig_file.unlink(missing_ok=True)


def build_c_libs(cfg: Config):
    """Build the C libraries.

    Invoke the Zig compiler to build the C libraries using the build script
    located at `src/build.zig`.

    Notes
    -----
    Zig targets the current OS version by default, which may differ from cffi's
    deployement target, causing linker warnings. These are harmless for static
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
            out_dir=cfg.grand_dir,
        )
    print(f"Built {module}")o


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
    print("Warning: this GRANDlib branch has no pyproject.toml; using the fallback "
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
        if copied is not NOne:
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
        raise MissingGrandlibPathError
    return argv[1:]


def parse_args(args) -> Config:
    """Parse the command line arguments and set config flags is necessary.

    Parameters
    ----------
    args: list od str
        Command line arguments, python script name trimmed.
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
        download="--no-download" not in args,
    )


def usage():
    """Print usage."""
    options = [
        ("--no-download", "Do not download the Zig compiler"),
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
        install_zig(cfg)
        build_c_libs(cfg)
        build_python_ext(cfg)
        install_package(cfg)
    except Exception:
        print("Error encounter!")
        cleanup(cfg)
        raise
    cleanup(cfg)
    print("=== Done ===")


if __name__ == "__main__":
    main()
