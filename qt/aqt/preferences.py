# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from typing import Any, cast

import anki.lang
import aqt
import aqt.forms
import aqt.operations
from anki.collection import OpChanges
from anki.consts import new_card_scheduling_labels
from aqt import AnkiQt
from aqt.operations.collection import set_preferences
from aqt.profiles import VideoDriver
from aqt.qt import *
from aqt.theme import Theme
from aqt.utils import HelpPage, disable_help_button, openHelp, showInfo, showWarning, tr


class Preferences(QDialog):
    def __init__(self, mw: AnkiQt) -> None:
        QDialog.__init__(self, mw, Qt.WindowType.Window)
        self.mw = mw
        self.prof = self.mw.pm.profile
        self.form = aqt.forms.preferences.Ui_Preferences()
        self.form.setupUi(self)
        disable_help_button(self)
        self.form.buttonBox.button(QDialogButtonBox.StandardButton.Help).setAutoDefault(
            False
        )
        self.form.buttonBox.button(
            QDialogButtonBox.StandardButton.Close
        ).setAutoDefault(False)
        qconnect(
            self.form.buttonBox.helpRequested, lambda: openHelp(HelpPage.PREFERENCES)
        )
        self.silentlyClose = True
        self.setup_collection()
        self.setup_profile()
        self.setup_global()
        self.show()

    def accept(self) -> None:
        # avoid exception if main window is already closed
        if not self.mw.col:
            return

        def after_collection_update() -> None:
            self.update_profile()
            self.update_global()
            self.mw.pm.save()
            self.done(0)
            aqt.dialogs.markClosed("Preferences")

        self.update_collection(after_collection_update)

    def reject(self) -> None:
        self.accept()

    # Preferences stored in the collection
    ######################################################################

    def setup_collection(self) -> None:
        self.prefs = self.mw.col.get_preferences()

        form = self.form

        scheduling = self.prefs.scheduling

        version = scheduling.scheduler_version
        form.dayLearnFirst.setVisible(version == 2)
        form.legacy_timezone.setVisible(version >= 2)
        form.newSpread.setVisible(version < 3)
        form.sched2021.setVisible(version >= 2)

        form.lrnCutoff.setValue(int(scheduling.learn_ahead_secs / 60.0))
        form.newSpread.addItems(list(new_card_scheduling_labels(self.mw.col).values()))
        form.newSpread.setCurrentIndex(scheduling.new_review_mix)
        form.dayLearnFirst.setChecked(scheduling.day_learn_first)
        form.dayOffset.setValue(scheduling.rollover)
        form.legacy_timezone.setChecked(not scheduling.new_timezone)
        form.sched2021.setChecked(version == 3)

        reviewing = self.prefs.reviewing
        form.timeLimit.setValue(int(reviewing.time_limit_secs / 60.0))
        form.showEstimates.setChecked(reviewing.show_intervals_on_buttons)
        form.showProgress.setChecked(reviewing.show_remaining_due_counts)
        form.showPlayButtons.setChecked(not reviewing.hide_audio_play_buttons)
        form.interrupt_audio.setChecked(reviewing.interrupt_audio_when_answering)

        editing = self.prefs.editing
        form.useCurrent.setCurrentIndex(
            0 if editing.adding_defaults_to_current_deck else 1
        )
        form.paste_strips_formatting.setChecked(editing.paste_strips_formatting)
        form.ignore_accents_in_search.setChecked(editing.ignore_accents_in_search)
        form.pastePNG.setChecked(editing.paste_images_as_png)
        form.default_search_text.setText(editing.default_search_text)

        form.backup_explanation.setText(
            anki.lang.with_collapsed_whitespace(tr.preferences_backup_explanation())
        )
        form.daily_backups.setValue(self.prefs.backups.daily)
        form.weekly_backups.setValue(self.prefs.backups.weekly)
        form.monthly_backups.setValue(self.prefs.backups.monthly)
        form.minutes_between_backups.setValue(self.prefs.backups.minimum_interval_mins)

    def update_collection(self, on_done: Callable[[], None]) -> None:
        form = self.form

        scheduling = self.prefs.scheduling
        scheduling.new_review_mix = cast(Any, form.newSpread.currentIndex())
        scheduling.learn_ahead_secs = form.lrnCutoff.value() * 60
        scheduling.day_learn_first = form.dayLearnFirst.isChecked()
        scheduling.rollover = form.dayOffset.value()
        scheduling.new_timezone = not form.legacy_timezone.isChecked()

        reviewing = self.prefs.reviewing
        reviewing.show_remaining_due_counts = form.showProgress.isChecked()
        reviewing.show_intervals_on_buttons = form.showEstimates.isChecked()
        reviewing.time_limit_secs = form.timeLimit.value() * 60
        reviewing.hide_audio_play_buttons = not self.form.showPlayButtons.isChecked()
        reviewing.interrupt_audio_when_answering = self.form.interrupt_audio.isChecked()

        editing = self.prefs.editing
        editing.adding_defaults_to_current_deck = not form.useCurrent.currentIndex()
        editing.paste_images_as_png = self.form.pastePNG.isChecked()
        editing.paste_strips_formatting = self.form.paste_strips_formatting.isChecked()
        editing.default_search_text = self.form.default_search_text.text()
        editing.ignore_accents_in_search = (
            self.form.ignore_accents_in_search.isChecked()
        )

        self.prefs.backups.daily = form.daily_backups.value()
        self.prefs.backups.weekly = form.weekly_backups.value()
        self.prefs.backups.monthly = form.monthly_backups.value()
        self.prefs.backups.minimum_interval_mins = form.minutes_between_backups.value()

        def after_prefs_update(changes: OpChanges) -> None:
            self.mw.apply_collection_options()
            if scheduling.scheduler_version > 1:
                want_v3 = form.sched2021.isChecked()
                if self.mw.col.v3_scheduler() != want_v3:
                    self.mw.col.set_v3_scheduler(want_v3)

            on_done()

        set_preferences(parent=self, preferences=self.prefs).success(
            after_prefs_update
        ).run_in_background()

    # Preferences stored in the profile
    ######################################################################

    def setup_profile(self) -> None:
        "Setup options stored in the user profile."
        self.setup_network()

    def update_profile(self) -> None:
        self.update_network()

    # Profile: network
    ######################################################################

    def setup_network(self) -> None:
        self.form.media_log.setText(tr.sync_media_log_button())
        qconnect(self.form.media_log.clicked, self.on_media_log)
        self.form.syncOnProgramOpen.setChecked(self.prof["autoSync"])
        self.form.syncMedia.setChecked(self.prof["syncMedia"])
        self.form.autoSyncMedia.setChecked(self.mw.pm.auto_sync_media_minutes() != 0)
        if not self.prof["syncKey"]:
            self._hide_sync_auth_settings()
        else:
            self.form.syncUser.setText(self.prof.get("syncUser", ""))
            qconnect(self.form.syncDeauth.clicked, self.sync_logout)
        self.form.syncDeauth.setText(tr.sync_log_out_button())

    def on_media_log(self) -> None:
        self.mw.media_syncer.show_sync_log()

    def _hide_sync_auth_settings(self) -> None:
        self.form.syncDeauth.setVisible(False)
        self.form.syncUser.setText("")
        self.form.syncLabel.setText(
            tr.preferences_synchronizationnot_currently_enabled_click_the_sync()
        )

    def sync_logout(self) -> None:
        if self.mw.media_syncer.is_syncing():
            showWarning("Can't log out while sync in progress.")
            return
        self.prof["syncKey"] = None
        self.mw.col.media.force_resync()
        self._hide_sync_auth_settings()

    def update_network(self) -> None:
        self.prof["autoSync"] = self.form.syncOnProgramOpen.isChecked()
        self.prof["syncMedia"] = self.form.syncMedia.isChecked()
        self.mw.pm.set_auto_sync_media_minutes(
            self.form.autoSyncMedia.isChecked() and 15 or 0
        )
        if self.form.fullSync.isChecked():
            self.mw.col.mod_schema(check=False)

    # Global preferences
    ######################################################################

    def setup_global(self) -> None:
        "Setup options global to all profiles."
        self.form.reduce_motion.setChecked(self.mw.pm.reduced_motion())
        self.form.collapse_toolbar.setChecked(self.mw.pm.collapse_toolbar())
        self.form.uiScale.setValue(int(self.mw.pm.uiScale() * 100))
        themes = [
            tr.preferences_theme_label(theme=theme)
            for theme in (
                tr.preferences_theme_follow_system(),
                tr.preferences_theme_light(),
                tr.preferences_theme_dark(),
            )
        ]
        self.form.theme.addItems(themes)
        self.form.theme.setCurrentIndex(self.mw.pm.theme().value)
        qconnect(self.form.theme.currentIndexChanged, self.on_theme_changed)
        self.form.legacy_import_export.setChecked(self.mw.pm.legacy_import_export())

        self.setup_language()
        self.setup_video_driver()

        self.setupOptions()

    def update_global(self) -> None:
        restart_required = False

        self.update_video_driver()

        newScale = self.form.uiScale.value() / 100
        if newScale != self.mw.pm.uiScale():
            self.mw.pm.setUiScale(newScale)
            restart_required = True

        self.mw.pm.set_reduced_motion(self.form.reduce_motion.isChecked())
        self.mw.pm.set_collapse_toolbar(self.form.collapse_toolbar.isChecked())
        self.mw.pm.set_legacy_import_export(self.form.legacy_import_export.isChecked())

        if restart_required:
            showInfo(tr.preferences_changes_will_take_effect_when_you())

        self.updateOptions()

    def on_theme_changed(self, index: int) -> None:
        self.mw.set_theme(Theme(index))

    # legacy - one of Henrik's add-ons is currently wrapping them

    def setupOptions(self) -> None:
        pass

    def updateOptions(self) -> None:
        pass

    # Global: language
    ######################################################################

    def setup_language(self) -> None:
        f = self.form
        f.lang.addItems([x[0] for x in anki.lang.langs])
        f.lang.setCurrentIndex(self.current_lang_index())
        qconnect(f.lang.currentIndexChanged, self.on_language_index_changed)

    def current_lang_index(self) -> int:
        codes = [x[1] for x in anki.lang.langs]
        lang = anki.lang.current_lang
        if lang in anki.lang.compatMap:
            lang = anki.lang.compatMap[lang]
        else:
            lang = lang.replace("-", "_")
        try:
            return codes.index(lang)
        except:
            return codes.index("en_US")

    def on_language_index_changed(self, idx: int) -> None:
        code = anki.lang.langs[idx][1]
        self.mw.pm.setLang(code)
        showInfo(tr.preferences_please_restart_anki_to_complete_language(), parent=self)

    # Global: video driver
    ######################################################################

    def setup_video_driver(self) -> None:
        self.video_drivers = VideoDriver.all_for_platform()
        names = [
            tr.preferences_video_driver(driver=video_driver_name_for_platform(d))
            for d in self.video_drivers
        ]
        self.form.video_driver.addItems(names)
        self.form.video_driver.setCurrentIndex(
            self.video_drivers.index(self.mw.pm.video_driver())
        )
        self.form.video_driver.setVisible(qtmajor == 5)

    def update_video_driver(self) -> None:
        new_driver = self.video_drivers[self.form.video_driver.currentIndex()]
        if new_driver != self.mw.pm.video_driver():
            self.mw.pm.set_video_driver(new_driver)
            showInfo(tr.preferences_changes_will_take_effect_when_you())


def video_driver_name_for_platform(driver: VideoDriver) -> str:
    if driver == VideoDriver.ANGLE:
        return tr.preferences_video_driver_angle()
    elif driver == VideoDriver.Software:
        if is_mac:
            return tr.preferences_video_driver_software_mac()
        else:
            return tr.preferences_video_driver_software_other()
    else:
        if is_mac:
            return tr.preferences_video_driver_opengl_mac()
        else:
            return tr.preferences_video_driver_opengl_other()
