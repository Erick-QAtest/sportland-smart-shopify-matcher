from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import shutil


ENV_KEYS = {
    "SPORTLAND_BACKUP_MIRROR_DIR",
    "SPORTLAND_BACKUP_REQUIRE_MIRROR",
    "SPORTLAND_BACKUP_MIRROR_RETENTION_DAYS",
}


def discover_roots() -> list[tuple[str, Path]]:
    home = Path.home()
    candidates: list[tuple[str, Path]] = []

    icloud = home / "Library/Mobile Documents/com~apple~CloudDocs"
    if icloud.exists():
        candidates.append(("icloud", icloud))

    cloud_storage = home / "Library/CloudStorage"
    if cloud_storage.exists():
        for path in sorted(cloud_storage.iterdir()):
            if not path.is_dir():
                continue
            name = path.name.lower()
            if name.startswith("googledrive-"):
                candidates.append(("google-drive", path))
            elif name.startswith("dropbox"):
                candidates.append(("dropbox", path))
            elif name.startswith("onedrive-"):
                candidates.append(("onedrive", path))

    volumes = Path("/Volumes")
    if volumes.exists():
        for path in sorted(volumes.iterdir()):
            if path.is_dir() and not path.name.startswith("."):
                candidates.append(("volume", path))

    return candidates


def _quote_env(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def update_env(env_path: Path, mirror_dir: Path, retention_days: int) -> Path:
    existing = (
        env_path.read_text(encoding="utf-8").splitlines()
        if env_path.exists()
        else []
    )

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = env_path.with_name(f"{env_path.name}.backup.mirror.{stamp}")
    if env_path.exists():
        shutil.copy2(env_path, backup_path)

    kept: list[str] = []
    for line in existing:
        stripped = line.strip()
        key = stripped.split("=", 1)[0].strip() if "=" in stripped else ""
        if key in ENV_KEYS:
            continue
        kept.append(line)

    while kept and kept[-1] == "":
        kept.pop()

    kept.extend([
        "",
        "# Sportland Smart external backup mirror",
        f"SPORTLAND_BACKUP_MIRROR_DIR={_quote_env(str(mirror_dir))}",
        "SPORTLAND_BACKUP_REQUIRE_MIRROR=true",
        f"SPORTLAND_BACKUP_MIRROR_RETENTION_DAYS={retention_days}",
        "",
    ])
    env_path.write_text("\n".join(kept), encoding="utf-8")
    return backup_path


def write_probe(target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    probe = target / ".sportland_mirror_probe"
    payload = "sportland-smart-mirror-ok\n"
    probe.write_text(payload, encoding="utf-8")
    if probe.read_text(encoding="utf-8") != payload:
        raise RuntimeError("No se pudo verificar escritura/lectura en el mirror.")
    probe.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Configure Sportland external PostgreSQL backup mirror"
    )
    parser.add_argument("--discover", action="store_true")
    parser.add_argument(
        "--provider",
        choices=["icloud", "google-drive", "dropbox", "onedrive", "volume"],
    )
    parser.add_argument("--path")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--retention-days", type=int, default=30)
    args = parser.parse_args()

    candidates = discover_roots()

    if args.discover:
        if not candidates:
            print("No external/synced storage candidates were detected.")
            return 1
        print("Detected mirror candidates:")
        for idx, (provider, path) in enumerate(candidates, start=1):
            print(f"  {idx}. {provider}: {path}")
        return 0

    if args.retention_days < 1:
        print("ERROR: --retention-days must be >= 1")
        return 2

    if args.path:
        base = Path(args.path).expanduser().resolve()
    elif args.provider:
        matches = [path for provider, path in candidates if provider == args.provider]
        if not matches:
            print(f"ERROR: no {args.provider} location detected.")
            print("Run: python run_ops_mirror_setup.py --discover")
            return 2
        if len(matches) > 1:
            print(f"ERROR: multiple {args.provider} locations detected:")
            for path in matches:
                print(f"  - {path}")
            print("Use --path with the exact location you want.")
            return 2
        base = matches[0].resolve()
    else:
        print("Choose --provider or --path.")
        print("First run: python run_ops_mirror_setup.py --discover")
        return 2

    mirror_dir = base / "SportlandSmartBackups" / "PostgreSQL"
    write_probe(mirror_dir)

    project_root = Path(args.project_root).resolve()
    try:
        mirror_dir.resolve().relative_to(project_root)
    except ValueError:
        pass
    else:
        print("ERROR: mirror path cannot be inside the project.")
        return 2

    env_path = project_root / ".env"
    backup_path = update_env(
        env_path,
        mirror_dir,
        args.retention_days,
    )

    print("Sportland external backup mirror configured.")
    print(f"Mirror: {mirror_dir}")
    print("Policy: REQUIRED")
    print(f"Mirror retention: {args.retention_days} days")
    print(f".env backup: {backup_path}")
    print("")
    print("Next:")
    print("  python run_ops_backup.py")
    print("  python run_ops_health.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
