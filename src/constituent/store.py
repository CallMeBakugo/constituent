"""SQLite cache, local profile, watchlists, and civic diary."""

import gzip
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from importlib.resources import files
from pathlib import Path

HUBS = (
    ("Chat Control", "Encryption, age verification & online safety",
     "client-side scanning, encryption backdoor, end-to-end encryption, age verification, "
     "kids online safety, children harmed by AI technology, stop csam, earn it act"),
    ("DMCA Bullshit", "Copyright enforcement & digital repair rights",
     "digital millennium copyright act, section 1201, 17 u.s.c. 1201, takedown abuse, "
     "foreign anti-digital piracy, copyright infringement, farm freedom to repair"),
    ("FISA Court Rulings", "FISA legislation & surveillance authorities",
     "foreign intelligence surveillance act, foreign intelligence surveillance court, section 702, fisa amendments act"),
)
STATES = """AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH
NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY AS DC GU MP PR VI""".split()
STATUSES = ("Proposed", "In Committee", "On Floor", "Passed", "Failed", "Enacted")


def local_path(variable, fallback):
    base = Path(os.environ.get(variable) or Path.home() / fallback)
    path = base / "constituent"
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


def now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def fts_terms(phrases):
    # Hubs use comma-separated literal phrases, with no raw FTS operators.
    terms = (phrase.strip() for phrase in phrases.split(","))
    return " OR ".join(
        '"' + phrase.replace('"', '""') + '"' for phrase in terms
        if any(character.isalnum() for character in phrase)
    )


