"""Visual styles and native Qt palettes for the app’s two themes."""

from string import Template

from PySide6.QtGui import QColor, QPalette

DEFAULT_THEME = "dark"

# Each pair contains the light and dark values for the same UI role.
COLORS = {
    "canvas": ("#f8f7f3", "#17151d"),
    "text": ("#24232e", "#eeeaf4"),
    "title": ("#211b31", "#faf5ff"),
    "muted": ("#625e6d", "#bcb3cc"),
    "eyebrow": ("#65518b", "#c7a7f0"),
    "surface": ("#fff", "#211d2a"),
    "hero": ("#f0ebfb", "#30243f"),
    "hero_border": ("#e3d9f7", "#4b395f"),
    "top_border": ("#e5e2e9", "#393142"),
    "panel_border": ("#e7e1e8", "#3a3245"),
    "rule": ("#e8e3e9", "#393244"),
    "tab_border": ("#e9e4ed", "#3e344b"),
    "scroll": ("#c8bfd2", "#685c79"),
    "button_border": ("#ddd4e6", "#514460"),
    "panel_hover": ("#f3eefb", "#30263d"),
    "hover": ("#efe8fb", "#362847"),
    "primary": ("#6437a6", "#b895f4"),
    "primary_hover": ("#522b8c", "#cbb0fb"),
    "primary_text": ("#fff", "#231534"),
    "link": ("#6033a2", "#cfadff"),
    "focus": ("#8c61c2", "#c196fa"),
    "disabled_text": ("#83798c", "#a39ab1"),
    "disabled_bg": ("#efedf1", "#2b2634"),
    "field_border": ("#dcd5e3", "#51465e"),
    "selection": ("#6845a0", "#61448a"),
    "selected_tab": ("#59328c", "#e1c8ff"),
    "tab_indicator": ("#7b50b7", "#bb90f2"),
    "row_hover": ("#f8f5fc", "#2a2336"),
    "row_selected": ("#f1eafb", "#3a2c4c"),
    "row_border": ("#dac7f3", "#685183"),
}

STYLE = Template("""
QWidget {background: ${canvas}; color: ${text}; font-family: "Noto Sans"; font-size: 13px;}
QLabel, QTabWidget {background: transparent;}
QLabel#wordmark {font-family: "Noto Serif"; font-size: 23px; font-weight: 650; color: #fff;}
QFrame#sidebar QLabel#brandIcon {border-radius: 11px; background: #c4b4ff; color: #211244; font-size: 22px; font-weight: 800;}
QLabel#heroTitle {font-family: "Noto Serif"; font-size: 37px; font-weight: 650; color: ${title};}
QLabel#billTitle {font-family: "Noto Serif"; font-size: 30px; font-weight: 650; color: ${title};}
QLabel#sectionTitle {font-family: "Noto Serif"; font-size: 22px; font-weight: 600;}
QLabel#eyebrow {color: ${eyebrow}; font-size: 11px; font-weight: 750;}
QLabel#muted {color: ${muted};}
QLabel#smallMuted {color: ${muted}; font-size: 11px;}
QLabel#strong {font-weight: 670;}
QFrame#sidebar {background: #211932;}
QFrame#sidebar QWidget {background: transparent; color: #f5efff;}
QFrame#sidebar QLabel#navLabel {color: #c5b7d7; font-size: 10px; font-weight: 750;}
QFrame#sidebar QLabel#navMeta {color: #d2c6e0; font-size: 11px;}
QFrame#sidebar QPushButton {border: 1px solid transparent; color: #e8e0f0; text-align: left; padding: 8px 10px;}
QFrame#sidebar QPushButton:hover {background: #392d4e;}
QFrame#sidebar QPushButton:checked {background: #483768; color: #fff; border-color: #655184;}
QFrame#sidebar QPushButton#navNew {color: #d6c2fe; border: 1px dashed #67567c;}
QFrame#sidebar QLineEdit {color: #fff;}
QFrame#topbar {background: ${surface}; border-bottom: 1px solid ${top_border};}
QFrame#hero {background: ${hero}; border: 1px solid ${hero_border}; border-radius: 15px;}
QFrame#rule {background: ${rule}; min-height: 1px; max-height: 1px;}
QFrame#panel {background: ${surface}; border: 1px solid ${panel_border}; border-radius: 13px;}
QFrame#panel QWidget {background: transparent;}
QFrame#panel QScrollBar::handle:vertical {background: ${scroll};}
QFrame#panel QTabWidget::pane {border: none; border-top: 1px solid ${tab_border};}
QFrame#panel QPushButton {background: ${surface};}
QFrame#panel QPushButton:hover {background: ${panel_hover};}
QFrame#panel QPushButton#primary {background: ${primary}; color: ${primary_text}; border-color: ${primary};}
QFrame#panel QPushButton#primary:hover {background: ${primary_hover};}
QFrame#panel QPushButton#link {border: none; color: ${link}; padding: 4px 0; text-align: left;}
QFrame#panel QPushButton#link:hover {background: transparent; text-decoration: underline;}
QPushButton {border: 1px solid ${button_border}; border-radius: 8px; background: ${surface};
  padding: 8px 13px; font-weight: 650; min-height: 17px;}
QPushButton:hover {background: ${hover};}
QPushButton:focus, QLineEdit:focus, QComboBox:focus, QTextEdit:focus {border: 1px solid ${focus};}
QPushButton#primary {background: ${primary}; color: ${primary_text}; border-color: ${primary};}
QPushButton#primary:hover {background: ${primary_hover};}
QPushButton#link {border: none; background: transparent; color: ${link}; padding: 4px 0; text-align: left;}
QPushButton#link:hover {text-decoration: underline;}
QPushButton:disabled {color: ${disabled_text}; background: ${disabled_bg};}
QLineEdit, QComboBox, QTextEdit {background: ${surface}; border: 1px solid ${field_border};
  border-radius: 8px; padding: 8px 10px; selection-background-color: ${selection};}
QComboBox {padding-right: 25px;}
QTabBar::tab {background: transparent; color: ${muted}; padding: 10px 16px; border-bottom: 2px solid transparent;}
QTabBar::tab:selected {color: ${selected_tab}; font-weight: 750; border-bottom-color: ${tab_indicator};}
QListWidget {border: 0; outline: 0; background: transparent;}
QListWidget::item {background: transparent; border: 1px solid transparent; border-radius: 9px;}
QListWidget::item:hover {background: ${row_hover};}
QListWidget::item:selected {background: ${row_selected}; border-color: ${row_border}; color: ${text};}
QScrollArea {border: none; background: transparent;}
QScrollBar:vertical {width: 8px; background: transparent; margin: 2px;}
QScrollBar::handle:vertical {min-height: 28px; border-radius: 3px; background: ${scroll};}
QScrollBar::add-line, QScrollBar::sub-line {height: 0px;}
QDialog {background: ${canvas};}

QFrame#panel QFrame#hero {background: ${hero};}
QFrame#panel QFrame#rule {background: ${rule};}
QFrame#sidebar QPushButton#themeSwitch {border-color: #67567c; color: #e8e0f0;}
QComboBox QAbstractItemView {background: ${surface}; color: ${text};
  border: 1px solid ${field_border}; selection-background-color: ${selection}; selection-color: #fff;}
QToolTip {color: ${text}; background: ${surface}; border: 1px solid ${field_border};}
QLabel[stage] {border-radius: 7px; font-size: 10px; font-weight: 750; padding: 4px 8px;}
""")

