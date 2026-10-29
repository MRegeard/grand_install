# GRANDlib Install: a cross-platform installer

This repository provides a single, cross-platform way to install [GRANDlib](https://github.com/grand-mother/grand).
GRANDlib official installation instruction (see the
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
- Install GRANDlib as a Python package, in editable mode, and add the GRANDlib directory to the Python path
  of the conda environment (see [Environment variables](#environment-variables)).
- Clean up the build artifacts.
- Set GRANDlib's environment variables in the conda environment (see
  [Environment variables](#environment-variables)).
- Download the GRAND data model (about 1 GB), unless it is already up to date (see [Data model](#data-model)).

> [!NOTE]
> Contrary to the official installation steps, because GULL and TURTLE are statically linked to `_core.abi3.so`,
> no compiled library files are copied to the grand `lib` directory.

The script takes one positional argument: the path to your local GRANDlib directory. This path is used to
find the `grand.c` and `grand.h` files when building the Python C extension, and to install the resulting
`_core.abi3.so` into GRANDlib's `grand` source directory.

To run the install script, execute:
```bash
python install.py <PATH_TO_GRANDLIB> [options]
```
> [!TIP]
> Remember to activate your conda environment before running this command.

The following options are available:

| Option | Description |
|---|---|
| `--zig <PATH_TO_ZIG>` | Use the Zig compiler at `<PATH_TO_ZIG>`. By default, the script uses the `zig` found on your `PATH`, which is the one installed in the conda environment. |
| `--aires <PATH_TO_AIRES_BIN>` | Set the `AIRESBINDIR` environment variable to the `bin` directory of your AIRES installation. Only needed to convert AIRES/ZHAireS simulations with `sim2root`. |
| `--no-download-data` | Do not download the GRAND data model. |
| `-h, --help` | Show the help message. |

### Environment variables

GRANDlib's official procedure sets its environment variables with `source env/setup.sh`, which exports them
in your current shell. Instead, this install script stores them in the conda environment with
`conda env config vars set`, so they are set when the environment is activated and removed when it is
deactivated. The following variables are set:

| Variable | Value | Set |
|---|---|---|
| `GRAND_ROOT` | Path to your GRANDlib directory | Always |
| `AIRESBINDIR` | Path given with `--aires` | Only with `--aires` |

The variables only take effect the next time the environment is activated, so re-activate it once after
the installation:
```bash
conda deactivate && conda activate grand-dev
```

To list or remove them, use `conda env config vars list` and `conda env config vars unset <NAME>`.

`env/setup.sh` also sets the following variables, which this procedure handles differently:

- `PYTHONPATH`: `env/setup.sh` adds the GRANDlib directory to it, which makes the top-level modules of the
  repository, such as `sim2root`, importable. The editable install only makes the `grand` package importable,
  so the install script instead adds the GRANDlib directory to the Python path of the conda environment,
  with a `grandlib_root.pth` file in its `site-packages` directory. To undo it, delete this file.
- `C_INCLUDE_PATH` and `LIBRARY_PATH`: they are only used when compiling with a system C compiler,
  so they are not needed.

> [!NOTE]
> `env/setup.sh` also adds GRANDlib's `scripts`, `examples/dataio` and `quality` directories to your `PATH`.
> This procedure does not, so run these scripts with their full path, for example
> `python $GRAND_ROOT/scripts/convert_efield2voltage.py`.

### Data model

GRANDlib needs about 1 GB of model data: antenna effective lengths, RF-chain measurements and
Galactic-noise tables. The install script downloads it by running GRANDlib's
`data/download_data_grand.py` script, which skips the download if the data is already up to date.
The data comes from a single server, `forge.in2p3.fr`. If the download fails, GRANDlib is still installed,
and you can retry later with:
```bash
python <PATH_TO_GRANDLIB>/data/download_data_grand.py
```

Use `--no-download-data` to skip this step, for example if you already have the data.

## Verifying the installation

After re-activating the environment, run the checks recommended by
[GRANDlib's documentation](https://github.com/grand-mother/grand/blob/dev-next/docs/source/installation.rst)
from your GRANDlib directory:
```bash
python -c "import grand; print(grand.GRAND_DATA_PATH)"   # the package imports
python -m grand.basis.data_model                          # the data model matches its manifest
pytest tests/ -q                                          # the full test suite
```

The full test suite has over 1300 tests and takes about 20 minutes on one core. For a quick check of the
C extension built by this procedure, run only the TURTLE and GULL tests, which take a few seconds:
```bash
pytest tests/geo/ -q
```
