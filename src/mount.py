#!/usr/bin/env python

import sys

from subprocess import run

disk = sys.argv[1]
fs_type = sys.argv[2]

run("sudo ./src/umount.sh", shell=True)

cryptpass = input("Encryption password: ").strip()

if fs_type == "ext4":
    run(f"yes '{cryptpass}' | sudo cryptsetup open {disk}2 cryptroot", shell=True)

    run("vchange -ay MyVolGrp", shell=True)

    run("mount /dev/MyVolGrp/root /mnt", shell=True)
elif fs_type == "btrfs":
    run(f"yes '{cryptpass}' | sudo cryptsetup open {disk}3 cryptroot", shell=True)
    run(f"yes '{cryptpass}' | sudo cryptsetup open {disk}2 cryptswap", shell=True)

    run("sudo mount -o compress=zstd,subvol=@ /dev/mapper/cryptroot /mnt", shell=True)
    run("sudo mount -o compress=zstd,subvol=@snapshots /dev/mapper/cryptroot /mnt/.snapshots", shell=True)
    run("sudo mount -o compress=zstd,subvol=@home /dev/mapper/cryptroot /mnt/home", shell=True)

run(f"sudo mount {disk}1 /mnt/boot/efi", shell=True)
