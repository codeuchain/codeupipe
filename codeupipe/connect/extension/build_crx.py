#!/usr/bin/env python3
"""
build_crx.py — Build a CRX3-format Chrome extension from a directory.

CRX3 format:
    [4 bytes] "Cr24" magic
    [4 bytes] version = 3 (uint32 LE)
    [4 bytes] header_size (uint32 LE)
    [header_size bytes] CrxFileHeader protobuf
    [rest] ZIP payload

The protobuf schema for CrxFileHeader:

    message CrxFileHeader {
        message AsymmetricKeyProof {
            bytes public_key = 1;
            bytes signature = 2;
        }
        repeated AsymmetricKeyProof sha256_with_rsa = 2;
    }

We hand-encode the protobuf to avoid any external dependency.

Usage (CLI):
    python3 build_crx.py <extension_dir> [--out <output.crx>] [--key <private_key.pem>]

Usage (library):
    from build_crx import build_crx
    crx_bytes = build_crx(Path("my_extension/"))
    Path("output.crx").write_bytes(crx_bytes)

Zero external dependencies — stdlib only.
"""
from __future__ import annotations

import hashlib
import io
import os
import struct
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Optional, Tuple

# ── Protobuf hand-encoding ──────────────────────────────────────────

def _encode_varint(value: int) -> bytes:
    """Encode an unsigned integer as a protobuf varint."""
    parts = []
    while value > 0x7F:
        parts.append((value & 0x7F) | 0x80)
        value >>= 7
    parts.append(value & 0x7F)
    return bytes(parts)


def _encode_length_delimited(field_number: int, data: bytes) -> bytes:
    """Encode a length-delimited protobuf field."""
    tag = (field_number << 3) | 2  # wire type 2 = length-delimited
    return _encode_varint(tag) + _encode_varint(len(data)) + data


def _encode_crx_file_header(public_key_der: bytes, signature: bytes) -> bytes:
    """
    Encode CrxFileHeader protobuf.

    CrxFileHeader.sha256_with_rsa (field 2) is an AsymmetricKeyProof:
        AsymmetricKeyProof.public_key (field 1) = public_key_der
        AsymmetricKeyProof.signature  (field 2) = signature
    """
    # Build the inner AsymmetricKeyProof message
    proof = (
        _encode_length_delimited(1, public_key_der)
        + _encode_length_delimited(2, signature)
    )
    # Wrap in CrxFileHeader.sha256_with_rsa (field 2)
    return _encode_length_delimited(2, proof)


# ── RSA key management ──────────────────────────────────────────────

def _generate_rsa_key(key_path: Path) -> None:
    """Generate a 2048-bit RSA private key using openssl."""
    subprocess.run(
        ["openssl", "genrsa", "-out", str(key_path), "2048"],
        check=True,
        capture_output=True,
    )


def _get_public_key_der(key_path: Path) -> bytes:
    """Extract DER-encoded public key from a PEM private key."""
    r = subprocess.run(
        ["openssl", "rsa", "-in", str(key_path), "-pubout", "-outform", "DER"],
        check=True,
        capture_output=True,
    )
    return r.stdout


def _sign_data(key_path: Path, data: bytes) -> bytes:
    """Sign data with SHA256-RSA using openssl."""
    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as tf:
        tf.write(data)
        tf.flush()
        data_path = tf.name

    try:
        sig_path = data_path + ".sig"
        subprocess.run(
            [
                "openssl", "dgst", "-sha256", "-sign", str(key_path),
                "-out", sig_path, data_path,
            ],
            check=True,
            capture_output=True,
        )
        sig = Path(sig_path).read_bytes()
        return sig
    finally:
        for p in (data_path, data_path + ".sig"):
            try:
                os.unlink(p)
            except OSError:
                pass


# ── ZIP builder ─────────────────────────────────────────────────────

def _build_zip(extension_dir: Path, manifest_override: Optional[Path] = None) -> bytes:
    """
    Create a ZIP archive of the extension directory.

    If manifest_override is provided, use that file as manifest.json
    in the ZIP instead of the one in extension_dir.

    Excludes:
      - Python files (.py), hidden files, __pycache__, node_modules
      - STORE_LISTING.md (metadata, not runtime)
      - manifest.android.json (variant, not runtime)
      - platform/ subdirectory (SPA deployment files, not extension code)
    """
    # Directories to skip entirely (not part of the extension runtime)
    _SKIP_DIRS = {"__pycache__", "node_modules", "platform"}

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(extension_dir):
            # Skip hidden dirs and excluded directories
            root_path = Path(root)
            parts = root_path.relative_to(extension_dir).parts
            if any(p.startswith(".") or p in _SKIP_DIRS for p in parts):
                continue

            for fname in sorted(files):
                fpath = root_path / fname
                arcname = str(fpath.relative_to(extension_dir))

                # Skip build artifacts and non-extension files
                if fname.startswith(".") or fname.endswith(".py"):
                    continue
                if fname == "STORE_LISTING.md":
                    continue
                # Skip manifest variants (only manifest.json is the runtime manifest)
                if fname.startswith("manifest.") and fname != "manifest.json":
                    continue

                # Use override manifest if specified
                if arcname == "manifest.json" and manifest_override:
                    zf.write(manifest_override, "manifest.json")
                    continue

                zf.write(fpath, arcname)

    return buf.getvalue()