class Store:
    def __init__(self, path):
        self.path = Path(path)
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS hubs (
                    id INTEGER PRIMARY KEY, name TEXT UNIQUE COLLATE NOCASE,
                    description TEXT NOT NULL, phrases TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS bills (
                    key TEXT PRIMARY KEY, date TEXT NOT NULL, status TEXT NOT NULL,
                    data TEXT NOT NULL, unread INTEGER NOT NULL DEFAULT 0
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS bill_search USING fts5(
                    key UNINDEXED, title, details, tokenize='unicode61'
                );
                CREATE TABLE IF NOT EXISTS members (
                    id TEXT PRIMARY KEY, state TEXT NOT NULL, chamber TEXT NOT NULL,
                    district TEXT NOT NULL, data TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS diary (
                    id INTEGER PRIMARY KEY, created TEXT NOT NULL, bill TEXT NOT NULL,
                    official TEXT NOT NULL, stance TEXT NOT NULL, status TEXT NOT NULL
                );
            """)
            db.execute("BEGIN IMMEDIATE")
            if self.get_setting("snapshot", db=db) is None:
                resource = files("constituent").joinpath("snapshot.json.gz")
                with resource.open("rb") as raw, gzip.GzipFile(fileobj=raw) as compressed:
                    seed = json.load(compressed)
                db.executemany("INSERT INTO hubs(name,description,phrases) VALUES (?,?,?)", HUBS)
                self.write_bills(db, seed["bills"])
                self.write_members(db, seed["members"])
                self.set_setting("snapshot", seed["date"], db)
                self.set_setting("court_filings", seed.get("filings", []), db)
                for url, validators in seed.get("validators", {}).items():
                    self.set_setting(url, validators, db)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def get_setting(self, key, default=None, *, db=None):
        if db is None:
            with self.connect() as connection:
                return self.get_setting(key, default, db=connection)
        row = db.execute("SELECT data FROM settings WHERE key=?", (key,)).fetchone()
        return json.loads(row["data"]) if row else default

    def set_setting(self, key, value, db=None):
        if db is None:
            with self.connect() as connection:
                self.set_setting(key, value, connection)
            return
        db.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (key, json.dumps(value)))

    def hubs(self):
        with self.connect() as db:
            return list(db.execute("SELECT * FROM hubs ORDER BY id"))

    def add_hub(self, name, phrases):
        if not name.strip() or not fts_terms(phrases):
            raise ValueError("Enter a name and at least one keyword or phrase.")
        with self.connect() as db:
            cursor = db.execute(
                "INSERT INTO hubs(name,description,phrases) VALUES (?,?,?)",
                (name.strip(), "Custom watchlist", phrases.strip()),
            )
            return cursor.lastrowid

    def bills(self, phrases, search="", status="", *, db=None):
        if db is None:
            with self.connect() as connection:
                return self.bills(phrases, search, status, db=connection)
        hub_query = fts_terms(phrases)
        search_query = fts_terms(search)
        query = f"({hub_query}) AND ({search_query})" if search_query else hub_query
        rows = db.execute("""
            SELECT b.data, b.unread FROM bill_search AS f
            JOIN bills AS b ON f.key=b.key
            WHERE bill_search MATCH ? AND (?='' OR b.status=?)
            ORDER BY b.date DESC, b.key
        """, (query, status, status))
        return [dict(json.loads(row["data"]), unread=bool(row["unread"])) for row in rows]

    def write_bills(self, db, bills, notify=False):
        # Build the FTS rowid map once. FTS term queries cannot index an UNINDEXED key.
        search_rows = dict(db.execute("SELECT key, rowid FROM bill_search"))
        previous = dict(db.execute("SELECT key, data FROM bills")) if notify else {}
        pending = set()
        for bill in bills:
            key = bill["key"]
            data = json.dumps(bill, ensure_ascii=False, sort_keys=True)
            cached = previous.get(key)
            if cached == data:
                continue
            if notify and not cached and bill["actions"]:
                pending.add(key)
            if cached:
                old_actions = {(a["date"], a["text"]) for a in json.loads(cached)["actions"]}
                if any((a["date"], a["text"]) not in old_actions for a in bill["actions"]):
                    pending.add(key)
            db.execute("""
                INSERT INTO bills(key,date,status,data) VALUES (?,?,?,?)
                ON CONFLICT(key) DO UPDATE SET date=excluded.date,
                    status=excluded.status, data=excluded.data
            """, (key, bill["date"], bill["status"], data))
            if key in search_rows:
                db.execute("DELETE FROM bill_search WHERE rowid=?", (search_rows[key],))
            alternate_id = f"{bill['kind']} {bill['number']}"
            title = " ".join([bill["bill_id"], alternate_id, bill["title"], *bill["titles"]])
            details = "\n".join([bill["summary"], *bill["subjects"]])
            db.execute("INSERT INTO bill_search VALUES (?,?,?)", (key, title, details))
        if not notify or not pending:
            return 0
        tracked = {
            row[0]
            for hub in db.execute("SELECT phrases FROM hubs")
            for row in db.execute("SELECT key FROM bill_search WHERE bill_search MATCH ?", (fts_terms(hub[0]),))
        }
        updated = pending & tracked
        db.executemany("UPDATE bills SET unread=1 WHERE key=?", ((key,) for key in updated))
        return len(updated)

    def mark_read(self, key):
        with self.connect() as db:
            db.execute("UPDATE bills SET unread=0 WHERE key=?", (key,))

    def write_members(self, db, members):
        chambers = {(member["chamber"],) for member in members}
        db.executemany("DELETE FROM members WHERE chamber=?", chambers)
        db.executemany(
            "INSERT INTO members VALUES (?,?,?,?,?)",
            ((m["id"], m["state"], m["chamber"], m["district"], json.dumps(m)) for m in members),
        )

    def members(self, state=""):
        with self.connect() as db:
            return sorted(
                (json.loads(row[0]) for row in db.execute(
                    "SELECT data FROM members WHERE ?='' OR state=?", (state, state)
                )),
                key=lambda m: (m["state"], m["chamber"] != "Senate", m["district"], m["name"]),
            )

    def representatives(self, profile):
        return [
            member for member in self.members(profile["state"])
            if member["chamber"] == "Senate" or member["district"] == profile["district"]
        ]

    def member_roles(self, member_id):
        found = {}
        with self.connect() as db:
            tracked = {
                row[0]
                for hub in db.execute("SELECT phrases FROM hubs")
                for row in db.execute("SELECT key FROM bill_search WHERE bill_search MATCH ?", (fts_terms(hub[0]),))
            }
            for row in db.execute("SELECT key,data FROM bills ORDER BY date DESC"):
                if row["key"] not in tracked:
                    continue
                bill = json.loads(row["data"])
                for role, field in (("Sponsor", "sponsors"), ("Cosponsor", "cosponsors")):
                    matches = [person for person in bill[field] if person["id"] == member_id]
                    if matches:
                        found[bill["key"]] = (bill, f"{role} (withdrawn)" if matches[0].get("withdrawn") else role)
        return list(found.values())

    def diary(self):
        with self.connect() as db:
            return list(db.execute("SELECT * FROM diary ORDER BY id DESC"))

    def log(self, bill, official, stance, status):
        with self.connect() as db:
            return db.execute(
                "INSERT INTO diary(created,bill,official,stance,status) VALUES (?,?,?,?,?)",
                (now(), bill, official, stance, status),
            ).lastrowid

    def mark_sent(self, entry):
        with self.connect() as db:
            db.execute("UPDATE diary SET status='Marked sent' WHERE id=?", (entry,))
