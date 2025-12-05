#!/usr/bin/env python3

import argparse
import os
import subprocess as sp
import re
from contextlib import contextmanager
from datetime import datetime

DEBUG = False

# Actual directory names to clone repos
OOTM_REPO_DIR = "tb-ootm"
KERNEL_REPO_DIR = "tb-kernel"

# Set required Debian environment variables
os.environ['DEBIAN_FRONTEND'] = 'noninteractive'
# These can be anything
os.environ['DEBFULLNAME'] = 'Tegra Builder'
os.environ['DEBEMAIL'] = 'tegra-builder@builder.local'

def run_cmd(cmd: list[str], **kwargs) -> sp.CompletedProcess[bytes]:
    """
    Wrapper for running shell commands
    """
    if DEBUG:
        print(f"CMD: \"{' '.join(cmd)}\"")
    return sp.run(cmd, **kwargs)

def run_capture(cmd: list[str]) -> str:
    """
    Run a command and return stdout.
    """
    completed = run_cmd(cmd, capture_output=True)
    if completed.returncode != 0:
        print(f"ERROR [{completed.returncode}]: {completed.stderr.decode('utf-8')}")
        raise sp.CalledProcessError(completed.returncode, cmd)
    return completed.stdout.decode('utf-8').strip()

def run(cmd: list[str]):
    """
    Run a command without capturing output.
    """
    run_cmd(cmd, check=True)

# Figured a chdir context manager would be a good idea for doing work in the
# repos, and I am very lazy, so I shall legally steal this code from SO.

# Source - https://stackoverflow.com/a
# Posted by cdunn2001, modified by community. See post 'Timeline' for change history
# Retrieved 2025-11-23, License - CC BY-SA 4.0

@contextmanager
def cd(newdir):
    prevdir = os.getcwd()
    os.chdir(os.path.expanduser(newdir))
    try:
        yield
    finally:
        os.chdir(prevdir)


