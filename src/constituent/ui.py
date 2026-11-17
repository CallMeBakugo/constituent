"""Native Qt desktop interface for the local civic workspace."""

import json
import sqlite3
from datetime import date
from urllib.parse import urlsplit

from PySide6.QtCore import QEvent, QSize, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFormLayout, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox, QPushButton,
    QScrollArea, QSizePolicy, QStackedWidget, QSystemTrayIcon, QTabWidget, QTextEdit,
    QVBoxLayout, QWidget,
)

from .advocacy import ensure_templates, letter, mailto
from .agency import AGENCY_OPINIONS, RULEMAKING, comment_window
from .legislation import EVENT_LABELS, action_kind, bill_stage
from .office_data import bill_votes, official_contact
from .sources import FISC_OPINIONS, GPO, HOUSE_LOOKUP
from .store import STATUSES, STATES
from .sync import current_congress, refresh
from .theme import DEFAULT_THEME, apply_theme



def label(text="", name="", wrap=False):
    item = QLabel(text)
    item.setTextFormat(Qt.TextFormat.PlainText)
    item.setObjectName(name)
    item.setWordWrap(wrap)
    return item


def button(text, callback, role=""):
    item = QPushButton(text)
    item.setObjectName(role)
    item.setCursor(Qt.CursorShape.PointingHandCursor)
    item.clicked.connect(callback)
    return item


def box(widget=None, margins=(0, 0, 0, 0), gap=10, horizontal=False):
    layout = (QHBoxLayout if horizontal else QVBoxLayout)(widget)
    layout.setContentsMargins(*margins)
    layout.setSpacing(gap)
    return layout


def frame(name, margins=(18, 18, 18, 18), gap=10):
    widget = QFrame()
    widget.setObjectName(name)
    return widget, box(widget, margins, gap)


def rule():
    item = QFrame()
    item.setObjectName("rule")
    return item


def scroll(layout_widget):
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setWidget(layout_widget)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    return area


def plain_scroll(margins=(0, 0, 0, 0), gap=12):
    widget = QWidget()
    return scroll(widget), box(widget, margins, gap)


def badge(status):
    item = label(status)
    item.setProperty("stage", status)
    return item


def display_date(iso):
    try:
        return date.fromisoformat(iso[:10]).strftime("%b %d, %Y").replace(" 0", " ")
    except ValueError:
        return "Date unavailable"


def safe_open(url):
    parsed = urlsplit(url)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname:
        return False
    host = parsed.hostname.lower()
    if not (host.endswith(".gov") or host == "govinfo.gov"):
        return False
    return QDesktopServices.openUrl(QUrl(url))


class RefreshThread(QThread):
    progress = Signal(str)
    result = Signal(int, list)

    def __init__(self, store):
        super().__init__()
        self.store = store

    def run(self):
        try:
            count, errors = refresh(self.store, self.progress.emit)
        except Exception as error:
            count, errors = 0, [str(error)]
        self.result.emit(count, errors)


class OfficeLookup(QThread):
    contacts_ready = Signal(dict)
    votes_ready = Signal(list)

    def __init__(self, owner, bill, offices):
        super().__init__(owner)
        self.store, self.bill, self.offices = owner.store, bill, offices

    def run(self):
        from concurrent.futures import ThreadPoolExecutor
        try:
            with ThreadPoolExecutor(max_workers=4) as pool:
                votes = pool.submit(bill_votes, self.store, self.bill, self.offices)
                forms = pool.map(lambda office: official_contact(self.store, office), self.offices)
                self.contacts_ready.emit(dict(zip((office["id"] for office in self.offices), forms)))
                self.votes_ready.emit(votes.result())
        except Exception:
            self.votes_ready.emit([])


