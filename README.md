# Constituent

**Public alpha** · Linux desktop · Android ARM64 · MIT

Constituent tracks U.S. federal bills and prepares constituent letters. It opens offline with 16,732 House and Senate bills from the 119th Congress, a 539-office congressional directory, and recent Foreign Intelligence Surveillance Court filings. The bundled records were retrieved on November 16, 2026.

![Constituent in dark mode showing the Chat Control hub](docs/constituent-dark.png)

## Install and run

Requires Linux, Python 3.12 or newer, and a desktop session. Install the local wheel with [pipx](https://pipx.pypa.io/). pipx installs PySide6 and its Qt runtime with the app.

```sh
pipx install ./constituent-2.0.0-py3-none-any.whl
constituent
```

Dark mode is the default. Use **Switch to light mode** in the sidebar to change it. Constituent remembers your choice across launches.

With a system tray available, minimizing or closing the window keeps Constituent in the tray and its refresh schedule stays active. Click the tray icon or the desktop launcher to bring the window back. To exit, right-click the tray icon and choose **Quit Constituent**.

Start with `constituent --offline` to skip automatic refresh. The **Refresh** button still works in this mode. For source development, extract the source archive and run `pipx install .` from its root, or run `PYTHONPATH=src python -m constituent --offline` with PySide6 already installed.

## Track a bill and contact an office

1. Open **Chat Control**, **DMCA Bullshit**, or **FISA Court Rulings**, or create a hub from comma-separated search phrases. Use the status filter or search inside a hub. Edit a hub with **Edit hub**. Searches rank matches in titles, summaries, and subject tags above matches that only appear in the full bill text. Excerpts link to the published version and show whether it is current or earlier. Turn on **Latest published text only** to exclude older text matches.
2. Select **Watch** to add a bill to your watchlist. Open **What changed** to see new official actions on bills matched by a hub or saved to your watchlist. Watches, activity, and older Congress records are stored locally.
3. Save your name, mailing address, state, and U.S. House district in **My profile**. The House.gov lookup opens separately if you need your district. Constituent matches the saved state and district against the cached office roster.
4. Select a bill, choose **Oppose** or **Support**, and select an office. Edit the preview if needed. Offices in the chamber currently handling the bill appear first. When a recorded roll is available from the House or Senate, the preview shows the selected member’s vote and links to the official record. The app can copy the letter and open the office’s published contact form or official website. Paste the letter and submit it there. A separate **Copy subject** button is available for forms with a subject field.
5. Use **Civic diary** to review the handoff and mark it sent after you submit it. The app has no access to your mail client's outbox or the office's form submission status.

The default letter bodies are in `${XDG_CONFIG_HOME:-~/.config}/constituent/templates/`. They support `{{bill_id}}`, `{{bill_title}}`, `{{bill_stage}}`, `{{official_name}}`, `{{official_title}}`, `{{stance}}`, `{{user_name}}`, and `{{user_address}}`.

## Official data and refresh

- **Legislation.** [GovInfo Bill Status](https://www.govinfo.gov/bulkdata/BILLSTATUS) archives supply H.R. and S. measures, CRS summaries when available, sponsors, committees, action timelines, and linked floor votes. The bill record links back to Congress.gov. Badges distinguish a chamber’s passage, calendar placement, referrals, and failed procedural motions. When the source identifies a substitute title, the bill view displays it alongside the originating measure. After a Congress changes, refresh pulls the newly seated Congress and keeps the existing local records.
- **Directory.** [Office of the Clerk](https://clerk.house.gov/xml/lists/MemberData.xml), [House.gov](https://www.house.gov/representatives), and the [Senate’s contact feed](https://www.senate.gov/general/contact_information/senators_cfm.xml) supply sitting members and delegates, published phone numbers, Capitol office addresses, and official websites or contact links. A vacancy or district without a current office record may reduce the available contacts.
- **Court filings.** The first page of the [FISA Court’s public-filing index](https://www.fisc.uscourts.gov/public-filings) supplies recent filing titles and dates. The app opens the official filing externally. **Declassified opinions** in the FISA hub links to dated [ODNI releases](https://www.intelligence.gov/transparency) and the published documents.
- **Public comments.** The DMCA hub shows the Copyright Office’s Section 1201 proceeding, filing deadlines, and the official submission link. [Read the rulemaking notice](https://www.govinfo.gov/content/pkg/FR-2026-10-28/pdf/2026-21939.pdf).

On Linux the app refreshes on startup and every four hours while open, matching GovInfo’s stated bulk-update cadence. The first online refresh builds the offline text index. For the bundled Congress, the status archives are about 45 MB and the text archives are about 132 MB. The resulting SQLite cache takes roughly 390 MB. The bundled titles and summaries are available while the initial text download runs. Subsequent refreshes use conditional requests where the source provides cache validators. New actions in matched bills get an in-app badge and a notification when the session supports desktop notifications. A source failure leaves the previous cache available. Open the sync status to see refresh errors.

SQLite lives under `${XDG_DATA_HOME:-~/.local/share}/constituent/`. The saved address is local and unencrypted, protected by the user’s filesystem permissions. Public-data refresh requests do not carry profile data. Opening a draft or copying a letter passes the text to the chosen application or the system clipboard.

## Android alpha

Install the signed ARM64 APK from the [GitHub release](https://github.com/CallMeBakugo/constituent/releases/tag/v2.0.0) on Android 9 or newer. In Obtainium, add the [Constituent repository](https://github.com/CallMeBakugo/constituent) as a GitHub source and enable prereleases. The app starts with the bundled snapshot. Open the navigation menu and use **Refresh** to download official data and build the full bill-text index. The first refresh is best done over Wi-Fi.

The APK uses package id `org.constituent.constituent`. Future APK updates over an existing install require the same signing key. The [Android build notes](packaging/android/README.md) describe the build and identify the bundled runtime sources.

## Verify or refresh the snapshot

```sh
PYTHONPATH=src QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v
PYTHONPATH=src python tools/make_snapshot.py --congress 119
```

The application architecture keeps PySide6 at the interface boundary. The official-source parsers, refresh service, local cache, and letter renderer are pure Python.
