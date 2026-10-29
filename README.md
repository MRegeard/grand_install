# GRANDlib Install: a unified external installation procedure

This repository provides a single, cross-platform procedure to install [GRANDlib](https://github.com/grand-mother/grand).
The official installation procedure (see the
[installation documentation](https://github.com/grand-mother/grand/blob/dev-next/docs/source/installation.rst)
on the default branch, `dev-next`) currently supports only Linux x86-64.

GRANDlib depends on two C libraries: [TURTLE](https://github.com/niess/turtle) for topography and
[GULL](https://github.com/niess/gull) for the geomagnetic field. Both libraries need to be compiled and linked
into GRANDlib's Python C extension, and this is the step that makes cross-platform installation difficult.
This procedure relies on the [Zig](https://ziglang.org/) compiler, which compiles C code consistently
across operating systems and architectures.

## Prerequisites and recommendations

GRANDlib is installed in a conda environment, so an up-to-date conda installation is required.

To install GRANDlib as a Python package inside the conda environment, the install script needs a `pyproject.toml` file.
GRANDlib provides one on its `dev-next` branch (and the `dev-next-*` branches derived from it). We therefore recommend
checking out the `dev-next` branch to simplify the installation. If the current branch of the provided GRANDlib directory
contains neither a `pyproject.toml` nor a `setup.py` file, the install script falls back to the `pyproject.toml` file
provided in this repository.

> [!NOTE]
> The authors of this repository try their best to keep this file in sync with the one on GRANDlib's
> `dev-next` branch, but this cannot be guaranteed.

## Installation

### Conda environment

First, create a conda environment with the packages required for the installation and for GRANDlib.
They are listed in the `grand-dev.yaml` file of this repository, a modified version of the
[`grand-dev.yml`](https://github.com/grand-mother/grand/blob/dev-next/env/conda/grand-dev.yml) file from
GRANDlib's `dev-next` branch. The main difference is that our file removes `c-compiler` and `make`,
which are no longer needed, and adds `zig` as a dependency.

To create the conda environment, run:
```bash
conda env create -f grand-dev.yaml
```
> [!NOTE]
> This creates a conda environment named `grand-dev`, as set by the `name` field of the
> `grand-dev.yaml` file. To use a different name, pass the `-n, --name <NAME>` option to the
> command above (see the [conda documentation](https://docs.conda.io/projects/conda/en/stable/commands/env/create.html)
> for details).

To activate the conda environment, run:
```bash
conda activate grand-dev
```
> [!TIP]
> Replace `grand-dev` with your environment's name if you chose a custom one.

### Install script

The installation relies on a Python script, which performs the following steps:

- Clone the TURTLE and GULL repositories into a temporary `build` folder. TURTLE is cloned at tag `v0.9`,
  and GULL is checked out at commit `286ace5` after cloning.
- Build the C libraries with Zig. This calls `zig build [options]`, which runs the `build.zig` build script
  and creates two static library files in the temporary `build` folder.
- Build the Python C extension by calling the `build` function defined in `build_ext.py`.
  [CFFI](https://cffi.readthedocs.io/en/stable/) generates the C source of the extension, and Zig
  preprocesses, compiles and links it, so no system C compiler is needed. The resulting dynamic library
  (`_core.abi3.so`) is installed directly in the `grand` folder of the GRANDlib root directory (see below).
- Install GRANDlib as a Python package, in editable mode.
- Clean up the build artifacts.

The script takes one positional argument: the path to your local GRANDlib directory. This path is used to
find the `grand.c` and `grand.h` files when building the Python C extension, and to install the resulting
`_core.abi3.so` into GRANDlib's `grand` source directory.

To run the install script, execute:
```bash
python install.py <PATH_TO_GRANDLIB>
```
> [!TIP]
> Remember to activate your conda environment before running this command.

By default, the script uses the `zig` found on your `PATH`, which is the one installed in the conda
environment. To use a different Zig compiler, pass its path with the `--zig <PATH_TO_ZIG>` option.
