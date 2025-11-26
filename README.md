# tegra-kernel-builder

This is a convenience sccript to automate the process of building the Tegra
OOTM and daily-build kernel locally. When complete, the resulting debs will be
in the current working directory when running the script.

## Prerequisites

- Push your copies of the OOTM and kernel to repos that the script can clone
- Run the script on an arm64 device running Ubuntu
  - Designed with Tegra devices in mind

## Usage

Run `./tegra-kernel-builder.py -h` for usage info.