class TegraBuilder:
    def __init__(self,
                 ootm_repo: str,
                 ootm_branch: str,
                 kernel_repo: str,
                 kernel_branch: str):
        self.ootm_repo = ootm_repo
        self.ootm_branch = ootm_branch
        self.kernel_repo = kernel_repo
        self.kernel_branch = kernel_branch

        # Cross-building is currently not supported, so assume the package arch
        # matches the host arch
        self.arch = run_capture(['dpkg', '--print-architecture'])

        self.cwd = os.getcwd()

        # Packaging fields to be set dynamically during build process
        self.release = ''
        self.tegra_branch = ''
        self.ootm_version = ''
        self.ootm_binpkgs = []
        self.kernel_binpkgs = []

    def _init_repo(self, path, repo, branch):
        if os.path.isdir(path):
            # If repo exists, just fetch instead of re-cloning
            with cd(path):
                run(['git', 'restore', '.'])
                run(['git', 'clean', '-xdf'])
                run(['git', 'fetch', repo, branch])
                run(['git', 'checkout', 'FETCH_HEAD'])
        else:
            run(['git', 'clone', repo, '-b', branch, '--single-branch', path])

    def _install_dependencies(self):
        run(['sudo', '-E', 'apt', '-y', 'update'])
        run(['sudo', '-E', 'apt', '-y', 'install',
             'git', 'build-essential', 'devscripts'])

    def _init_ootm(self):
        self.ootm_path = f"{self.cwd}/{OOTM_REPO_DIR}"
        self._init_repo(self.ootm_path, self.ootm_repo, self.ootm_branch)

    def _build_ootm(self):
        with cd(self.ootm_path):
            ootm_srcpkg = run_capture(['dpkg-parsechangelog', '-S', 'Source'])
            self.release = run_capture(['dpkg-parsechangelog', '-S', 'Distribution'])
            self.tegra_branch = ootm_srcpkg.removeprefix('tegra-oot-')

            # Update changelog. Use autoincremented version because it doesn't
            # matter, the kernel just needs a file to pull.
            run(['dch', "OOTM development build"])
            run(['dch', '-r', self.release])
            self.ootm_version = run_capture(['dpkg-parsechangelog', '-S', 'Version'])

            # Need to generate control file so apt build-dep works
            run(['fakeroot', 'debian/rules', 'debian/control'])
            run(['sudo', '-E', 'apt', '-y', 'build-dep', '.'])

            run(['fakeroot', 'debian/rules', 'clean'])
            run(['debuild', '-b', '--no-sign'])

            with open("debian/control", 'r') as f:
                pattern = re.compile(r'^Package: (.*)$', re.MULTILINE)
                self.ootm_binpkgs = pattern.findall(f.read())

            print("OOTM dkms packages built successfully.")

    def _init_kernel(self):
        self.kernel_path = f"{self.cwd}/{KERNEL_REPO_DIR}"
        self._init_repo(self.kernel_path, self.kernel_repo, self.kernel_branch)

    def _build_kernel(self):
        # Generate dkms-versions file
        with cd(self.kernel_path):
            with open("debian/debian.env", 'r') as f:
                pattern = re.compile(r'^DEBIAN=(.*)$', re.MULTILINE)
                debian_path = pattern.search(f.read())[1]
            # Start with dkms-versions from parent kernel, which we assume is debian_path minus -ppadev
            debian_parent = debian_path.removesuffix('-ppadev')
            run(['cp', f"{debian_parent}/dkms-versions", f"{debian_path}/dkms-versions"])
            for binpkg in self.ootm_binpkgs:
                bin_path = os.path.abspath(f"{self.ootm_path}/../{binpkg}_{self.ootm_version}_{self.arch}.deb")
                module_name = binpkg.removesuffix('-dkms')
                dkms_string = (f"{module_name} {self.ootm_version}"
                               + f" modulename={module_name}"
                               + f" debpath={bin_path}"
                               + f" arch={self.arch}"
                               + f" rprovides={module_name}-modules"
                               + f" rprovides={binpkg}"
                               +  " buildheaders=true"
                               +  " type=standalone")
                with open(f"{debian_path}/dkms-versions", 'a') as f:
                    f.write(dkms_string + '\n')

            # In-place sub was easier just running sed, and as previously stated, I am lazy
            run(['sed', '-i', '-E', f"s/^(BRANCHES=).*$/\\1{self.tegra_branch}/", f"{debian_path}/rules.d/{self.arch}.mk"])

            # Update changelog
            kernel_version = run_capture(['dpkg-parsechangelog', '-S', 'Version', '-l', f"{debian_path}/changelog"])
            timestamp = datetime.now().strftime("%Y%m%d%H%M")
            kernel_version = re.compile(r'-.*').sub(f"-{timestamp}.1", kernel_version)
            # If debian/changelog is tracked, assume we should use that.
            # Otherwise, use the derivative directory.
            chfile = "debian/changelog"
            if not os.path.isfile(chfile):
                chfile = f"{debian_path}/changelog"
            run(['dch', '-c', chfile, '-v', kernel_version, "Kernel development build"])
            run(['dch', '-c', chfile, '-r', self.release])

            run(['fakeroot', 'debian/rules', 'clean'])
            run(['sudo', '-E', 'apt', '-y', 'build-dep', '.'])
            run(['debuild', '-b', '--no-sign'])

            with open("debian/control", 'r') as f:
                pattern = re.compile(r'^Package: (.*)$', re.MULTILINE)
                self.kernel_binpkgs = pattern.findall(f.read())

            print("Kernel packages built successfully.")

    def build(self):
        self._install_dependencies()
        self._init_ootm()
        self._build_ootm()
        self._init_kernel()
        self._build_kernel()


def main():
    parser = argparse.ArgumentParser(
        prog='tegra-builder.py',
        description="Builds the tegra kernel with OOTM like a daily build.",
    )
    parser.add_argument('--ootm-repo',
                        help="Out-of-tree modules DKMS package repo to clone.")
    parser.add_argument('--ootm-branch',
                        help="Out-of-tree modules DKMS package repo branch to checkout.")
    parser.add_argument('--kernel-repo',
                        help="Kernel git repo to clone.")
    parser.add_argument('--kernel-branch',
                        help="Kernel git repo branch to checkout.")
    parser.add_argument('--debug', action='store_true',
                        help="Debug mode prints commands as they run.")

    args = parser.parse_args()

    global DEBUG
    DEBUG = args.debug

    TegraBuilder(args.ootm_repo, args.ootm_branch, args.kernel_repo, args.kernel_branch).build()

if __name__ == '__main__':
    main()
