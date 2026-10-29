"""Build the GRANDlib Python C extension (grand._core) with cffi and Zig.

cffi only generates the C source of the extension; Zig preprocesses grand.h and
compiles and links the extension, so no system C compiler is needed.
"""

import argparse
import platform
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path
from typing import Optional

from cffi import FFI
from pycparser import c_generator, parse_file


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


def extension_name() -> str:
    """File name Python expects for the stable-ABI extension on this platform."""
    return "_core.pyd" if platform.system() == "Windows" else "_core.abi3.so"


def make_ffi(src_dir: Path, inc_dir: Path, zig_bin: Path) -> FFI:
    """Declare grand.h to cffi, using `zig cc -E` as the C preprocessor."""
    ffi = FFI()
    ast = parse_file(
        str(src_dir / "grand.h"),
        use_cpp=True,
        cpp_path=str(zig_bin),
        cpp_args=["cc", "-E", f"-I{inc_dir}", "-DFILE=struct FILE"],
    )
    ffi.cdef(c_generator.CGenerator().visit(ast))
    ffi.set_source("grand._core", (src_dir / "grand.c").read_text())
    return ffi


def compile_extension(
    c_file: Path,
    out: Path,
    zig_bin: Path,
    include_dirs: list[Path],
    objects: list[Path],
) -> None:
    """Compile and link the generated C source into a Python extension with Zig."""
    cmd = [
        str(zig_bin),
        "cc",
        "-shared",
        "-fPIC",
        "-O2",
        f"-I{sysconfig.get_path('include')}",
        *(f"-I{d}" for d in include_dirs),
        str(c_file),
        *(str(o) for o in objects),
        "-o",
        str(out),
    ]

    system = platform.system()
    if system == "Darwin":
        # Python symbols are provided by the interpreter at import time.
        cmd += ["-undefined", "dynamic_lookup", f"-Wl,-install_name,{out.name}"]
    elif system == "Windows":
        # Untested: link against the stable-ABI import library python3.lib.
        cmd += [f"-L{Path(sys.base_prefix) / 'libs'}", "-lpython3"]

    subprocess.run(cmd, check=True)


def build(
    build_dir: Path,
    src_dir: Path,
    out_dir: Optional[Path] = None,
    zig_bin: Optional[Path] = None,
) -> Path:
    """Build grand._core and return the path of the compiled module."""
    build_dir = Path(build_dir).expanduser().resolve()
    src_dir = Path(src_dir).expanduser().resolve()
    out_dir = Path(out_dir or build_dir / "grand").expanduser().resolve()
    if zig_bin is None:
        found = shutil.which("zig")
        if found is None:
            raise RuntimeError("No zig found on PATH; pass zig_bin explicitly.")
        zig_bin = Path(found)

    lib_dir = build_dir / "lib"
    inc_dir = build_dir / "include"
    tmp_dir = build_dir / "tmp"

    check_inputs(src_dir, inc_dir, lib_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    c_file = tmp_dir / "_core.c"
    make_ffi(src_dir, inc_dir, zig_bin).emit_c_code(str(c_file))

    module = out_dir / extension_name()
    compile_extension(
        c_file,
        module,
        zig_bin,
        include_dirs=[inc_dir, src_dir],
        objects=[lib_dir / "libturtle.a", lib_dir / "libgull.a"],
    )
    return module


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("build_dir", type=Path)
    parser.add_argument(
        "--src-dir",
        type=Path,
        required=True,
        help="Directory containing grand.h and grand.c (GRANDlib's src/).",
    )
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument(
        "--zig", type=Path, default=None, help="Zig binary (default: zig on PATH)."
    )
    args = parser.parse_args()
    module = build(args.build_dir, args.src_dir, args.out_dir, args.zig)
    print(f"Built {module}")


if __name__ == "__main__":
    main()
