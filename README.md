# tegra-kernel-builder

This is a convenience sccript to automate the process of building the Tegra
OOTM and daily-build kernel locally. When complete, the resulting debs will be
in the current working directory when running the script.

## Prerequisites

- Kernel must be based on top of a daily kernel so it supports building all
  OOTM packages from a single source package.
  - Jammy: `https://git.launchpad.net/~ubuntu-tegra/+git/kernel-recipe recipe-pkg-nvidia-tegra-igx-next`
  - Noble: `https://git.launchpad.net/~ubuntu-tegra/+git/kernel-recipe noble/recipe-pkg-nvidia-tegra-next`
- OOTM must be based on top of the DKMS source repo.
  - Jammy: `https://git.launchpad.net/~ubuntu-tegra/+git/tegra-oot jetson/jammy-prep`
  - Noble: `https://git.launchpad.net/~ubuntu-tegra/+git/tegra-oot jetson/noble-prep`
- Push your copies of the OOTM and kernel to repos that the script can clone
- Run the script on an arm64 device running Ubuntu
  - Designed with Tegra devices in mind

## Usage

Run `./tegra-kernel-builder.py -h` for usage info.
