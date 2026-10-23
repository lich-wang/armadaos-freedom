#!/usr/bin/env python3
"""Pack a TB710FU kShimC boot image: stock Android kernel + kShimC + one Linux entry.

The unit's own boot_a dump provides the Android (GKI) kernel and the boot v4
header.  The DualBootKernelPatcher packer lays out
  [Image-00 Android (base)] [shim] [Image-01 Linux] [Image-02 DTB] [Image-03 initramfs]
gzip-compresses the packed kernel, and the result is rebuilt into boot.img with
an AVB hash footer signed by the AOSP testkey_rsa4096 (same salt, rollback
index and properties as the original footer), which this unit's vbmeta_a
chains for boot.

The DTB must carry /chosen/kshim,initrd-entry = <3> when --initrd is given.
Runs on Linux (the packer is a Linux binary); nothing here touches a device.
"""
import argparse
import gzip
import hashlib
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile

PAGE = 4096
PART_SIZE = 96 * 1024 * 1024


def avb_info(avbtool, path):
    return subprocess.check_output([sys.executable, avbtool, "info_image", "--image", path],
                                   text=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--boot", required=True, help="boot_a dump of the unit (boot v4, raw GKI)")
    ap.add_argument("--runtime", required=True, help="4 MiB kShimC.bin")
    ap.add_argument("--linux", required=True, help="raw arm64 Image")
    ap.add_argument("--dtb", required=True, help="DTB for the Linux entry")
    ap.add_argument("--initrd", help="initramfs blob (Image-03)")
    ap.add_argument("--packer", required=True, help="DualBootKernelPatcher packer binary")
    ap.add_argument("--avbtool", required=True, help="AOSP external/avb avbtool.py")
    ap.add_argument("--key", required=True, help="AOSP test/data/testkey_rsa4096.pem")
    ap.add_argument("--out", required=True, help="output boot.img")
    ap.add_argument("--android-name", default="HyperOS")
    ap.add_argument("--linux-name", default="Linux")
    ap.add_argument("--default", choices=["android", "linux"], default="android",
                    help="entry booted when the countdown expires")
    ap.add_argument("--timeout-ms", type=int, default=8000)
    ap.add_argument("--no-gzip", action="store_true",
                    help="keep the packed kernel raw (only fits without a large Linux Image)")
    a = ap.parse_args()

    boot = open(a.boot, "rb").read()
    if boot[:8] != b"ANDROID!":
        sys.exit("--boot is not an Android boot image")
    kernel_size, ramdisk_size = struct.unpack_from("<II", boot, 8)
    header_version = struct.unpack_from("<I", boot, 40)[0]
    sig_size = struct.unpack_from("<I", boot, 1580)[0]
    if header_version != 4 or ramdisk_size != 0 or sig_size != 0:
        sys.exit("expected boot v4 without ramdisk/signature (got v%d, ramdisk %d, sig %d)"
                 % (header_version, ramdisk_size, sig_size))
    kernel = boot[PAGE:PAGE + kernel_size]
    if kernel[56:60] != b"ARM\x64":
        sys.exit("the base kernel must be a raw arm64 Image")
    if open(a.linux, "rb").read(64)[56:60] != b"ARM\x64":
        sys.exit("--linux must be a raw arm64 Image")

    work = tempfile.mkdtemp(prefix="tb710fu-pack.")
    try:
        open(os.path.join(work, "Image.android"), "wb").write(kernel)
        shutil.copy(a.runtime, os.path.join(work, "kShimC.bin"))
        shutil.copy(a.linux, os.path.join(work, "Image.linux"))
        shutil.copy(a.dtb, os.path.join(work, "linux.dtb"))
        cfg = ["[Pack]", "Shim=kShimC.bin", "Output=PackedKernel",
               "Default=" + ("Image-01" if a.default == "linux" else "Image-00"),
               "Timeout=%d" % a.timeout_ms, "",
               "[Image-00]", "Name=" + a.android_name, "Path=Image.android", "Type=Linux",
               "BaseImage=true", "Align=21", "",
               "[Image-01]", "Name=" + a.linux_name, "Path=Image.linux", "Type=Linux",
               "BaseImage=false", "Align=21", "DeviceTreeBlob=Image-02", "",
               "[Image-02]", "Name=" + a.linux_name + " DTB", "Path=linux.dtb", "Type=DTB",
               "BaseImage=false", ""]
        if a.initrd:
            shutil.copy(a.initrd, os.path.join(work, "initrd.img"))
            cfg += ["[Image-03]", "Name=Initramfs", "Path=initrd.img", "Type=Blob",
                    "BaseImage=false", "Align=16", ""]
        cfg += ["[Manifest]", "Type=Manifest", ""]
        open(os.path.join(work, "build.cfg"), "w").write("\n".join(cfg))
        subprocess.run([os.path.abspath(a.packer), "build.cfg"], cwd=work, check=True)
        packed = open(os.path.join(work, "PackedKernel"), "rb").read()
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if packed[56:60] != b"ARM\x64":
        sys.exit("packer output is not an arm64 Image")
    payload = packed if a.no_gzip else gzip.compress(packed, compresslevel=9, mtime=0)

    # boot.img: original header page with the new kernel_size, kernel padded to PAGE
    hdr = bytearray(boot[:PAGE])
    struct.pack_into("<I", hdr, 8, len(payload))
    body = bytes(hdr) + payload + b"\0" * (-len(payload) % PAGE)
    if len(body) >= PART_SIZE - 1024 * 1024:
        sys.exit("boot image too large for the 96 MiB partition")
    open(a.out, "wb").write(body)

    # AVB hash footer, signed like the original one
    info = avb_info(a.avbtool, a.boot)
    salt = re.search(r"Salt:\s+([0-9a-f]+)", info).group(1)
    rollback = re.search(r"Rollback Index:\s+(\d+)", info).group(1)
    cmd = [sys.executable, a.avbtool, "add_hash_footer", "--image", a.out,
           "--partition_name", "boot", "--partition_size", str(PART_SIZE),
           "--key", a.key, "--algorithm", "SHA256_RSA4096",
           "--rollback_index", rollback, "--salt", salt]
    seen = set()
    for prop in re.findall(r"Prop: (\S+) -> '([^']*)'", info):
        if prop not in seen:
            seen.add(prop)
            cmd += ["--prop", "%s:%s" % prop]
    subprocess.run(cmd, check=True)

    print("packed  %d bytes, payload %d bytes (%s)"
          % (len(packed), len(payload), "raw" if a.no_gzip else "gzip"))
    print("%s sha256 %s" % (a.out, hashlib.sha256(open(a.out, "rb").read()).hexdigest()))


if __name__ == "__main__":
    main()
