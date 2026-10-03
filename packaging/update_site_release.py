"""Writes site/release.json from a published GitHub release, so the website's download
button always points at the newest stable installer.

    python packaging/update_site_release.py <tag> [output path]

Needs the GitHub CLI (`gh`) logged in or GH_TOKEN set. Used by the "Update website release
info" workflow; can also be run by hand after publishing a release.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = "anant-agarwal12/top-display"
DEFAULT_OUT = Path(__file__).resolve().parent.parent / "site" / "release.json"


def gh(*args: str) -> str:
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def build(tag: str) -> dict:
    release = json.loads(gh("release", "view", tag, "--repo", REPO, "--json",
                            "tagName,publishedAt,isPrerelease,isDraft,assets"))
    if release["isPrerelease"] or release["isDraft"]:
        raise SystemExit(f"{tag} is a pre-release or draft: the website only shows stable releases.")

    installer = next((a for a in release["assets"] if re.fullmatch(r"TopDisplay-Setup-.+\.exe", a["name"])), None)
    checksum = next((a for a in release["assets"] if a["name"] == (installer or {}).get("name", "") + ".sha256"), None)
    if not installer or not checksum:
        raise SystemExit(f"{tag} has no TopDisplay-Setup-*.exe with a matching .sha256 asset.")

    sha_text = gh("release", "download", tag, "--repo", REPO, "--pattern", checksum["name"], "--output", "-")
    sha = sha_text.split()[0].lower()
    if not re.fullmatch(r"[0-9a-f]{64}", sha):
        raise SystemExit(f"{checksum['name']} does not start with a SHA-256: {sha_text[:80]!r}")

    return {
        "version": release["tagName"].lstrip("v"),
        "date": release["publishedAt"][:10],
        "size_mb": f"{installer['size'] / (1024 * 1024):.1f}",
        "sha256": sha,
        "url": installer["url"],
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_OUT
    data = build(sys.argv[1])
    out.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out}: {data}")
