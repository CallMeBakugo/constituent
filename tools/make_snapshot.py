"""Rebuild the bundled snapshot from official downloads or captured source files."""

import argparse
import gzip
import json
from datetime import date
from pathlib import Path

from constituent.sources import (
    FISC_OPINIONS, HOUSE_SITES, HOUSE_XML, SENATE_XML, bills_from_archive, court_filings,
    fetch, house_members, senate_members,
)
from constituent.sync import archive_url


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--congress", required=True, type=int)
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--from-directory", type=Path, help="Use named copies of the official feeds.")
    args = parser.parse_args()
    target = Path(__file__).resolve().parents[1] / "src/constituent/snapshot.json.gz"
    validators = {}

    def read(url, name):
        if args.from_directory:
            return (args.from_directory / name).read_bytes()
        data, validators[url] = fetch(url)
        return data

    bills = [
        bill for kind in ("hr", "s")
        for bill in bills_from_archive(read(archive_url(args.congress, kind), f"{kind}.zip"))
    ]
    members = house_members(read(HOUSE_XML, "house.xml"), read(HOUSE_SITES, "house.html"))
    members += senate_members(read(SENATE_XML, "senate.xml"))
    filings = court_filings(read(FISC_OPINIONS, "fisc.html"))
    with target.open("wb") as raw, gzip.GzipFile(fileobj=raw, filename="", mode="wb", mtime=0) as output:
        payload = {"date": args.date, "bills": bills, "members": members, "filings": filings, "validators": validators}
        output.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode())
    print(f"Wrote {len(bills):,} bills and {len(members):,} office records to {target.name}.")


if __name__ == "__main__":
    main()
