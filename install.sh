#!/bin/sh -e
#
# A simple installer for Artix Linux
#
# Copyright (c) 2022 Maxwell Anderson
#
# This file is part of artix-installer.
#
# artix-installer is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# artix-installer is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with artix-installer. If not, see <https://www.gnu.org/licenses/>.

confirm_password() {
	stty -echo
	until [ "$pass1" = "$pass2" ] && [ "$pass2" ]; do
		printf "%s: " "$1" >&2 && read -r pass1 && printf "\n" >&2
		printf "confirm %s: " "$1" >&2 && read -r pass2 && printf "\n" >&2
	done
	stty echo
	echo "$pass2"
}

# Load keymap
sudo loadkeys us

# Check boot mode
[ ! -d /sys/firmware/efi ] && printf "Not booted in UEFI mode. Aborting..." && exit 1

# Choose MY_INIT
until [ "$MY_INIT" = "openrc" ] || [ "$MY_INIT" = "dinit" ]; do
	printf "Init system (openrc/dinit): " && read -r MY_INIT
	[ ! "$MY_INIT" ] && MY_INIT="openrc"
done

# Choose disk
while :; do
	sudo fdisk -l
	printf "\nDisk to install to (e.g. /dev/sda): " && read -r MY_DISK
	[ -b "$MY_DISK" ] && break
done

PART1="$MY_DISK"1
PART2="$MY_DISK"2
PART3="$MY_DISK"3
case "$MY_DISK" in
*"nvme"*)
	PART1="$MY_DISK"p1
	PART2="$MY_DISK"p2
	PART3="$MY_DISK"p3
	;;
esac

# Swap size
until (echo "$SWAP_SIZE" | grep -Eq "^[0-9]+$") && [ "$SWAP_SIZE" -gt 0 ] && [ "$SWAP_SIZE" -lt 97 ]; do
	printf "Size of swap partition in GiB (4): " && read -r SWAP_SIZE
	[ ! "$SWAP_SIZE" ] && SWAP_SIZE=4
done

# Choose filesystem
until [ "$MY_FS" = "btrfs" ] || [ "$MY_FS" = "ext4" ]; do
	printf "Filesystem (btrfs/ext4): " && read -r MY_FS
	[ ! "$MY_FS" ] && MY_FS="btrfs"
done

ROOT_PART=$PART3
[ "$MY_FS" = "ext4" ] && ROOT_PART=$PART2

# Encrypt or not
printf "Encrypt? (y/N): " && read -r ENCRYPTED
[ ! "$ENCRYPTED" ] && ENCRYPTED="n"

MY_ROOT="/dev/mapper/root"
MY_SWAP="/dev/mapper/swap"
if [ $ENCRYPTED = "y" ]; then
	CRYPTPASS=$(confirm_password "encryption password")
else
	MY_ROOT=$PART3
	MY_SWAP=$PART2
	[ "$MY_FS" = "ext4" ] && MY_ROOT=$PART2
fi
[ $MY_FS = "ext4" ] && MY_SWAP="/dev/MyVolGrp/swap"

# Timezone
until [ -f /usr/share/zoneinfo/"$REGION_CITY" ]; do
	printf "Region/City (e.g. 'America/Denver'): " && read -r REGION_CITY
	[ ! "$REGION_CITY" ] && REGION_CITY="America/Denver"
done

# Host
while :; do
	printf "Hostname: " && read -r MY_HOSTNAME
	[ "$MY_HOSTNAME" ] && break
done

# Users
ROOT_PASSWORD=$(confirm_password "root password")

installvars() {
	echo MY_INIT="$MY_INIT" MY_DISK="$MY_DISK" PART1="$PART1" PART2="$PART2" PART3="$PART3" \
		SWAP_SIZE="$SWAP_SIZE" MY_FS="$MY_FS" ROOT_PART="$ROOT_PART" ENCRYPTED="$ENCRYPTED" MY_ROOT="$MY_ROOT" MY_SWAP="$MY_SWAP" \
		REGION_CITY="$REGION_CITY" MY_HOSTNAME="$MY_HOSTNAME" \
		CRYPTPASS="$CRYPTPASS" ROOT_PASSWORD="$ROOT_PASSWORD"
}

printf "\nDone with configuration. Installing...\n\n"

# Install
sudo "$(installvars)" sh src/installer.sh

# Chroot
sudo cp src/iamchroot.sh /mnt/root/ &&
	sudo "$(installvars)" artix-chroot /mnt /bin/bash -c 'sh /root/iamchroot.sh; rm /root/iamchroot.sh; exit' &&
	printf '\nYou may now poweroff.\n'
