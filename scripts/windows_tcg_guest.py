GUEST_SCRIPT = r'''#!/bin/bash
set -eu
work=/tmp/tcg-benchmark
rootfs=$work/root
rm -rf "$work"; mkdir -p "$rootfs"/{bin,dev,proc,sys,tmp,mnt}
cp "$(command -v busybox)" "$rootfs/bin/busybox"; chmod +x "$rootfs/bin/busybox"
cat > "$work/mono.c" <<'C'
#include <stdint.h>
#include <stdio.h>
#include <time.h>
int main(void) {
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC, &ts) != 0) return 1;
    printf("%lld\n", (long long)ts.tv_sec * 1000000000LL + ts.tv_nsec);
    return 0;
}
C
for command in sh mount mkdir dd sync echo cat cut sleep sha256sum ls dmesg mknod modprobe; do ln -sf /bin/busybox "$rootfs/bin/$command"; done
cat > "$rootfs/init" <<'INIT'
#!/bin/sh
set -eu
mount -t proc proc /proc 2>/dev/null || true
mount -t sysfs sysfs /sys 2>/dev/null || true
mount -t devtmpfs devtmpfs /dev 2>/dev/null || true
modprobe virtio_pci 2>/tmp/modprobe.log || true
modprobe virtio_blk 2>>/tmp/modprobe.log || true
modprobe crc32c_generic 2>>/tmp/modprobe.log || true
modprobe crc32c 2>>/tmp/modprobe.log || true
modprobe ext4 2>>/tmp/modprobe.log || true
for _ in $(seq 1 50); do
  [ -b /dev/vda ] && break
  sleep .1
done
mkdir -p /mnt
echo GUEST_READY
case "${SCENARIO:-smoke}" in
  smoke)
    dd if=/dev/zero of=/tmp/cpu.bin bs=1M count=64 2>/dev/null
    i=0; while [ "$i" -lt 8 ]; do busybox sha256sum /tmp/cpu.bin >/dev/null; i=$((i + 1)); done
    echo GUEST_DONE smoke
    ;;
  boot)
    echo GUEST_DONE boot
    ;;
  cpu)
    dd if=/dev/zero of=/tmp/cpu.bin bs=1M count=64 2>/dev/null
    i=0; while [ "$i" -lt 16 ]; do busybox sha256sum /tmp/cpu.bin >/dev/null; i=$((i + 1)); done
    echo GUEST_DONE cpu
    ;;
  memory)
    dd if=/dev/zero of=/tmp/memory.bin bs=1M count=128 2>/dev/null
    busybox sha256sum /tmp/memory.bin >/dev/null
    echo GUEST_DONE memory
    ;;
  storage)
    echo PHASE mount
    if ! mount -t ext4 /dev/vda /mnt 2>/tmp/mount.log; then
      echo GUEST_FAILED phase=mount
      echo DEVICES
      ls -l /dev
      echo PARTITIONS
      cat /proc/partitions
      echo MOUNT_ERROR
      cat /tmp/mount.log
      echo MODPROBE_ERROR
      cat /tmp/modprobe.log
      echo KERNEL_LOG
      dmesg | tail -n 40
      exit 21
    fi
    echo PHASE sequential-write
    write_start=$(mono_ns)
    if ! dd if=/dev/zero of=/mnt/blob bs=1M count=256 conv=fsync 2>/tmp/write.log; then
      echo GUEST_FAILED phase=write; cat /tmp/write.log; exit 22
    fi
    write_end=$(mono_ns)
    echo STORAGE_WRITE_NS=$write_start,$write_end
    echo PHASE sequential-read
    read_start=$(mono_ns)
    if ! dd if=/mnt/blob of=/dev/null bs=1M 2>/tmp/read.log; then
      echo GUEST_FAILED phase=read; cat /tmp/read.log; exit 23
    fi
    read_end=$(mono_ns)
    echo STORAGE_READ_NS=$read_start,$read_end
    sync
    echo GUEST_DONE storage
    ;;
esac
sleep 2
INIT
chmod +x "$rootfs/init"
kernel=$(ls -1 /boot/vmlinuz-* | sort | tail -n1)
kernel_version=${kernel##*/vmlinuz-}
mkdir -p "$rootfs/lib/modules/$kernel_version"
cp -a "/lib/modules/$kernel_version/." "$rootfs/lib/modules/$kernel_version/"
depmod -b "$rootfs" "$kernel_version" >/dev/null 2>&1 || true
(cd "$rootfs" && find . -print | cpio -o -H newc 2>/dev/null | gzip -1 > "$work/initramfs.gz")
disk="${DISK_PATH:-$work/disk.raw}"
if [ ! -f "$disk" ]; then truncate -s 2G "$disk"; fi
if [ "$SCENARIO" = storage ]; then
  if ! mke2fs -t ext4 -F "$disk" >/tmp/host-mkfs.log 2>&1; then
    echo GUEST_FAILED phase=host-mkfs
    cat /tmp/host-mkfs.log
    exit 20
  fi
fi
qemu-system-x86_64 -accel tcg,thread=multi -M q35 -m "$GUEST_MEMORY_MIB" -smp "$GUEST_CPU" \
  -kernel "$kernel" -initrd "$work/initramfs.gz" -append "console=ttyS0 init=/init SCENARIO=$SCENARIO" \
  -drive "file=$disk,if=none,id=benchmark-disk,format=raw,cache=none,aio=native" \
  -device virtio-blk-pci,drive=benchmark-disk -display none \
  -serial file:/tmp/tcg-serial.log -monitor none >/tmp/qemu.stderr 2>&1 &
qemu_pid=$!
for _ in $(seq 1 3600); do
  if grep -Eq "GUEST_(DONE|FAILED) $SCENARIO|GUEST_FAILED phase=" /tmp/tcg-serial.log 2>/dev/null; then break; fi
  sleep .1
cat /tmp/tcg-serial.log || true
cat /tmp/qemu.stderr || true
kill "$qemu_pid" 2>/dev/null || true; wait "$qemu_pid" 2>/dev/null || true
'''
