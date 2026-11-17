"""Official agency records that provide context or a way to participate."""

from datetime import date

RULEMAKING = {
    "title": "DMCA §1201 circumvention exemptions",
    "docket": "U.S. Copyright Office docket 2026-4 · Regulations.gov COLC-2026-0100",
    "notice": "https://www.govinfo.gov/content/pkg/FR-2026-10-28/pdf/2026-21939.pdf",
    "docket_url": "https://www.regulations.gov/docket/COLC-2026-0100",
    "submit": "https://www.copyright.gov/1201/2027/comment-submission/",
    "rounds": (
        ("Initial comments supporting or providing evidence on proposed exemptions", "2026-12-07"),
        ("Response comments opposing proposed exemptions", "2027-02-22"),
        ("Reply comments supporting or providing evidence on proposals", "2027-03-22"),
    ),
}

AGENCY_OPINIONS = (
    ("2025-09-12", "March 2025 Section 702 certification opinion", "https://www.odni.gov/3555/pr-29-25/"),
    ("2025-08-19", "February and April 2025 Section 702 Certification D opinions", "https://www.odni.gov/3546/pr-23-25/"),
    ("2025-07-11", "January 2025 FISC opinion on FISA Title I", "https://www.odni.gov/1265/pr-14-25/"),
    ("2025-05-02", "September 2024 FISC opinion on Section 702 certification amendments", "https://www.odni.gov/1517/pr-09-25/"),
)


def comment_window(today=None):
    today = today or date.today()
    return next((entry for entry in RULEMAKING["rounds"] if date.fromisoformat(entry[1]) >= today), None)
