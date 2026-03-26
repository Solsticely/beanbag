#!/usr/bin/env bash
set -euxo pipefail

# Need (on debian):
# sudo apt-get install libguestfs-tools qemu-system-<your architecture>

MACH="$(uname -m)"

DEBIAN_VERSION_NAME='trixie'
DEBIAN_VERSION_NO=13
SSH_PORT=22222

case "$MACH" in
  aarch64)
    DEBIAN_ARCH='arm64'
    QEMU_MACH='virt'
    ;;
  *)
    DEBIAN_ARCH="$MACH"
    QEMU_MACH='pc'
    ;;
esac

if [ ! -e ./deb.qcow2 ] ; then
  if [ -e ./deb.qcow2.orig ] ; then
    printf '\033[33;1m%s\033[0m\n' "Restoring debian image!"
    cp ./deb.qcow2.orig ./deb.qcow2
  else
    printf '\033[33;1m%s\033[0m\n' "Downloading debian! This may take a while..."
    curl -L "https://cloud.debian.org/images/cloud/${DEBIAN_VERSION_NAME}/latest/debian-${DEBIAN_VERSION_NO}-genericcloud-${DEBIAN_ARCH}.qcow2" > deb.qcow2
    cp ./deb.qcow2 ./deb.qcow2.orig
  fi
fi

if [ ! -e initrd.img ] || [ ! -e vmlinuz ] ; then
  rm ./initrd.img ./vmlinuz || true

  printf '\033[33;1m%s\033[0m\n' "Extracting kernel and boot images! This may take a while..."
  eval "$(guestfish --listen)"
  guestfish --remote add-ro deb.qcow2
  guestfish --remote run
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

printf '\033[33;1mRun `ssh root@localhost -p %d`\nWhen done, run `killall qemu-system-%s`\nIf this is your first run:\n\trun `apt install openssh-server`, then\n\trun `nano /etc/sshd_config` and set `PermitRootLogin yes` & `PasswordAuthentication yes`, then\n\ton the host machine, run `cp deb.qcow2{,.orig}`\033[0m\n' "$SSH_PORT" "$MACH"

# Thanks to https://blachniet.com/posts/create-a-minimal-local-debian-vm-with-qemu/
# and https://wiki.qemu.org/Documentation/Platforms/ARM
# and https://wiki.qemu.org/Documentation/Networking#How_to_get_SSH_access_to_a_guest
# and https://translatedcode.wordpress.com/2017/07/24/installing-debian-on-qemus-64-bit-arm-virt-board/
# My system is already virtualised and doesn't support nested virtualisation, so I
# can't use -accel kvm. If you can, turn it on!
qemu-system-"$MACH"                                 \
  -kernel vmlinuz                                   \
  -initrd initrd.img                                \
  -append 'root=/dev/vda1'                          \
  -machine "$QEMU_MACH"                             \
  -cpu cortex-a53                                   \
  -drive if=none,file=deb.qcow2,format=qcow2,id=hd  \
  -device virtio-blk-pci,drive=hd                   \
  -m 512m                                           \
  -smp 4                                            \
  -nic user,hostfwd=tcp::"$SSH_PORT"-:22            \
  -chardev stdio,id=char0                           \
  -mon chardev=char0                                \
  -serial vc                                        \

# To use the terminal, replace from -chardev stdio.... onwards with:
  # -nographic                                        \
# and maybe
  # -serial mon:stdio                                 \

# To use KVM, add the following to the end:
  # -accel kvm                                        \
