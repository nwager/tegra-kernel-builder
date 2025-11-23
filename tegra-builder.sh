#!/bin/bash
#
# Builds the tegra kernel with OOTM like a daily build.
#

set -e

TOPDIR="$(realpath $(dirname $0))"

KERNEL_REPO=$TOPDIR/kernel-recipe
KERNEL_BRANCH=temp
OOTM_REPO=$TOPDIR/tegra-oot
OOTM_BRANCH=temp

export DEBIAN_FRONTEND=noninteractive
export DEBFULLNAME="Tegra Builder"
export DEBEMAIL="tegra-builder@builder.local"

ARCH=arm64

# Install dependencies
sudo apt -y install git build-essential devscripts

# Start OOTM

cd $OOTM_REPO
git checkout $OOTM_BRANCH

ootm_srcpkg="$(dpkg-parsechangelog -SSource)"
ootm_branch=${ootm_srcpkg#tegra-oot-}

# Just use the autoincremented version, doesn't really matter
dch "OOTM development build"
dch -r "$(dpkg-parsechangelog -SDistribution)"
ootm_version="$(dpkg-parsechangelog -SVersion)"

# Need to generate control file so apt build-dep works
fakeroot debian/rules debian/control

ootm_bin_names="$(sed -n 's/^Package: //p' debian/control)"

sudo apt -y build-dep .
fakeroot debian/rules clean

debuild -b --no-sign

echo "OOTM dkms packages built successfully"

# End OOTM

# Start kernel

cd $KERNEL_REPO
git checkout $KERNEL_BRANCH

# Generate dkms-versions
. debian/debian.env
cp debian.nvidia-tegra/dkms-versions $DEBIAN/dkms-versions
for b in $ootm_bin_names
do
	modulename=${b%-dkms}
	dkms_string="$modulename $ootm_version"
	dkms_string+=" modulename=$modulename"
	dkms_string+=" debpath=$(realpath $OOTM_REPO/../${b}_${ootm_version}_${ARCH}.deb)"
	dkms_string+=" arch=$ARCH"
	dkms_string+=" rprovides=$modulename-modules"
	dkms_string+=" rprovides=$b"
	dkms_string+=" buildheaders=true"
	dkms_string+=" type=standalone"

	echo "$dkms_string" >> $DEBIAN/dkms-versions
done

# Build the correct OOTM branch
sed -i -E "s/BRANCHES=.*/BRANCHES=$ootm_branch/" $DEBIAN/rules.d/$ARCH.mk

kver="$(dpkg-parsechangelog -SVersion | sed 's/-.*//')"
abi="$(date +"%Y%m%d%H%M" --utc).1"
dch -v "$kver-$abi" "Kernel development build"
dch -r "$(dpkg-parsechangelog -SDistribution)"

fakeroot debian/rules clean
sudo apt -y build-dep .

debuild -b --no-sign

echo "Kernel packages built successfully"

# End kernel