# ── CRX3 assembly ───────────────────────────────────────────────────

def build_crx(
    extension_dir: Path,
    key_path: Optional[Path] = None,
    manifest_override: Optional[Path] = None,
) -> bytes:
    """
    Build a CRX3 file from an extension directory.

    Args:
        extension_dir: Path to the unpacked extension directory.
        key_path: Path to RSA private key PEM. If None, generates a
                  temporary key (extension ID will change each build).
        manifest_override: Optional path to a manifest.json to use
                          instead of the one in extension_dir.

    Returns:
        The complete CRX3 file as bytes.
    """
    temp_key = False
    if key_path is None:
        fd, tmp = tempfile.mkstemp(suffix=".pem")
        os.close(fd)
        key_path = Path(tmp)
        _generate_rsa_key(key_path)
        temp_key = True

    try:
        # 1. Build ZIP payload
        zip_data = _build_zip(extension_dir, manifest_override)

        # 2. Get public key
        pub_der = _get_public_key_der(key_path)

        # 3. Build the signed data blob:
        #    CRX3 signs: "CRX3 SignedData\x00" + uint32_le(0) + zip_data
        #    But Chrome actually signs a different structure.
        #    The signed_header_data contains the SHA-256 of the CRX ID.
        #
        #    Simplified: Chrome signs the concatenation of:
        #       b"CRX3 SignedData\x00"
        #       + uint32_le(len(signed_header_data))
        #       + signed_header_data
        #       + zip_data
        #
        #    signed_header_data is a protobuf CrxFileHeader.SignedHeaderData
        #    containing the crx_id (SHA-256 of the public key, first 16 bytes).

        crx_id = hashlib.sha256(pub_der).digest()[:16]
        # SignedHeaderData protobuf: field 1 (bytes) = crx_id
        signed_header_data = _encode_length_delimited(1, crx_id)

        # Build the data to sign
        sign_input = (
            b"CRX3 SignedData\x00"
            + struct.pack("<I", len(signed_header_data))
            + signed_header_data
            + zip_data
        )

        # 4. Sign
        signature = _sign_data(key_path, sign_input)

        # 5. Build CrxFileHeader protobuf
        #    field 2 = sha256_with_rsa (AsymmetricKeyProof)
        #    field 10000 = signed_header_data (bytes)
        header_proto = (
            _encode_crx_file_header(pub_der, signature)
            + _encode_length_delimited(10000, signed_header_data)
        )

        # 6. Assemble CRX3
        crx = (
            b"Cr24"                                  # magic
            + struct.pack("<I", 3)                    # version
            + struct.pack("<I", len(header_proto))    # header size
            + header_proto                            # CrxFileHeader
            + zip_data                                # ZIP payload
        )

        return crx

    finally:
        if temp_key:
            try:
                key_path.unlink()
            except OSError:
                pass


def extension_id_from_key(key_path: Path) -> str:
    """
    Compute the Chrome extension ID from an RSA key file.

    The extension ID is the first 32 hex chars of SHA-256(public_key_der),
    mapped through a-p (instead of 0-f).
    """
    pub_der = _get_public_key_der(key_path)
    digest = hashlib.sha256(pub_der).hexdigest()[:32]
    # Chrome uses a-p alphabet instead of 0-9a-f
    return "".join(chr(ord("a") + int(c, 16)) for c in digest)


# ── CLI ─────────────────────────────────────────────────────────────

def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Build a CRX3 Chrome extension from a directory.",
    )
    parser.add_argument(
        "extension_dir",
        type=Path,
        help="Path to the unpacked extension directory.",
    )
    parser.add_argument(
        "--out", "-o",
        type=Path,
        default=None,
        help="Output CRX file path. Defaults to <extension_dir>.crx.",
    )
    parser.add_argument(
        "--key", "-k",
        type=Path,
        default=None,
        help="RSA private key PEM. If omitted, generates a temporary key.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Override manifest.json (e.g. manifest.android.json).",
    )

    args = parser.parse_args()

    if not args.extension_dir.is_dir():
        print(f"Error: {args.extension_dir} is not a directory", file=sys.stderr)
        return 1

    out_path = args.out or args.extension_dir.with_suffix(".crx")

    print(f"Building CRX3 from {args.extension_dir}")
    if args.manifest:
        print(f"  Manifest override: {args.manifest}")
    if args.key:
        print(f"  Signing key: {args.key}")
    else:
        print("  Signing key: <temporary>")

    crx_bytes = build_crx(
        args.extension_dir,
        key_path=args.key,
        manifest_override=args.manifest,
    )

    out_path.write_bytes(crx_bytes)
    size_kb = len(crx_bytes) / 1024
    print(f"  Output: {out_path} ({size_kb:.1f} KB)")

    if args.key:
        ext_id = extension_id_from_key(args.key)
        print(f"  Extension ID: {ext_id}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