LIGHT_BADGES = {
    "Proposed": ("#f0ebf7", "#5f437a"), "In Committee": ("#f7edd3", "#745313"),
    "On Floor": ("#e7edff", "#394c8d"), "Passed": ("#e6ecff", "#344986"),
    "Failed": ("#f7e5e7", "#8b364b"), "Enacted": ("#e3f0e7", "#2c634a"),
}
DARK_BADGES = {
    "Proposed": ("#3b2c4b", "#e1c5f8"), "In Committee": ("#493820", "#f8dca4"),
    "On Floor": ("#293957", "#c9dbff"), "Passed": ("#2d3659", "#cfdaff"),
    "Failed": ("#492935", "#ffc7d0"), "Enacted": ("#263f35", "#b8eaca"),
}


def apply_theme(app, theme):
    dark = theme == "dark"
    colors = {name: pair[dark] for name, pair in COLORS.items()}
    role = QPalette.ColorRole
    palette = QPalette()
    for palette_role, color in {
        role.Window: colors["canvas"], role.WindowText: colors["text"],
        role.Base: colors["surface"], role.AlternateBase: colors["row_hover"],
        role.Text: colors["text"], role.PlaceholderText: colors["muted"],
        role.Button: colors["surface"], role.ButtonText: colors["text"],
        role.ToolTipBase: colors["surface"], role.ToolTipText: colors["text"],
        role.BrightText: colors["title"], role.Link: colors["link"],
        role.Highlight: colors["selection"], role.HighlightedText: "#ffffff",
    }.items():
        palette.setColor(palette_role, QColor(color))
    for palette_role in (role.Text, role.WindowText, role.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, palette_role, QColor(colors["disabled_text"]))
    app.setPalette(palette)
    badges = DARK_BADGES if dark else LIGHT_BADGES
    rules = [
        f'QFrame#panel QLabel[stage="{stage}"] {{ background-color: {background}; color: {text}; }}'
        for stage, (background, text) in badges.items()
    ]
    app.setStyleSheet(STYLE.substitute(colors) + "\n".join(rules))
