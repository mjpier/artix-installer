#!/usr/bin/env python

import sys

from subprocess import run, check_output

def make_password(s):
    print(s, end="")

    while True:
        password = input("Password: ").strip()
        second = input("Repeat password: ").strip()

        if password == second and len(password) > 1:
            return password

print("\nInstalling Artix Linux...\n")

# Check boot mode
if len(check_output("ls /sys/firmware/efi/efivars", shell=True)) < 8:
    print("\nNot booted in UEFI mode. Aborting...")
    sys.exit()

# Load keymap
keymap = input("\nKeymap (us): ").strip()
if len(keymap) < 2:
    keymap = "us"
run(f"loadkeys {keymap}", shell=True)

# Partition disk
disk = sys.argv[1]
part1 = f"{disk}1"
part2 = f"{disk}2"
part3 = f"{disk}3"
if "nvme" in disk:
    part1 = f"{disk}p1"
    part2 = f"{disk}p2"
    part3 = f"{disk}p3"
run("yes | pacman -Sy --needed parted", shell=True)

erase = input(f"\nWould you like to erase the contents of {disk}? (y/N): ").strip()
if erase == "y":
    run(f"dd bs=4096 if=/dev/zero iflag=nocache of={disk} oflag=direct status=progress", shell=True)

swap_size = input("\nSize of swap partition (4GiB): ").strip()
swap_size = "".join([x for x in swap_size if x.isdigit()])
if swap_size == "":
    swap_size = "4"
swap_size = int(swap_size)

fs_type = input(
    "\nDesired filesystem:"
    "\n(1)  ext4"
    "\n(2)  ZFS"
    "\n(3+) Btrfs\n: "
).strip()
root_part = part2
fs_pkgs = ""
if fs_type == "1":
    fs_type = "ext4"
    fs_pkgs = "cryptsetup lvm2 lvm2-openrc"
elif fs_type == "2":
    fs_type = "zfs"
    fs_pkgs = "zfs-dkms"
    run("curl -L https://archzfs.com/archzfs.gpg |  pacman-key -a -", shell=True)
    run("curl -L https://git.io/JtQpl | xargs -i{} pacman-key --lsign-key {}", shell=True)
    run("curl -L https://git.io/JtQp4 > /etc/pacman.d/mirrorlist-archzfs", shell=True)
    run("printf '\n\n[archzfs]\nInclude = /etc/pacman.d/mirrorlist-archzfs\n' >> /etc/pacman.conf", shell=True)
    run("yes | pacman -Sy zfs-dkms", shell=True)
    run("modprobe zfs", shell=True)
else:
    fs_type = "btrfs"
    root_part = part3
    fs_pkgs = "cryptsetup btrfs-progs"

run("./src/umount.sh > /dev/null 2>&1", shell=True)

run(f"""parted -s {disk} mktable gpt \\
mkpart artix_boot fat32 0% 1GiB \\
set 1 esp on \\
align-check optimal 1""", shell=True)

if fs_type == "ext4":
    run(f"""parted -s {disk} \\
mkpart artix_root ext4 1GiB 100% \\
set 2 lvm on \\
align-check optimal 2""", shell=True)
elif fs_type == "zfs":
    run(f"""parted -s {disk} \\
mkpart artix_root 1GiB 100% \\
align-check optimal 2""", shell=True)
elif fs_type == "btrfs":
    run(f"""parted -s {disk} \\
mkpart artix_swap linux-swap 1GiB {1+swap_size}GiB \\
mkpart artix_root btrfs {1+swap_size}GiB 100% \\
set 2 swap on \\
align-check optimal 2 \\
align-check optimal 3""", shell=True)

choice = input("\nWould you like to manually edit partitions? (y/N): ").strip()
if choice == "y":
    run(f"cfdisk {disk}", shell=True)

run(f"sfdisk -l {disk}", shell=True)

# Setup encrypted partitions
if fs_type == "ext4" or fs_type == "btrfs":
    cryptpass = make_password("\nSetting encryption password...\n")

    luks_options = input("\nAdditional cryptsetup options (e.g. `--type luks1`): ").strip()

    run(f"echo '{cryptpass}' | cryptsetup -q luksFormat {luks_options} {root_part}", shell=True)
    run(f"yes '{cryptpass}' | cryptsetup open {root_part} cryptroot", shell=True)

if fs_type == "btrfs":
    run(f"echo '{cryptpass}' | cryptsetup -q luksFormat {part2}", shell=True)
    run(f"yes '{cryptpass}' | cryptsetup open {part2} cryptswap", shell=True)

