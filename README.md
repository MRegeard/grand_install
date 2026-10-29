# GRANDlib Install: a Unified External Installation procedure

This repository provides a unique cross-plateform procedure to install [GRANDlib](https://github.com/grand-mother/grand).
Currently, the official installation procedure
(see: [installation documentation](https://github.com/grand-mother/grand/blob/dev-next/docs/source/installation.rst) --
on HEAD branch `dev-next`) only support Linux x86-64.

GRANDlib depends on two C library ([TURTLE](https://github.com/niess/turtle) for topography and [GULL](https://github.com/niess/gull)
for geomagnetic field). Both these library needs to be compiled and linked to the GRANDlib C--Python extension. This step is the
culprit when it comes to cross-plateform compilation. This procedure rely on the [Zig](https://ziglang.org/)
compiler ability to natively compile C code to any target architecture and operating system.

## Pre-requisite and recommandation

GRANDlib will be installed in a conda environment (or venv). Therefore, a up-to-date conda installation
is required.

To install GRANDlib as a Python package inside the conda environment, the install script needs a `pyproject.toml` file.
GRANDlib provides such a file in its `dev-next` (and derived `dev-next-*`) branch. We therefore recommand to checkout to
the `dev-next` branch to simplify the installtion process. If the current branch of the provided GRANDlib direcory does not
contains a `pyproject.toml` file, the install script will fallback to the `pyproject.toml` file of this project.

> [!NOTE]
> While the authors of this repository will try their best to keep this file in sync with the
> GRANDlib (`dev-next` branch) one, it cannot be guaranteed.

## Installation

### Conda environment

We first need to create a conda environment with the packages required for the installation and for
GRANDlib. These are specified in the `grand-dev.yaml` file, which is a modified version of the
[`grand-dev.yml`](https://github.com/grand-mother/grand/blob/dev-next/env/conda/grand-dev.yml) file of
`grand-mother/grand@dev-next` branch. The main difference between the two files is that the former
removes `c-compiler` and `make`, which are not needed anymore, while adding `zig` as a dependency.

Creating the conda environment can be done via the following command:
```bash
conda env create -f grand-dev.yaml
```
> [!NOTE]
> This will create a conda environment named `grand-dev`, given by the name field of the
> `grand-dev.yaml` file. A custom name can be assigned by passing the `-n, --name <NAME>`
> option to the previous command
> (check [conda documentation](https://docs.conda.io/projects/conda/en/stable/commands/env/create.html)
> for more).

To activate the conda environment, run the following command:
```bash
conda activate grand-dev
```
> [!TIP]
> Change `grand-dev` to the relevant name if a custom environment name was provided.

### Install script

The installation process rely on a python script, which preforms the following:

- Clone the TURTLE and GULL repository into a temporary `build` folder. TURTLE clone is done at the
specific tag `v0.9`, while GULL is checkout at commit `286ace5` after cloning.
- Build the C library with zig. This calls `zig build [options]` which run the build script `build.zig`,
creating two static library file in the temporary build folder.
- Build the C--Python extension with [CFFI](https://cffi.readthedocs.io/en/stable/),
calling the `build` function defined in `build_ext.py`. The resulting dynamic library (`_core.abi3.so`)
is directly installed in the grand folder of the GRANDlib root directory (see below).
- Install GRANDlib as a python package.
- Cleanup build artifact.

The python script requires one positional argument: the path to the GRANDlib local directory. This
path is used to recover the `grand.c` and `grand.h` file when building the C-Python extension, as
well as when installing the resulting `_core.abi3.so` into the GRANDlib `grand` source directory.

To run the install script, execute the following command:
```bash
python install.py <PATH_TO_GRANDLIB>
```
> [!TIP]
> Do not forget to activate your grand environment before running this command.

A path to a specific zig compiler can be pass to the install script via the `--zig <PATH_TO_ZIG>` option.








