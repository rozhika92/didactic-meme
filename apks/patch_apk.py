#!/usr/bin/env python3
"""
Patch Facebook/Meta APKs to fix DalvikInternals crash on emulators.
Requires: apktool, apksigner (or jarsigner), zipalign, keytool

Usage:
  python3 patch_apk.py <input.apk>
  
Produces: <input>_patched.apk
"""
import subprocess
import sys
import os
import tempfile
import shutil


def run(cmd, **kw):
    print(f"  $ {cmd}")
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        print(f"    STDERR: {r.stderr.strip()}")
    return r


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 patch_apk.py <input.apk>")
        sys.exit(1)

    apk = os.path.abspath(sys.argv[1])
    base = os.path.splitext(os.path.basename(apk))[0]
    out = os.path.join(os.path.dirname(apk), f"{base}_patched.apk")

    with tempfile.TemporaryDirectory() as tmp:
        decoded = os.path.join(tmp, "decoded")
        unsigned = os.path.join(tmp, "unsigned.apk")
        keystore = os.path.join(tmp, "debug.keystore")

        # Step 1: Decode (skip resources — they cause errors on FB APKs)
        print("[1/5] Decoding APK...")
        r = run(f'apktool d -f -r "{apk}" -o "{decoded}"')
        if r.returncode != 0:
            sys.exit(1)

        # Step 2: Patch DalvikInternals.smali
        smali = os.path.join(
            decoded, "smali/com/facebook/common/dextricks/DalvikInternals.smali"
        )
        if not os.path.exists(smali):
            print("ERROR: DalvikInternals.smali not found")
            sys.exit(1)

        print("[2/5] Patching DalvikInternals...")
        with open(smali, "r") as f:
            content = f.read()

        # Patch A: Make integrateWithLibSigChain a no-op
        content = content.replace(
            ".method public static synchronized native integrateWithLibSigChain(I)V\n.end method",
            ".method public static synchronized integrateWithLibSigChain(I)V\n"
            "    .locals 0\n"
            "    return-void\n"
            ".end method",
        )

        # Patch B: Make mprotect methods no-ops
        for sig in [
            "mprotect(JJI)I",
            "mprotectExecAll([Ljava/lang/String;)V",
            "mprotectExecCode()V",
        ]:
            old = f".method public static native {sig}\n.end method"
            if sig.endswith(")I"):
                new = (
                    f".method public static {sig}\n"
                    "    .locals 1\n"
                    "    const/4 v0, 0x0\n"
                    "    return v0\n"
                    ".end method"
                )
            else:
                new = (
                    f".method public static {sig}\n"
                    "    .locals 0\n"
                    "    return-void\n"
                    ".end method"
                )
            content = content.replace(old, new)

        # Patch C: Replace <clinit> with safe version (try-catch everything)
        clinit_start = content.find(
            ".method public static constructor <clinit>()V"
        )
        clinit_end = content.find(".end method", clinit_start) + len(".end method")

        safe_clinit = """.method public static constructor <clinit>()V
    .locals 3
    const/4 v2, 0x1
    :try_start_all
    const-string v0, "dextricks"
    invoke-static {v0}, Lcom/facebook/soloader/SoLoader;->loadLibrary(Ljava/lang/String;)Z
    invoke-static {}, Lcom/facebook/common/dextricks/DalvikInternals;->ignoreSIGPIPE()V
    sget-boolean v0, LX/0oz;->A00:Z
    invoke-static {v0}, Lcom/facebook/common/dextricks/DalvikInternals;->setIsArt(Z)V
    sget v1, Landroid/os/Build$VERSION;->SDK_INT:I
    invoke-static {v1}, Lcom/facebook/common/dextricks/DalvikInternals;->setSdkInt(I)V
    :try_end_all
    .catch Ljava/lang/Throwable; {:try_start_all .. :try_end_all} :catch_all
    goto :goto_done
    :catch_all
    move-exception v0
    :goto_done
    sput-boolean v2, Lcom/facebook/common/dextricks/DalvikInternals;->INITED:Z
    invoke-static {}, LX/001;->A0x()Ljava/util/ArrayList;
    move-result-object v0
    sput-object v0, Lcom/facebook/common/dextricks/DalvikInternals;->sDexBaseNames:Ljava/util/List;
    return-void
.end method"""

        content = content[:clinit_start] + safe_clinit + content[clinit_end:]

        with open(smali, "w") as f:
            f.write(content)
        print("    Done: integrateWithLibSigChain + mprotect disabled")

        # Step 3: Rebuild
        print("[3/5] Rebuilding APK...")
        r = run(f'apktool b "{decoded}" -o "{unsigned}"')
        if r.returncode != 0:
            sys.exit(1)

        # Step 4: Generate key and sign
        print("[4/5] Signing APK...")
        run(
            f'keytool -genkey -v -keystore "{keystore}" -storepass android '
            f'-alias debug -keypass android -keyalg RSA -keysize 2048 '
            f'-validity 10000 -dname "CN=Debug, O=Debug, C=US"'
        )
        run(
            f'jarsigner -sigalg SHA256withRSA -digestalg SHA-256 '
            f'-keystore "{keystore}" -storepass android -keypass android '
            f'"{unsigned}" debug'
        )

        # Step 5: Zipalign
        print("[5/5] Zipaligning...")
        r = run(f'zipalign -f 4 "{unsigned}" "{out}"')
        if r.returncode != 0:
            shutil.copy2(unsigned, out)

        print(f"\nPatched APK: {out}")
        print(f"Install: adb install {out}")


if __name__ == "__main__":
    main()