class Window(QMainWindow):
    def __init__(self, store, config, *, automatic_refresh=True, mobile=False):
        super().__init__()
        self.store = store
        self.mobile = mobile
        self.theme = store.get_setting("theme", DEFAULT_THEME)
        apply_theme(QApplication.instance(), self.theme)
        self.templates = ensure_templates(config)
        self.profile = store.get_setting("profile")
        self.hub_id = 1
        self.view = "hub"
        self.active_bill = None
        self.worker = None
        self.office_workers = set()
        self.quitting = False
        self.sync_errors = []
        self.setWindowTitle("Constituent")
        if self.mobile:
            self.resize(390, 780)
        else:
            self.resize(1350, 860)
            self.setMinimumSize(1060, 690)
        logo = QPixmap(64, 64)
        logo.fill(Qt.GlobalColor.transparent)
        painter = QPainter(logo)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor("#c4b4ff"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(0, 0, 64, 64, 16, 16)
        painter.setPen(QColor("#211244"))
        painter.setFont(QFont("Noto Serif", 29, QFont.Weight.Bold))
        painter.drawText(logo.rect(), Qt.AlignmentFlag.AlignCenter, "C")
        painter.end()
        self.setWindowIcon(QIcon(logo))

        shell = QWidget()
        root = box(shell, gap=0, horizontal=True)
        self.setCentralWidget(shell)
        self.sidebar, self.navigation = frame("sidebar", (16, 22, 16, 18), 10)
        self.sidebar.setFixedWidth(228)
        root.addWidget(self.sidebar)
        self.sidebar.setVisible(not self.mobile)

        main = QWidget()
        main_layout = box(main, gap=0)
        root.addWidget(main, 1)
        top = QFrame()
        top.setObjectName("topbar")
        top.setFixedHeight(61)
        margins = (8, 0, 8, 0) if self.mobile else (24, 0, 24, 0)
        top_layout = box(top, margins, 9, horizontal=True)
        main_layout.addWidget(top)
        self.breadcrumb = label("", "strong")
        if self.mobile:
            self.mobile_menu = QMenu(self)
            navigation = QPushButton("☰  Menu")
            navigation.setMenu(self.mobile_menu)
            top_layout.addWidget(navigation)
            top_layout.addWidget(label("Constituent", "strong"))
        else:
            top_layout.addWidget(self.breadcrumb)
        top_layout.addStretch()
        self.feed_status = button("", self.sync_info, "link")
        self.feed_status.setToolTip("View data sources and the last refresh result")
        if self.mobile:
            top_layout.addWidget(button("Data", self.sync_info, "link"))
        else:
            top_layout.addWidget(self.feed_status)
        self.refresh_button = button("↻  Refresh", self.start_refresh)
        top_layout.addWidget(self.refresh_button)
        self.deck = QStackedWidget()
        main_layout.addWidget(self.deck, 1)

        self.tray = QSystemTrayIcon(self.windowIcon(), self)
        self.tray.setToolTip("Constituent")
        self.tray.activated.connect(self.activate_tray)
        self.tray.messageClicked.connect(self.restore_window)
        tray_menu = QMenu(self)
        tray_menu.addAction("Show Constituent", self.restore_window)
        tray_menu.addSeparator()
        tray_menu.addAction("Quit Constituent", self.request_quit)
        self.tray.setContextMenu(tray_menu)
        if not self.mobile:
            self.tray.show()
        self.poll = QTimer(self)
        self.poll.setInterval(4 * 60 * 60 * 1000)
        self.poll.timeout.connect(self.start_refresh)
        if automatic_refresh:
            self.poll.start()
            QTimer.singleShot(2500, self.start_refresh)
        self.update_feed_status()
        self.open_hub(1)

    def nav(self):
        if self.mobile:
            self.mobile_menu.clear()
            for hub in self.store.hubs():
                self.mobile_menu.addAction(hub["name"], lambda key=hub["id"]: self.open_hub(key))
            self.mobile_menu.addAction("New hub", self.new_hub)
            self.mobile_menu.addSeparator()
            self.mobile_menu.addAction("Government directory", self.open_directory)
            self.mobile_menu.addAction("What changed", self.open_activity)
            self.mobile_menu.addAction("Civic diary", self.open_diary)
            self.mobile_menu.addAction("My profile", self.edit_profile)
            self.theme_switch = self.mobile_menu.addAction(self.theme_switch_label(), self.toggle_theme)
            return
        while self.navigation.count():
            item = self.navigation.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        brand = QWidget()
        row = box(brand, (3, 0, 0, 0), 9, horizontal=True)
        icon = label("C", "brandIcon")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setFixedSize(34, 34)
        row.addWidget(icon)
        row.addWidget(label("Constituent", "wordmark"))
        row.addStretch()
        self.navigation.addWidget(brand)
        self.navigation.addSpacing(22)
        self.navigation.addWidget(label("LEGISLATION HUBS", "navLabel"))
        hub_widget = QWidget()
        hub_layout = box(hub_widget, gap=4)
        for hub in self.store.hubs():
            item = button(hub["name"], lambda checked=False, key=hub["id"]: self.open_hub(key))
            item.setCheckable(True)
            item.setChecked(self.view in {"hub", "filings"} and hub["id"] == self.hub_id)
            hub_layout.addWidget(item)
        area = scroll(hub_widget)
        area.setMaximumHeight(255)
        area.setFixedHeight(min(hub_layout.sizeHint().height(), 255))
        self.navigation.addWidget(area)
        self.navigation.addWidget(button("＋  New hub", self.new_hub, "navNew"))
        self.navigation.addSpacing(17)
        self.navigation.addWidget(label("CIVIC TOOLS", "navLabel"))
        for name, key, handler in (
            ("Government directory", "directory", self.open_directory),
            ("What changed", "activity", self.open_activity),
            ("Civic diary", "diary", self.open_diary),
            ("My profile", "profile", self.edit_profile),
        ):
            item = button(name, handler)
            item.setCheckable(True)
            item.setChecked(self.view == key)
            self.navigation.addWidget(item)
        self.navigation.addStretch()
        self.theme_switch = button(self.theme_switch_label(), self.toggle_theme, "themeSwitch")
        self.navigation.addWidget(self.theme_switch)
        region = self.profile and self.profile["state"]
        district = self.profile and self.profile["district"]
        district_label = f"{region} · At large" if district == "00" else f"{region}-{district}"
        self.navigation.addWidget(label(district_label if region else "Set up your district in My profile", "navMeta", True))
        self.navigation.addWidget(label("Local workspace", "navMeta"))

    def theme_switch_label(self):
        return "Switch to light mode" if self.theme == "dark" else "Switch to dark mode"

    def toggle_theme(self):
        self.theme = "light" if self.theme == "dark" else "dark"
        self.store.set_setting("theme", self.theme)
        apply_theme(QApplication.instance(), self.theme)
        self.theme_switch.setText(self.theme_switch_label())

    def update_feed_status(self):
        last = self.store.get_setting("last_sync")
        if self.sync_errors:
            state = "●  Refresh incomplete"
        elif last:
            state = f"●  Synced {display_date(last)}"
        else:
            state = f"●  Snapshot · {display_date(self.store.get_setting('snapshot'))}"
        self.feed_status.setText(state)

    def sync_info(self):
        info = QMessageBox(self)
        info.setWindowTitle("Official data")
        info.setTextFormat(Qt.TextFormat.PlainText)
        info.setText(f"Bundled snapshot: {display_date(self.store.get_setting('snapshot'))}")
        last = self.store.get_setting("last_sync")
        message = f"Last complete refresh: {display_date(last) if last else 'None yet'}\n\n"
        message += "Bills: GovInfo Bill Status and official bill text • Directory: House Clerk, House.gov, and Senate.gov. Court filings: Foreign Intelligence Surveillance Court."
        if self.sync_errors:
            message += "\n\n" + "\n".join(self.sync_errors)
        info.setInformativeText(message)
        source = info.addButton("Open GovInfo", QMessageBox.ButtonRole.ActionRole)
        info.addButton(QMessageBox.StandardButton.Close)
        info.exec()
        if info.clickedButton() == source:
            safe_open(GPO)

    def start_refresh(self):
        if self.quitting or self.worker:
            return
        self.worker = RefreshThread(self.store)
        if self.mobile:
            self.worker.progress.connect(lambda message: self.statusBar().showMessage(message))
        else:
            self.worker.progress.connect(self.feed_status.setText)
        self.worker.result.connect(self.refresh_done)
        self.worker.finished.connect(self.release_worker)
        self.refresh_button.setEnabled(False)
        self.worker.start()

    def release_worker(self):
        self.worker.deleteLater()
        self.worker = None
        if self.quitting and not self.office_workers:
            self.finish_quit()

    def refresh_done(self, count, errors):
        if self.quitting:
            return
        self.sync_errors = errors
        self.refresh_button.setEnabled(True)
        self.update_feed_status()
        if self.view == "hub":
            self.fill_bills(self.active_bill and self.active_bill["key"])
        elif self.view == "directory":
            self.fill_directory()
        elif self.view == "filings":
            self.open_filings()
        elif self.view == "activity":
            self.open_activity()
        if count:
            message = f"{count} new legislative {'action' if count == 1 else 'actions'}."
            self.statusBar().showMessage(message, 10000)
            if QSystemTrayIcon.supportsMessages():
                self.tray.showMessage("Constituent", message, QSystemTrayIcon.MessageIcon.Information)
            else:
                from shutil import which
                from subprocess import Popen
                if which("notify-send"):
                    Popen(["notify-send", "Constituent", message])
        elif errors:
            self.statusBar().showMessage("Refresh incomplete. The cached records are still available.", 9000)
        else:
            self.statusBar().showMessage("Official records are up to date.", 6500)

    def activate_tray(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.restore_window()

    def restore_window(self):
        if self.quitting:
            return
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized)
        self.show()
        self.raise_()
        self.activateWindow()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange and self.isMinimized():
            QTimer.singleShot(0, self.hide_minimized_window)

    def hide_minimized_window(self):
        if not self.mobile and self.isMinimized() and QSystemTrayIcon.isSystemTrayAvailable():
            self.hide()

    def closeEvent(self, event):
        if not self.mobile and not self.quitting and QSystemTrayIcon.isSystemTrayAvailable():
            event.ignore()
            self.hide()
            return
        if self.worker or self.office_workers:
            event.ignore()
            self.request_quit()
            return
        super().closeEvent(event)

    def request_quit(self):
        self.quitting = True
        self.poll.stop()
        if self.worker or self.office_workers:
            self.tray.setToolTip("Constituent is finishing its refresh before quitting")
            self.statusBar().showMessage("Finishing the current refresh before quitting.")
        else:
            self.finish_quit()

    def finish_quit(self):
        self.tray.hide()
        QApplication.instance().quit()

    def replace_page(self, page, breadcrumb):
        previous = self.deck.currentWidget()
        self.deck.addWidget(page)
        self.deck.setCurrentWidget(page)
        if previous:
            self.deck.removeWidget(previous)
            previous.deleteLater()
        self.breadcrumb.setText(breadcrumb)
        self.nav()

    def page_header(self, layout, title, subtitle, action=None):
        hero, content = frame("hero", (22, 15, 22, 15), 4)
        content.addWidget(label(title, "heroTitle", True))
        line = QHBoxLayout()
        line.addWidget(label(subtitle, "muted", True), 1)
        if action and not self.mobile:
            line.addWidget(action)
        content.addLayout(line)
        if action and self.mobile:
            content.addWidget(action, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(hero)

    def open_hub(self, key):
        self.hub_id = key
        self.view = "hub"
        self.active_bill = None
        self.hub = next(hub for hub in self.store.hubs() if hub["id"] == key)
        page = QWidget()
        outer = box(page, (21, 17, 21, 19), 14)
        heading = outer
        if self.mobile:
            toolbar = QWidget()
            heading = box(toolbar, gap=10)
            outer.addWidget(toolbar)
        action = None
        if self.hub["id"] == 3:
            action = button("Court filings", self.open_filings)
        elif self.hub["id"] == 2:
            action = button("Public comments", self.open_comments)
        self.page_header(heading, self.hub["name"], self.hub["description"], action)
        bar = QHBoxLayout()
        bar.setSpacing(10)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search titles, summaries, and bill text")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda: self.fill_bills())
        bar.addWidget(self.search, 1)
        self.status_filter = QComboBox()
        self.status_filter.addItems(["All statuses", *STATUSES])
        self.status_filter.setMinimumWidth(150)
        self.status_filter.currentIndexChanged.connect(lambda: self.fill_bills())
        if not self.mobile:
            bar.addWidget(self.status_filter)
        heading.addLayout(bar)
        if self.mobile:
            heading.addWidget(self.status_filter)
        options = QHBoxLayout()
        self.latest_text = QCheckBox("Latest published text only")
        self.latest_text.toggled.connect(lambda: self.fill_bills())
        options.addWidget(self.latest_text)
        options.addStretch()
        options.addWidget(button("Edit hub", lambda: self.hub_dialog(self.hub), "link"))
        heading.addLayout(options)
        left, left_layout = frame("panel", (9, 13, 9, 8), 9)
        if not self.mobile:
            left.setMinimumWidth(300)
            left.setMaximumWidth(359)
        row = QHBoxLayout()
        row.setContentsMargins(5, 0, 5, 0)
        row.addWidget(label("BILLS", "eyebrow"))
        row.addStretch()
        self.count_label = label("", "smallMuted")
        row.addWidget(self.count_label)
        left_layout.addLayout(row)
        self.results = QListWidget()
        self.results.setSpacing(3)
        self.results.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.results.currentItemChanged.connect(self.select_bill)
        left_layout.addWidget(self.results, 1)
        right, self.detail = frame("panel", (0, 0, 0, 0), 0)
        if self.mobile:
            self.hub_stack = QStackedWidget()
            self.hub_stack.addWidget(left)
            self.hub_stack.addWidget(right)
            self.hub_stack.currentChanged.connect(lambda index: toolbar.setVisible(index == 0))
            self.results.itemClicked.connect(lambda _: self.hub_stack.setCurrentIndex(1))
            outer.addWidget(self.hub_stack, 1)
        else:
            body = QHBoxLayout()
            body.setSpacing(12)
            body.addWidget(left, 3)
            body.addWidget(right, 6)
            outer.addLayout(body, 1)
        self.replace_page(page, f"Legislation hubs  /  {self.hub['name']}")
        self.fill_bills()

    def fill_bills(self, keep=None):
        status = self.status_filter.currentText() if self.status_filter.currentIndex() else ""
        self.visible_bills = self.store.bills(self.hub["phrases"], self.search.text(), status,
                                              latest_only=self.latest_text.isChecked())
        congress = current_congress()
        self.visible_bills.sort(key=lambda bill: bill["congress"] != congress)
        self.results.blockSignals(True)
        self.results.clear()
        self.count_label.setText(f"{len(self.visible_bills)} {'match' if len(self.visible_bills) == 1 else 'matches'}")
        index = 0
        for row, bill in enumerate(self.visible_bills):
            if bill["key"] == keep:
                index = row
            card = self.bill_card(bill)
            item = QListWidgetItem()
            item.setSizeHint(card.sizeHint())
            item.setData(Qt.ItemDataRole.AccessibleTextRole, f"{bill['bill_id']} {bill['title']} {bill['status']}")
            self.results.addItem(item)
            self.results.setItemWidget(item, card)
        self.results.blockSignals(False)
        if self.visible_bills:
            if not self.mobile or (keep and self.hub_stack.currentIndex() == 1):
                self.results.setCurrentRow(index)
        else:
            self.active_bill = None
            self.clear_detail()
            area, layout = plain_scroll((24, 25, 24, 24))
            layout.addWidget(label("No matching bills", "sectionTitle"))
            layout.addWidget(label("Try a different search or status filter.", "muted", True))
            layout.addStretch()
            self.detail.addWidget(area)

    def bill_card(self, bill):
        card = QWidget()
        content = box(card, (10, 8, 10, 8), 6)
        row = QHBoxLayout()
        row.addWidget(label(bill["bill_id"] + ("   •  New" if bill["unread"] else ""), "eyebrow"))
        row.addStretch()
        row.addWidget(badge(bill["status"]))
        content.addLayout(row)
        name = bill["title"]
        if len(name) > 98:
            name = name[:95].rstrip() + "…"
        title = label(name, "strong", True)
        title.setMinimumHeight(36)
        title.setMaximumHeight(42)
        content.addWidget(title)
        if bill["sponsors"]:
            sponsor = bill["sponsors"][0]["name"]
            sponsor = label(sponsor, "smallMuted")
            sponsor.setToolTip(" · ".join(bill["committees"]))
            content.addWidget(sponsor)
        row = QHBoxLayout()
        row.addWidget(label(display_date(bill["date"]), "smallMuted"))
        row.addStretch()
        row.addWidget(label(f"{bill['congress']}th Congress", "smallMuted"))
        content.addLayout(row)
        return card

    def clear_detail(self):
        while self.detail.count():
            widget = self.detail.takeAt(0).widget()
            widget.hide()
            widget.deleteLater()

    def select_bill(self, current, previous):
        if current is None:
            return
        bill = self.visible_bills[self.results.row(current)]
        if bill["unread"]:
            self.store.mark_read(bill["key"])
            bill["unread"] = False
            self.results.setItemWidget(current, self.bill_card(bill))
        self.render_bill(bill, self.hub["phrases"], self.search.text(), self.latest_text.isChecked())
        if self.mobile:
            self.hub_stack.setCurrentIndex(1)

    def render_bill(self, bill, phrases="", search="", latest_only=False):
        self.active_bill = bill
        self.clear_detail()
        area, layout = plain_scroll((21, 16, 21, 20), 11)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.detail.addWidget(area)
        if self.mobile and self.view == "hub":
            layout.addWidget(button("← Back to bills", lambda: self.hub_stack.setCurrentIndex(0), "link"))
        header = QHBoxLayout()
        header.addWidget(label(f"{bill['bill_id']}   /   {bill['congress']}th CONGRESS", "eyebrow"))
        header.addStretch()
        header.addWidget(badge(bill["status"]))
        layout.addLayout(header)
        layout.addWidget(label(bill["title"], "billTitle", True))
        stage = bill_stage(bill["actions"], bill["kind"], bill["status"] == "Enacted")
        layout.addWidget(label(stage.label, "strong", True))
        substitutes = bill.get("substitutes", [])
        if substitutes:
            layout.addWidget(label("Chamber amendment · " + " / ".join(substitutes), "eyebrow", True))
        if bill["sponsors"]:
            layout.addWidget(label(bill["sponsors"][0]["name"], "muted", True))
        if bill["committees"]:
            layout.addWidget(label(" · ".join(bill["committees"]), "smallMuted", True))
        layout.addSpacing(4)
        row = QHBoxLayout()
        row.addWidget(button("Oppose", lambda: self.advocate(bill, "oppose"), "primary"))
        row.addWidget(button("Support", lambda: self.advocate(bill, "support")))
        watched = self.store.is_watched(bill["key"])
        watch = QPushButton("Watching" if watched else "Watch bill")
        watch.setCheckable(True)
        watch.setChecked(watched)
        def set_watch(checked):
            self.store.set_watched(bill["key"], checked)
            watch.setText("Watching" if checked else "Watch bill")
        watch.toggled.connect(set_watch)
        row.addWidget(watch)
        row.addStretch()
        official = button("Congress.gov ↗", lambda: safe_open(bill["source"]), "link") if bill["source"] else None
        if official and not self.mobile:
            row.addWidget(official)
        layout.addLayout(row)
        if official and self.mobile:
            layout.addWidget(official, alignment=Qt.AlignmentFlag.AlignLeft)
        latest, latest_layout = frame("hero", (12, 10, 12, 10), 3)
        latest_layout.addWidget(label(f"LATEST ACTION   ·   {display_date(bill['date'])}", "eyebrow"))
        latest_layout.addWidget(label(bill["latest"] or "No action published.", "", True))
        layout.addWidget(latest)

        tabs = QTabWidget()
        layout.addWidget(tabs, 1)
        summary = QWidget()
        summary_layout = box(summary, (0, 11, 0, 0), 8)
        summary_layout.addWidget(label("Official summary", "sectionTitle"))
        summary_layout.addWidget(label(bill["summary"] or "Congress has yet to publish a summary for this measure.", "", True))
        match = self.store.text_match(bill["key"], phrases, search, latest_only=latest_only)
        if match:
            package, passage, source, published, is_latest = match
            summary_layout.addWidget(rule())
            heading = "Matching bill text" if is_latest else "Match in earlier bill text"
            summary_layout.addWidget(label(heading, "sectionTitle"))
            if published:
                summary_layout.addWidget(label(display_date(published), "eyebrow"))
            quote = label(passage, "", True)
            quote.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            summary_layout.addWidget(quote)
            summary_layout.addWidget(
                button(f"GovInfo · {package} ↗", lambda: safe_open(source), "link"),
                alignment=Qt.AlignmentFlag.AlignLeft,
            )
        summary_layout.addStretch()
        tabs.addTab(summary, "Summary")

        timeline = QWidget()
        timeline_layout = box(timeline, (0, 10, 0, 0), 10)
        if not bill["actions"]:
            timeline_layout.addWidget(label("No actions published.", "muted"))
        for action in bill["actions"]:
            heading = display_date(action["date"])
            event = EVENT_LABELS.get(action_kind(action))
            if event:
                heading += " · " + event
            timeline_layout.addWidget(label(heading, "eyebrow"))
            timeline_layout.addWidget(label(action["text"], "", True))
            for name, url in action["links"]:
                if url:
                    timeline_layout.addWidget(button(f"{name or 'Official record'} ↗", lambda _, target=url: safe_open(target), "link"),
                                              alignment=Qt.AlignmentFlag.AlignLeft)
            timeline_layout.addWidget(rule())
        timeline_layout.addStretch()
        tabs.addTab(timeline, f"Actions ({len(bill['actions'])})")

        people = QWidget()
        people_layout = box(people, (0, 10, 0, 0), 7)
        for heading, records in (("Sponsors", bill["sponsors"]), ("Cosponsors", bill["cosponsors"])):
            people_layout.addWidget(label(f"{heading} ({len(records)})", "sectionTitle"))
            if not records:
                people_layout.addWidget(label("None listed.", "muted"))
            for person in records:
                withdrawn = person.get("withdrawn")
                people_layout.addWidget(label(person["name"] + (" · Withdrawn" if withdrawn else ""), "", True))
        people_layout.addStretch()
        tabs.addTab(people, "Sponsors")
        stack = tabs.findChild(QStackedWidget)
        def fit_tab():
            current = tabs.currentWidget()
            if current and stack:
                for index in range(stack.count()):
                    child = stack.widget(index)
                    child.setSizePolicy(child.sizePolicy().horizontalPolicy(),
                                        QSizePolicy.Policy.Ignored if child is not current
                                        else QSizePolicy.Policy.Preferred)
                tabs.updateGeometry()
        tabs.currentChanged.connect(lambda _: fit_tab())
        fit_tab()

    def open_filings(self):
        self.view = "filings"
        page = QWidget()
        layout = box(page, (21, 17, 21, 19), 14)
        self.page_header(layout, "FISA Court filings", "Recent public filings from the court’s official index",
                         button("Back to bills", lambda: self.open_hub(self.hub_id)))
        panel, content = frame("panel", (16, 12, 16, 12))
        area, filings = plain_scroll((0, 3, 10, 3), 8)
        content.addWidget(area, 1)
        filings.addWidget(button("Open court index ↗", lambda: safe_open(FISC_OPINIONS), "link"),
                          alignment=Qt.AlignmentFlag.AlignLeft)
        if not self.store.get_setting("court_filings"):
            filings.addWidget(label("Refresh to retrieve the court’s public filings.", "muted"))
        for filing in self.store.get_setting("court_filings", []):
            date_text = f"Posted {display_date(filing.get('posted', ''))}  ·  Filed {display_date(filing.get('filed', ''))}"
            filings.addWidget(rule())
            filings.addWidget(label(date_text, "eyebrow"))
            filings.addWidget(label(filing["title"], "strong", True))
            filings.addWidget(button("Official filing ↗", lambda _, url=filing["url"]: safe_open(url), "link"),
                              alignment=Qt.AlignmentFlag.AlignLeft)
        filings.addWidget(rule())
        filings.addWidget(label("Declassified opinions", "sectionTitle"))
        for posted, title, url in AGENCY_OPINIONS:
            filings.addWidget(label(f"ODNI · {display_date(posted)}", "eyebrow"))
            filings.addWidget(label(title, "strong", True))
            filings.addWidget(button("Official release ↗", lambda _, target=url: safe_open(target), "link"),
                              alignment=Qt.AlignmentFlag.AlignLeft)
        filings.addStretch()
        layout.addWidget(panel, 1)
        self.replace_page(page, "FISA Court Rulings  /  Public filings")

    def open_comments(self):
        self.view = "comments"
        page = QWidget()
        layout = box(page, (21, 17, 21, 19), 14)
        self.page_header(layout, "Public comments", "U.S. Copyright Office rulemaking",
                         button("Back to bills", lambda: self.open_hub(self.hub_id)))
        panel, content = frame("panel")
        content.addWidget(label(RULEMAKING["title"], "sectionTitle", True))
        content.addWidget(label(RULEMAKING["docket"], "muted", True))
        next_round = comment_window()
        content.addWidget(label(
            f"Next deadline · {display_date(next_round[1])}" if next_round else "Comment rounds closed",
            "eyebrow",
        ))
        for description, deadline in RULEMAKING["rounds"]:
            content.addWidget(label(f"{display_date(deadline)} · {description}", "", True))
        content.addWidget(button("How to submit comments ↗", lambda: safe_open(RULEMAKING["submit"]), "primary"),
                          alignment=Qt.AlignmentFlag.AlignLeft)
        for title, key in (("Regulations.gov docket ↗", "docket_url"), ("Federal Register notice ↗", "notice")):
            content.addWidget(button(title, lambda _, url=RULEMAKING[key]: safe_open(url), "link"),
                              alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(panel)
        layout.addStretch()
        self.replace_page(page, "DMCA Bullshit  /  Public comments")

    def open_activity(self):
        self.view = "activity"
        page = QWidget()
        layout = box(page, (21, 17, 21, 19), 14)
        self.page_header(layout, "What changed", "New official actions and your watched bills")
        panel, content = frame("panel")
        area, entries = plain_scroll(gap=8)
        content.addWidget(area)
        entries.addWidget(label("Watching", "sectionTitle"))
        watched = self.store.watched_bills()
        if not watched:
            entries.addWidget(label("Choose Watch bill on a bill to keep it here.", "muted", True))
        for bill in watched:
            entries.addWidget(button(f'{bill["bill_id"]} · {bill["title"][:31 if self.mobile else 85]}',
                                     lambda _, key=bill["key"]: self.open_activity_bill(key), "link"),
                              alignment=Qt.AlignmentFlag.AlignLeft)
        entries.addWidget(rule())
        entries.addWidget(label("New actions", "sectionTitle"))
        activity = self.store.recent_activity()
        if not activity:
            entries.addWidget(label("New actions will appear after a refresh finds them.", "muted", True))
        for entry in activity:
            bill = json.loads(entry["data"])
            entries.addWidget(button(f'{bill["bill_id"]} · {bill["title"][:31 if self.mobile else 85]}',
                                     lambda _, key=entry["bill_key"]: self.open_activity_bill(key), "link"),
                              alignment=Qt.AlignmentFlag.AlignLeft)
            entries.addWidget(label(display_date(entry["date"]), "eyebrow"))
            entries.addWidget(label(entry["text"], "", True))
            entries.addWidget(rule())
        entries.addStretch()
        layout.addWidget(panel, 1)
        self.replace_page(page, "What changed")

    def open_activity_bill(self, key):
        bill = self.store.get_bill(key)
        if not bill:
            return
        self.view = "activity_bill"
        self.store.mark_read(key)
        page = QWidget()
        outer = box(page, (21, 17, 21, 19), 12)
        outer.addWidget(button("← What changed", self.open_activity, "link"),
                        alignment=Qt.AlignmentFlag.AlignLeft)
        panel, self.detail = frame("panel", (0, 0, 0, 0))
        outer.addWidget(panel, 1)
        self.replace_page(page, bill["bill_id"])
        self.render_bill(bill)

    def new_hub(self):
        self.hub_dialog()

    def hub_dialog(self, hub=None):
        dialog = QDialog(self)
        heading = "Edit hub" if hub else "New hub"
        dialog.setWindowTitle(heading)
        if not self.mobile:
            dialog.setMinimumWidth(460)
        content = box(dialog, (22, 19, 22, 19))
        content.addWidget(label(heading, "sectionTitle"))
        name = QLineEdit(hub["name"] if hub else "")
        terms = QLineEdit(hub["phrases"] if hub else "")
        terms.setPlaceholderText("e.g. right to repair, digital ownership")
        form = QFormLayout()
        if self.mobile:
            form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        form.addRow("Hub name", name)
        form.addRow("Keywords", terms)
        content.addLayout(form)
        content.addWidget(label("Use commas between phrases. A bill matches when it contains any phrase.", "muted", True))
        error = label("", "muted", True)
        content.addWidget(error)
        def save():
            try:
                saved_id = self.store.add_hub(name.text(), terms.text(), hub["id"] if hub else None)
            except sqlite3.IntegrityError:
                error.setText("A hub already uses that name.")
            except ValueError as exc:
                error.setText(str(exc))
            else:
                dialog.accept()
                self.open_hub(saved_id)
        save_button = button("Save hub" if hub else "Create hub", save, "primary")
        save_button.setDefault(True)
        content.addWidget(save_button, alignment=Qt.AlignmentFlag.AlignRight)
        dialog.exec()

    def edit_profile(self):
        profile = self.profile or {}
        dialog = QDialog(self)
        dialog.setWindowTitle("My profile")
        if not self.mobile:
            dialog.setMinimumWidth(525)
        content = box(dialog, (22, 19, 22, 19), 12)
        content.addWidget(label("My profile", "sectionTitle"))
        content.addWidget(label("Your address stays on this device until you choose to place it in a letter.", "muted", True))
        form = QFormLayout()
        if self.mobile:
            form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        name = QLineEdit(profile.get("name", ""))
        address = QTextEdit()
        address.setPlainText(profile.get("address", ""))
        address.setAcceptRichText(False)
        address.setPlaceholderText("Street address, city, state, and ZIP")
        address.setFixedHeight(92)
        state = QComboBox()
        state.addItem("Select your state or territory", "")
        for short in sorted(STATES):
            state.addItem(short, short)
        district = QComboBox()
        def districts():
            district.clear()
            district.addItem("Select a congressional district", "")
            for member in self.store.members(state.currentData()) if state.currentData() else []:
                if member["chamber"] == "House":
                    number = member["district"]
                    title = "At large" if number == "00" else f"District {int(number)}"
                    district.addItem(f"{title} · {member['name']}", number)
            if district.count() == 2 and district.itemData(1) == "00":
                district.setCurrentIndex(1)
        state.currentIndexChanged.connect(lambda _: districts())
        state.setCurrentIndex(max(0, state.findData(profile.get("state"))))
        districts()
        if profile.get("district"):
            district.setCurrentIndex(max(0, district.findData(profile["district"])))
        form.addRow("Name", name)
        form.addRow("Mailing address", address)
        form.addRow("State", state)
        form.addRow("House district", district)
        content.addLayout(form)
        content.addWidget(button("Find your district on House.gov ↗", lambda: safe_open(HOUSE_LOOKUP), "link"))
        error = label("", "muted", True)
        content.addWidget(error)

        def save():
            if not (name.text().strip() and address.toPlainText().strip() and state.currentData()):
                error.setText("Enter your name, mailing address, and state.")
                return
            if district.count() > 1 and not district.currentData():
                error.setText("Choose the House district for your address.")
                return
            self.profile = {"name": name.text().strip(), "address": address.toPlainText().strip(),
                            "state": state.currentData(), "district": district.currentData()}
            self.store.set_setting("profile", self.profile)
            dialog.accept()
        save_button = button("Save profile", save, "primary")
        save_button.setDefault(True)
        content.addWidget(save_button, alignment=Qt.AlignmentFlag.AlignRight)
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        if accepted:
            self.nav()
            if self.view == "directory":
                self.fill_directory()
        return accepted

    def advocate(self, bill, stance):
        if not self.profile and not self.edit_profile():
            return
        offices = self.store.representatives(self.profile)
        stage = bill_stage(bill["actions"], bill["kind"], bill["status"] == "Enacted")
        offices.sort(key=lambda office: (
            office["chamber"] != stage.chamber, not bool(office.get("form") or office.get("email"))
        ))
        if not offices:
            QMessageBox.information(self, "No offices found", "Check your state and district in My profile.")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(f"{stance.title()} {bill['bill_id']}")
        if not self.mobile:
            dialog.setMinimumWidth(600)
        content = box(dialog, (22, 18, 22, 18), 10)
        content.addWidget(label(f"{stance.title()} {bill['bill_id']}", "sectionTitle"))
        content.addWidget(label(stage.label, "muted", True))
        office_picker = QComboBox()
        for office in offices:
            office_picker.addItem(f"{office['name']} · U.S. {office['chamber']}", office)
        content.addWidget(office_picker)
        votes_area = QComboBox()
        votes_area.setVisible(False)
        content.addWidget(votes_area)
        vote_link = button("Official roll call ↗", lambda: safe_open(votes_area.currentData()), "link")
        vote_link.setVisible(False)
        content.addWidget(vote_link, alignment=Qt.AlignmentFlag.AlignLeft)
        contacts, roll_calls = {}, []
        subject_label = label("", "strong", True)
        content.addWidget(subject_label)
        preview = QTextEdit()
        preview.setAcceptRichText(False)
        preview.setMinimumHeight(145 if self.mobile else 240)
        content.addWidget(preview)
        footer = QVBoxLayout() if self.mobile else QHBoxLayout()
        content.addLayout(footer)
        note = label("", "muted", True)
        content.addWidget(note)
        action = button("", lambda: handoff(), "primary")
        footer.addWidget(action)
        copy = button("Copy letter", lambda: handoff(copy_only=True))
        footer.addWidget(copy)
        copy_subject = button("Copy subject", lambda: QApplication.clipboard().setText(subject_label.text()))
        footer.addWidget(copy_subject)
        footer.addStretch()
        office_picker.currentIndexChanged.connect(lambda _: show_letter())

        def update_office():
            office = office_picker.currentData()
            form = contacts.get(office["id"]) or office["form"]
            action.setText("Open email draft" if office["email"] else
                           "Copy & open contact page" if form else "Copy & open office site")
            votes_area.clear()
            for official, vote, day, kind, url in roll_calls:
                if official == office["id"]:
                    votes_area.addItem(f"{vote} · {kind} · {display_date(day)}", url)
            votes_area.setVisible(votes_area.count() > 0)
            vote_link.setVisible(votes_area.count() > 0)

        def show_letter():
            office = office_picker.currentData()
            try:
                subject, body = letter(self.templates, bill, office, self.profile, stance)
            except (ValueError, OSError, UnicodeError) as error:
                subject_label.clear()
                preview.clear()
                note.setText(str(error))
                action.setEnabled(False)
                copy.setEnabled(False)
                copy_subject.setEnabled(False)
                return
            subject_label.setText(subject)
            preview.setPlainText(body)
            copy.setEnabled(True)
            copy_subject.setEnabled(True)
            action.setEnabled(bool(office["email"] or office["form"] or office["site"]))
            update_office()
            note.setText("Your diary records the handoff. You can mark the letter sent after submitting it.")

        def handoff(copy_only=False):
            office = office_picker.currentData()
            subject, body = subject_label.text(), preview.toPlainText()
            if not body.strip():
                note.setText("Enter a message before preparing the letter.")
                return
            if copy_only or not office["email"]:
                QApplication.clipboard().setText(body)
                if copy_only:
                    outcome = "Copied"
                elif safe_open(contacts.get(office["id"]) or office["form"] or office["site"]):
                    outcome = "Contact opened"
                else:
                    outcome = "Copied"
                    note.setText("Copied the letter. The default browser could not open the office page.")
                    self.store.log(bill["bill_id"], office["name"], stance, outcome)
                    return
            else:
                if not QDesktopServices.openUrl(QUrl(mailto(office["email"], subject, body))):
                    note.setText("Could not open a mail client. Copy the letter to continue.")
                    return
                outcome = "Draft opened"
            self.store.log(bill["bill_id"], office["name"], stance, outcome)
            note.setText(f"{outcome} for {office['name']}. Recorded in your civic diary.")
        def display_contacts(forms):
            contacts.update(forms)
            update_office()

        def display_votes(votes):
            roll_calls.extend(votes)
            update_office()

        def release_lookup():
            self.office_workers.remove(worker)
            worker.deleteLater()
            if self.quitting and not (self.worker or self.office_workers):
                self.finish_quit()

        show_letter()
        worker = OfficeLookup(self, bill, offices)
        self.office_workers.add(worker)
        worker.contacts_ready.connect(display_contacts, Qt.ConnectionType.QueuedConnection)
        worker.votes_ready.connect(display_votes, Qt.ConnectionType.QueuedConnection)
        worker.finished.connect(release_lookup, Qt.ConnectionType.QueuedConnection)
        worker.start()
        try:
            dialog.exec()
        finally:
            if worker in self.office_workers:
                worker.contacts_ready.disconnect(display_contacts)
                worker.votes_ready.disconnect(display_votes)
                worker.finished.connect(dialog.deleteLater)
            else:
                dialog.deleteLater()

    def open_directory(self):
        self.view = "directory"
        page = QWidget()
        outer = box(page, (21, 17, 21, 19), 14)
        self.page_header(outer, "Government directory", "U.S. House and Senate offices",
                         button("My profile", self.edit_profile))
        bar = QHBoxLayout()
        self.member_search = QLineEdit()
        self.member_search.setPlaceholderText("Search name, state code, or district")
        self.member_search.setClearButtonEnabled(True)
        self.member_search.textChanged.connect(lambda _: self.fill_directory())
        bar.addWidget(self.member_search, 1)
        self.member_filter = QComboBox()
        self.member_filter.addItems(["All offices", "My representatives", "House", "Senate"])
        self.member_filter.currentIndexChanged.connect(lambda _: self.fill_directory())
        bar.addWidget(self.member_filter)
        outer.addLayout(bar)
        panel, layout = frame("panel", (12, 12, 12, 12), 4)
        self.member_list = QListWidget()
        self.member_list.itemActivated.connect(self.member_detail)
        self.member_list.itemClicked.connect(self.member_detail)
        layout.addWidget(self.member_list)
        outer.addWidget(panel, 1)
        self.replace_page(page, "Civic tools  /  Government directory")
        if self.profile:
            self.member_filter.setCurrentIndex(1)
        else:
            self.fill_directory()

    def fill_directory(self):
        selection = self.member_filter.currentText()
        self.member_list.clear()
        if selection == "My representatives" and not self.profile:
            item = QListWidgetItem("Save your state and district in My profile to see your representatives.")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.member_list.addItem(item)
            return
        members = (self.store.representatives(self.profile) if selection == "My representatives"
                   else self.store.members())
        term = self.member_search.text().strip().casefold()
        for member in members:
            if selection in {"House", "Senate"} and selection != member["chamber"]:
                continue
            district = member["district"]
            place = f"{member['state']}-{district}" if district else member["state"]
            if term not in f"{member['name']} {place}".casefold():
                continue
            suffix = " · ".join(filter(None, (member["chamber"], place, member["party"], member["phone"])))
            item = QListWidgetItem(f"{member['name']}    /    {suffix}")
            item.setSizeHint(QSize(0, self.member_list.fontMetrics().height() + 16))
            item.setData(Qt.ItemDataRole.UserRole, member)
            self.member_list.addItem(item)

    def member_detail(self, item):
        member = item.data(Qt.ItemDataRole.UserRole)
        if not member:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(member["name"])
        if not self.mobile:
            dialog.resize(640, 535)
        content = box(dialog, (20, 17, 20, 17))
        content.addWidget(label(member["name"], "sectionTitle"))
        content.addWidget(label(f"{member['chamber']} · {member['state']} · {member['party']}", "eyebrow"))
        layout_area, records = plain_scroll(gap=10)
        for value in (member["phone"], member["address"], member["term"]):
            if value:
                line = label(value, "", True)
                line.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                records.addWidget(line)
        if member["form"] or member["site"]:
            target = member["form"] or member["site"]
            records.addWidget(button("Official contact ↗", lambda: safe_open(target), "link"),
                              alignment=Qt.AlignmentFlag.AlignLeft)
        if member["committees"]:
            records.addWidget(label("Committees", "strong"))
            records.addWidget(label("\n".join(member["committees"]), "", True))
        records.addWidget(rule())
        records.addWidget(label("Sponsorship on your hubs", "strong"))
        matches = self.store.member_roles(member["id"])
        if not matches:
            records.addWidget(label("No sponsorship found in the cached matches.", "muted", True))
        for bill, role in matches:
            records.addWidget(label(f"{role} · {bill['bill_id']} · {bill['title']}", "", True))
        records.addStretch()
        content.addWidget(layout_area, 1)
        content.addWidget(button("Close", dialog.accept), alignment=Qt.AlignmentFlag.AlignRight)
        dialog.exec()

    def open_diary(self):
        self.view = "diary"
        page = QWidget()
        content = box(page, (21, 17, 21, 19), 14)
        self.page_header(content, "Civic diary", "Your advocacy activity, stored locally")
        panel, panel_layout = frame("panel", (16, 12, 16, 12))
        area, rows = plain_scroll(gap=9)
        panel_layout.addWidget(area)
        entries = self.store.diary()
        if not entries:
            rows.addWidget(label("No letters yet", "sectionTitle"))
            rows.addWidget(label("Open a bill and choose Oppose or Support to prepare your first letter.", "muted", True))
        for entry in entries:
            row = QHBoxLayout()
            details = QVBoxLayout()
            details.addWidget(label(f"{entry['stance'].title()} {entry['bill']} · {entry['official']}", "strong", True))
            details.addWidget(label(f"{display_date(entry['created'])} · {entry['status']}", "muted"))
            row.addLayout(details, 1)
            if entry["status"] != "Marked sent":
                row.addWidget(button("Mark sent", lambda _, key=entry["id"]: self.mark_sent(key)))
            rows.addLayout(row)
            rows.addWidget(rule())
        rows.addStretch()
        content.addWidget(panel, 1)
        self.replace_page(page, "Civic tools  /  Civic diary")

    def mark_sent(self, key):
        self.store.mark_sent(key)
        self.open_diary()
