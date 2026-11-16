"""Refresh the public cache with conditional requests to official sources."""

from datetime import date

from .bill_text import archive_url as text_archive_url
from .sources import (
    FISC_OPINIONS, GPO, HOUSE_SITES, HOUSE_XML, SENATE_XML, bills_from_archive, court_filings,
    fetch, house_members, senate_members,
)
from .store import now


def current_congress():
    today = date.today()
    year = today.year - int(today.year % 2 == 1 and (today.month, today.day) < (1, 3))
    return (year - 1789) // 2 + 1


def archive_url(congress, kind):
    return f"{GPO}/{congress}/{kind}/BILLSTATUS-{congress}-{kind}.zip"


def refresh_bill_text(store, congress, progress):
    first_year = 1789 + (congress - 1) * 2
    sessions = (1, 2) if date.today().year > first_year else (1,)
    errors = []
    for session in sessions:
        for kind, chamber in (("hr", "House"), ("s", "Senate")):
            url = text_archive_url(congress, session, kind)
            progress(f"Checking {chamber.lower()} bill text · session {session}…")
            try:
                archive, validators = fetch(url, store.get_setting(url))
                if archive is not None:
                    with store.connect() as db:
                        db.execute("BEGIN IMMEDIATE")
                        store.write_bill_text(db, archive)
                        store.set_setting(url, validators, db)
            except Exception as error:
                errors.append(f"{chamber} bill text, session {session} — {error}")
    return errors


def refresh(store, progress=lambda message: None):
    congress = current_congress()
    errors = []
    for cached_congress in sorted(store.cached_congresses() | {congress}, reverse=True):
        errors.extend(refresh_bill_text(store, cached_congress, progress))
    count = 0
    for kind, chamber in (("hr", "House"), ("s", "Senate")):
        url = archive_url(congress, kind)
        progress(f"Checking {chamber.lower()} bills…")
        try:
            archive, validators = fetch(url, store.get_setting(url))
            if archive is not None:
                bills = bills_from_archive(archive)
                with store.connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    new_actions = store.write_bills(db, bills, notify=True)
                    store.set_setting(url, validators, db)
                count += new_actions
        except Exception as error:
            errors.append(f"{chamber} bills — {error}")
    progress("Checking congressional directory…")
    try:
        roster, _ = fetch(HOUSE_XML)
        page, _ = fetch(HOUSE_SITES)
        members = house_members(roster, page)
        with store.connect() as db:
            store.write_members(db, members)
    except Exception as error:
        errors.append(f"House directory — {error}")
    try:
        roster, validators = fetch(SENATE_XML, store.get_setting(SENATE_XML))
        if roster is not None:
            members = senate_members(roster)
            with store.connect() as db:
                store.write_members(db, members)
                store.set_setting(SENATE_XML, validators, db)
    except Exception as error:
        errors.append(f"Senate directory — {error}")
    progress("Checking FISA Court filings…")
    try:
        page, validators = fetch(FISC_OPINIONS, store.get_setting(FISC_OPINIONS))
        if page is not None:
            filings = court_filings(page)
            with store.connect() as db:
                store.set_setting("court_filings", filings, db)
                store.set_setting(FISC_OPINIONS, validators, db)
    except Exception as error:
        errors.append(f"FISA Court filings — {error}")
    if not errors:
        store.set_setting("last_sync", now())
    return count, errors
