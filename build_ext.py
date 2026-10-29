"""Build the GRANDlib cffi extension module (grand._core)."""

import argparse
from pathlib import Path
from cffi import FFI
from pycparser import c_generator, parse_file
import shutil
import platform
import sysconfig
import subprocess


def make_ffi(src_dir: Path, inc_dir: Path, lib_dir: Path, zig_bin: Path) -> FFI:
    ffi = FFI()

    ast = parse_file(
        str(src_dir / "grand.h"),
        use_cpp=True,
        cpp_path=str(zig_bin),
        cpp_args=["cc", "-E", f"-I{inc_dir}", "-DFILE=struct FILE"],
    )
    ffi.cdef(c_generator.CGenerator().visit(ast))

    ffi.set_source(
        "grand._core",
        (src_dir / "grand.c").read_text(),
        extra_objects=[str(lib_dir / "libturtle.a"), str(lib_dir / "libgull.a")],
        include_dirs=[str(inc_dir), str(src_dir)],
    )
    return ffi


def check_inputs(src_dir: Path, inc_dir: Path, lib_dir: Path) -> None:
    """Fail early with a clear message instead of a cryptic compiler error."""
    required = [
        src_dir / "grand.h",
        src_dir / "grand.c",
        inc_dir / "turtle.h",
        inc_dir / "gull.h",
        lib_dir / "libturtle.a",
        lib_dir / "libgull.a",
    ]
    missing = [str(p) for p in required if not p.is_file()]
    if missing:
        raise FileNotFoundError("Missing build inputs:\n  " + "\n  ".join(missing))


def strip_conda_rpath(module: Path) -> None:
    """Remove the conda lib rpath on macOS; not needed with static linking."""
    conda_lib = str(Path(sysconfig.get_path("stdlib")).parent.parent / "lib")
    result = subprocess.run(
        ["otool", "-l", str(module)], capture_output=True, text=True
    )
    if any("path" in line and conda_lib in line for line in result.stdout.splitlines()):
        subprocess.run(
            ["install_name_tool", "-delete_rpath", conda_lib, str(module)],
            capture_output=True,
        )


def build(
    build_dir: Path, src_dir: Path, zig_bin: Path, out_dir: Path | None = None
) -> Path:
    """Build grand._core and return the path of the compiled module."""
    build_dir = Path(build_dir).expanduser().resolve()
    src_dir = Path(src_dir).expanduser().resolve()
    out_dir = Path(out_dir or build_dir / "grand").expanduser().resolve()

    lib_dir = build_dir / "lib"
    inc_dir = build_dir / "include"
    tmp_dir = build_dir / "tmp"

    check_inputs(src_dir, inc_dir, lib_dir)
    ffi = make_ffi(src_dir, inc_dir, lib_dir, zig_bin)

    tmp_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    built = Path(ffi.compile(tmpdir=str(tmp_dir), verbose=False))
    module = out_dir / "_core.abi3.so"
    shutil.move(str(built), str(module))

    if platform.system() == "Darwin":
        strip_conda_rpath(module)

    return module


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("build_dir", type=Path)
    parser.add_argument(
        "--src-dir",
        type=Path,
        required=True,
        help="Directory containing grand.h and grand.c (Grandlib's src/).",
    )
    zig_found = shutil.which("zig")
    if zig_found is None:
        raise RuntimeError(
            "No zig found on PATH. Activate the conda environment or pass --zig <path>."
        )
    parser.add_argument("--zig", type=Path, default=Path(zig_found))
    parser.add_argument("--out-dir", type=Path, default=None)
    args = parser.parse_args()
    module = build(args.build_dir, args.src_dir, args.zig, args.out_dir)
    print(f"Built {module}")


if __name__ == "__main__":
    main()
