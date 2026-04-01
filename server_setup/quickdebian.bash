#!/usr/bin/env bash
set -euxo pipefail

# Need (on debian):
# sudo apt-get install libguestfs-tools qemu-system-<your architecture>

MACH="$(uname -m)"

DEBIAN_VERSION_NAME='trixie'
DEBIAN_VERSION_NO=13
MAX_DISK_SIZE=15G

declare -a ARGS
ARGS=(
  -nic "user,hostfwd=tcp::20022-:22,hostfwd=tcp::20186-:186,hostfwd=udp::26001-:60001"
)

case "$MACH" in
  aarch64)
    DEBIAN_ARCH='arm64'
    QEMU_MACH='virt'
    QEMU_CPU='cortex-a53'
    QEMU_USE_INITRD=1
    APPEND_CMD='console=ttyAMA0'
    ;;
  x86_64)
    QEMU_USE_INITRD=0
    DEBIAN_ARCH='amd64'
    QEMU_MACH='q35'
    QEMU_CPU='qemu64'
    ;;
  *)
    QEMU_USE_INITRD=0
    DEBIAN_ARCH="$MACH"
    QEMU_MACH='pc'
    QEMU_CPU='host'
    ;;
esac

# Try to detect whether we have KVM available
QEMU_EMULATOR=tcg
set +e
timeout -k .5 .5s qemu-system-"$MACH" -accel kvm -M "$QEMU_MACH" -nographic
KVM_ERR="$?"
set -e
if [ "$KVM_ERR" -eq 124 ] ; then
  # KVM is available!
  # QEMU_CPU=host
  QEMU_EMULATOR=kvm
fi

declare -a ARGS
ARGS+=(
  -machine "$QEMU_MACH"
  -cpu "$QEMU_CPU"
  -drive "if=none,file=deb.qcow2,format=qcow2,id=hd"
  -device "virtio-blk-pci,drive=hd"
  -m 512m
  -smp 4
  -accel "$QEMU_EMULATOR"
)

if [ ! -e ./deb.qcow2 ] ; then
  if [ -e ./deb.qcow2.orig ] ; then
    printf '\033[33;1m%s\033[0m\n' "Restoring debian image!"
    cp ./deb.qcow2.orig ./deb.qcow2
  else
    printf '\033[33;1m%s\033[0m\n' "Downloading debian! This may take a while..."
    curl -L "https://cloud.debian.org/images/cloud/${DEBIAN_VERSION_NAME}/latest/debian-${DEBIAN_VERSION_NO}-nocloud-${DEBIAN_ARCH}.qcow2" > deb.qcow2.orig

    # Thanks to https://edafe.de/2025/02/shrink-optimise-and-expand-an-existing-qcow2-image/
    # Increase main partition size (images come with 4GiB I believe)
    printf '\033[33;1mCreating new %s disk!\033[0m\n' "$MAX_DISK_SIZE"
    qemu-img create -f qcow2 -o cluster_size=2M ./deb.qcow2 "$MAX_DISK_SIZE"

    printf '\033[33;1m%s\033[0m\n' "Balooning debian size! This may take a while..."
    virt-resize --expand /dev/sda1 ./deb.qcow2.orig ./deb.qcow2

    printf '\033[33;1m%s\033[0m\n' "Configuring image! This may take a while..."
    virt-customize -a deb.qcow2               \
      --install openssh-server                \
      --root-password password:root           \
      --upload ./sshd_config:/etc/ssh/sshd_config

    cp ./deb.qcow2 ./deb.qcow2.orig
  fi
fi

# Extract initrd & kernel on platforms that don't have consistent boot
if [ "$QEMU_USE_INITRD" -eq 1 ] ; then
  ARGS+=(
    -kernel vmlinuz
    -initrd initrd.img
    -append "root=/dev/vda1 ro $APPEND_CMD"
  )
  if [ ! -e initrd.img ] || [ ! -e vmlinuz ] ; then
    rm ./initrd.img ./vmlinuz || true

    printf '\033[33;1m%s\033[0m\n' "Extracting kernel and boot images! This may take a while..."
    eval "$(guestfish --listen)"
    guestfish --remote add-ro deb.qcow2
    guestfish --remotve run
    guestfish --remote mount /dev/sda1 /

    LS_BOOT="$(guestfish --remote ls /boot)"
    VMLINUZ_PATH="/boot/$(printf '%s' "$LS_BOOT" | grep vmlinuz- | head -1)"
    printf '\033[33;1mVMLINUZ path: %s\033[0m\n' "$VMLINUZ_PATH"
    INITRD_PATH="/boot/$(printf '%s' "$LS_BOOT" | grep initrd.img- | head -1)"
    printf '\033[33;1mINITRD path: %s\033[0m\n' "$INITRD_PATH"

    printf '\033[33;1m%s\033[0m\n' "Downloading VMLINUZ"
    guestfish --remote download "$VMLINUZ_PATH" ./vmlinuz
    printf '\033[33;1m%s\033[0m\n' "Downloading INITRD"
    guestfish --remote download "$INITRD_PATH" ./initrd.img

    printf '\033[33;1m%s\033[0m\n' "DONE!"
    guestfish --remote exit
  fi
fi


# shellcheck disable=SC2016
printf '\033[33;1mRun `ssh root@localhost -p <selected ssh port>`\nWhen done, run `killall qemu-system-%s`\033[0m\n' "$MACH"

# Thanks to https://blachniet.com/posts/create-a-minimal-local-debian-vm-with-qemu/
# and https://wiki.qemu.org/Documentation/Platforms/ARM
# and https://wiki.qemu.org/Documentation/Networking#How_to_get_SSH_access_to_a_guest
# and https://translatedcode.wordpress.com/2017/07/24/installing-debian-on-qemus-64-bit-arm-virt-board/
# and https://trainwit.ch/blog/qemu-serial-defaults/
qemu-system-"$MACH"                                 \
  "${ARGS[@]}"                                      \
  -serial stdio                                     \
  -display none                                     \

# To disable ^C from quitting QEMU, replace -serial stdio with:
  # -serial mon:stdio                                 \

# To use the GUI:
# 1. change -display none or -nographic with one of:
  # -display gtk                                      \
  # -display sdl                                      \
# 2. change -serial stdio with all of:
  # -serial vc                                        \
  # -mon chardev=char0                                \
  # -chardev stdio,id=char0                           \

# To disable the GUI and simplify the serial console output,
# replace -chardev ..., -mon ..., and -serial ... with:
  # -nographic                                        \

reset
