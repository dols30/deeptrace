#!/usr/bin/env python3
"""Extract ASVspoof 2021 DF archives and create the evaluation CSV."""

import argparse
import csv
import hashlib
import json
import random
import tarfile
from pathlib import Path


ARCHIVES = [f"ASVspoof2021_DF_eval_part{i:02d}.tar.gz" for i in range(4)]


def safe_extract(archive: Path, destination: Path) -> None:
    destination = destination.resolve()
    with tarfile.open(archive, "r:gz") as stream:
        members = stream.getmembers()
        for member in members:
            target = (destination / member.name).resolve()
            if destination not in target.parents and target != destination:
                raise ValueError(f"Unsafe archive member: {member.name}")
            if not (member.isfile() or member.isdir()):
                raise ValueError(f"Unsupported archive member: {member.name}")
        stream.extractall(destination, members=members)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive_dir", type=Path)
    parser.add_argument("dataset_dir", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--parts", nargs="+", default=["00", "01", "02", "03"])
    parser.add_argument("--max-per-class", type=int)
    parser.add_argument("--seed", type=int, default=20210911)
    args = parser.parse_args()

    args.dataset_dir.mkdir(parents=True, exist_ok=True)
    selected_archives = [f"ASVspoof2021_DF_eval_part{part}.tar.gz" for part in args.parts]
    for name in [*selected_archives, "DF-keys-full.tar.gz"]:
        archive = args.archive_dir / name
        if not archive.is_file():
            raise SystemExit(f"Missing archive: {archive}")
        print(f"Extracting {archive}", flush=True)
        safe_extract(archive, args.dataset_dir)

    protocol = args.dataset_dir / "keys/DF/CM/trial_metadata.txt"
    audio_by_id = {
        path.stem: path.resolve()
        for path in args.dataset_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in {".flac", ".wav"}
    }
    rows_by_label = {0: [], 1: []}
    for line_number, line in enumerate(protocol.read_text().splitlines(), 1):
        fields = line.split()
        if len(fields) < 6 or fields[5] not in {"bonafide", "spoof"}:
            raise ValueError(f"Invalid protocol line {line_number}")
        utterance_id = fields[1]
        audio = audio_by_id.get(utterance_id)
        if audio is None:
            continue
        label = 0 if fields[5] == "bonafide" else 1
        rows_by_label[label].append((utterance_id, audio, label))

    rng = random.Random(args.seed)
    rows = []
    selected_counts = {}
    for label, candidates in rows_by_label.items():
        candidates.sort(key=lambda row: row[0])
        if args.max_per_class is not None:
            if len(candidates) < args.max_per_class:
                raise ValueError(
                    f"Only {len(candidates)} class-{label} files are available; "
                    f"requested {args.max_per_class}"
                )
            candidates = rng.sample(candidates, args.max_per_class)
        selected_counts[str(label)] = len(candidates)
        rows.extend(candidates)
    rng.shuffle(rows)
    if not rows:
        raise ValueError("No protocol entries matched the extracted audio")

    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    with args.manifest.open("w", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(["id", "path", "label"])
        writer.writerows(rows)
    metadata = {
        "dataset": "ASVspoof 2021 DF evaluation",
        "parts": args.parts,
        "seed": args.seed,
        "max_per_class": args.max_per_class,
        "selected_counts": selected_counts,
        "protocol_sha256": hashlib.sha256(protocol.read_bytes()).hexdigest(),
    }
    args.manifest.with_suffix(args.manifest.suffix + ".metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n"
    )
    print(f"Wrote {len(rows)} rows to {args.manifest}")


if __name__ == "__main__":
    main()