# Format partitions and mount
run(f"mkfs.fat -F 32 {part1}", shell=True)

if fs_type == "ext4":
    # Setup LVM
    run("pvcreate /dev/mapper/cryptroot", shell=True)
    run("vgcreate MyVolGrp /dev/mapper/cryptroot", shell=True)
    run(f"lvcreate -L {swap_size}G MyVolGrp -n swap", shell=True)
    run("lvcreate -l 100%FREE MyVolGrp -n root", shell=True)

    run("mkswap /dev/MyVolGrp/swap", shell=True)
    run("mkfs.ext4 /dev/MyVolGrp/root", shell=True)

    run("mount /dev/MyVolGrp/root /mnt", shell=True)
elif fs_type == "zfs":
    root_id = ""
    by_ids = check_output("find /dev/disk/by-id -type l -printf '%p %l\n'", shell=True).strip().decode("utf-8").split("\n")
    for byid in by_ids:
        if byid.endswith(root_part[5:]) and byid.startswith("/dev/disk/by-id/wwn"):
            root_id = byid[:byid.find(" ")]
            break
    else:
        for byid in by_ids:
            if byid.endswith(root_part[5:]) and byid.startswith("/dev/disk/by-id/ata"):
                root_id = byid[:byid.find(" ")]
                break
        else:
            print(f"\nSomething went wrong. No by-id file found for {root_part}.")
            sys.exit()

    run(f"""zpool create -o ashift=12 \\
-O mountpoint=none \\
-O canmount=off \\
-O devices=off \\
-R /mnt \\
-O compression=lz4 \\
-O encryption=on \\
-O keyformat=passphrase \\
-O keylocation=prompt \\
zroot /dev/disk/by-id/{root_id}""", shell=True)

    # Create datasets
    run("zfs create -o mountpoint=none zroot/ROOT", shell=True)
    run("zfs create -o mountpoint=none zroot/data -o canmount=noauto", shell=True)
    run("zfs create -o mountpoint=/ zroot/ROOT/default", shell=True)
    run("zfs create -o mountpoint=/home zroot/data/home", shell=True)

    # Mount
    run("zpool export zroot", shell=True)
    run("zpool import -d /dev/disk/by-id -R /mnt zroot -N", shell=True)
    run("zfs load-key zroot", shell=True)
    run("zfs mount zroot/ROOT/default", shell=True)
    run("zfs mount -a", shell=True)

    # Misc
    run("zpool set bootfs=zroot/ROOT/default zroot", shell=True)
    run("zpool set cachefile=/etc/zfs/zpool.cache zroot", shell=True)
    run("mkdir /mnt/etc", shell=True)
    run("mkdir /mnt/etc/zfs", shell=True)
    run("cp /etc/zfs/zpool.cache /mnt/etc/zfs/", shell=True)

    # Create swap
    run(f"""zfs create -V {swap_size} \\
-b $(getconf PAGESIZE) \\
-o compression=zle \\
-o logbias=throughput \\
-o sync=standard \\
-o primarycache=metadata \\
-o secondarycache=none \\
-o com.sum=auto-snapshot=false zroot/swap""", shell=True)
    run("mkswap -f /dev/zvol/zroot/swap", shell=True)
elif fs_type == "btrfs":
    run("mkswap /dev/mapper/cryptswap", shell=True)
    run("mkfs.btrfs /dev/mapper/cryptroot", shell=True)

    # Create subvolumes
    run("mount /dev/mapper/cryptroot /mnt", shell=True)
    run("btrfs subvolume create /mnt/@", shell=True)
    run("btrfs subvolume create /mnt/@snapshots", shell=True)
    run("btrfs subvolume create /mnt/@home", shell=True)
    run("umount -R /mnt", shell=True)

    # Mount subvolumes
    run("mount -o compress=zstd,subvol=@ /dev/mapper/cryptroot /mnt", shell=True)
    run("mkdir /mnt/.snapshots", shell=True)
    run("mkdir /mnt/home", shell=True)
    run("mount -o compress=zstd,subvol=@snapshots /dev/mapper/cryptroot /mnt/.snapshots", shell=True)
    run("mount -o compress=zstd,subvol=@home /dev/mapper/cryptroot /mnt/home", shell=True)

run("mkdir -p /mnt/boot/efi", shell=True)
run(f"mount {part1} /mnt/boot/efi", shell=True)

# Install base system and kernel
run(f"basestrap /mnt base base-devel openrc {fs_pkgs} python neovim parted", shell=True)
run("basestrap /mnt linux linux-firmware linux-headers", shell=True)
run("fstabgen -U /mnt >> /mnt/etc/fstab", shell=True)
