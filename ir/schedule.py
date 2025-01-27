# Copyright 2013 Tiago Barroso
# Copyright 2013 Frank Kmiec
# Copyright 2013-2016 Aleksej
# Copyright 2017 Christian Weiß
# Copyright 2018 Timothée Chauvin
# Copyright 2017-2019 Joseph Lorimer <joseph@lorimer.me>
#
# Permission to use, copy, modify, and distribute this software for any purpose
# with or without fee is hereby granted, provided that the above copyright
# notice and this permission notice appear in all copies.
#
# THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH
# REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY
# AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT,
# INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM
# LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR
# OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR
# PERFORMANCE OF THIS SOFTWARE.

# pylint: disable=import-error,invalid-name,no-name-in-module,no-member,protected-access,missing-docstring

from random import gauss, shuffle
from re import sub

from anki.consts import QUEUE_TYPE_SUSPENDED
from anki.utils import stripHTML
from aqt import mw
from aqt.utils import showInfo, tooltip
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from .util import showBrowser

SCHEDULE_EXTRACT = 0
SCHEDULE_SOON = 1
SCHEDULE_SOONISH = 2
SCHEDULE_LATER = 3
SCHEDULE_MUCHLATER = 4
SCHEDULE_CUSTOM = 6
SCHEDULE_NEVER = 8


class Scheduler:
    did = None
    cardListWidget = None

    def showDialog(self, currentCard=None):
        if currentCard:
            self.did = currentCard.did
        elif mw._selectedDeck():
            self.did = mw._selectedDeck()["id"]
        else:
            return

        if not self._getCardInfo(self.did):
            showInfo("Please select an Incremental Reading deck.")
            return

        dialog = QDialog(mw)
        layout = QVBoxLayout()
        self.cardListWidget = QListWidget()
        self.cardListWidget.setAlternatingRowColors(True)
        self.cardListWidget.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.cardListWidget.setWordWrap(True)
        self.cardListWidget.itemDoubleClicked.connect(
            lambda: showBrowser(
                self.cardListWidget.currentItem().data(Qt.UserRole)["nid"]
            )
        )

        self._updateListItems()

        upButton = QPushButton("Up")
        upButton.clicked.connect(self._moveUp)
        downButton = QPushButton("Down")
        downButton.clicked.connect(self._moveDown)
        topButton = QPushButton("Top")
        topButton.clicked.connect(self._moveToTop)
        bottomButton = QPushButton("Bottom")
        bottomButton.clicked.connect(self._moveToBottom)
        randomizeButton = QPushButton("Randomize")
        randomizeButton.clicked.connect(self._randomize)

        controlsLayout = QHBoxLayout()
        controlsLayout.addWidget(topButton)
        controlsLayout.addWidget(upButton)
        controlsLayout.addWidget(downButton)
        controlsLayout.addWidget(bottomButton)
        controlsLayout.addStretch()
        controlsLayout.addWidget(randomizeButton)

        buttonBox = QDialogButtonBox(QDialogButtonBox.Close | QDialogButtonBox.Save)
        buttonBox.accepted.connect(dialog.accept)
        buttonBox.rejected.connect(dialog.reject)
        buttonBox.setOrientation(Qt.Horizontal)

        layout.addLayout(controlsLayout)
        layout.addWidget(self.cardListWidget)
        layout.addWidget(buttonBox)

        dialog.setLayout(layout)
        dialog.setWindowModality(Qt.WindowModal)
        dialog.resize(500, 500)
        choice = dialog.exec_()

        if choice == 1:
            cids = []
            for i in range(self.cardListWidget.count()):
                card = self.cardListWidget.item(i).data(Qt.UserRole)
                cids.append(card["id"])

            self.reorder(cids)

    def _updateListItems(self):
        # Checking if CardListWidget is None is a workaround for the following error:
        # Which unfortunately does not always work because the underlying C++ object
        # is the thing that gets deleted, not the python object.
        #         Traceback (most recent call last):
        #   File "aqt/webview.py", line 493, in handler
        #   File "aqt/editor.py", line 483, in <lambda>
        #   File "</Applications/Anki.app/Contents/MacOS/decorator.pyc:decorator-gen-70>", line 2, in _closeWindow
        #   File "anki/hooks.py", line 638, in decorator_wrapper
        #   File "anki/hooks.py", line 630, in repl
        #   File "/Users/cjon/Library/Application Support/Anki2/addons21/ir/main.py", line 250, in onBrowserClosed
        #     Reviewer._answerButtonList = wrap(
        #   File "/Users/cjon/Library/Application Support/Anki2/addons21/ir/schedule.py", line 127, in _updateListItems
        #     self.cardListWidget.clear()
        # RuntimeError: wrapped C/C++ object of type QListWidget has been deleted
        if self.cardListWidget is None:
            return
        cardInfo = self._getCardInfo(self.did)
        self.cardListWidget.clear()
        posWidth = len(str(len(cardInfo) + 1))
        for i, card in enumerate(cardInfo, start=1):
            if self.settings["prioEnabled"]:
                info = card["priority"]
            else:
                info = str(i).zfill(posWidth)
            title = sub(r"\s+", " ", stripHTML(card["title"]))
            try:
                text = self.settings["organizerFormat"].format(info=info, title=title)
            except KeyError as keyerror:
                tooltip(f"KeyError in _updateListItems: {keyerror}")
                text = str(title)

            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, card)
            self.cardListWidget.addItem(item)

    def _moveToTop(self):
        selected = self._getSelected()
        if not selected:
            showInfo("Please select one or several items.")
            return

        selected.reverse()
        for item in selected:
            self.cardListWidget.takeItem(self.cardListWidget.row(item))
            self.cardListWidget.insertItem(0, item)
            item.setSelected(True)

        self.cardListWidget.scrollToTop()

    def _moveUp(self):
        selected = self._getSelected()
        if not selected:
            showInfo("Please select one or several items.")
            return

        if self.cardListWidget.row(selected[0]) == 0:
            return

        for item in selected:
            row = self.cardListWidget.row(item)
            self.cardListWidget.takeItem(row)
            self.cardListWidget.insertItem(row - 1, item)
            item.setSelected(True)
            self.cardListWidget.scrollToItem(item)

    def _moveDown(self):
        selected = self._getSelected()
        if not selected:
            showInfo("Please select one or several items.")
            return

        selected.reverse()

        if self.cardListWidget.row(selected[0]) == self.cardListWidget.count() - 1:
            return

        for item in selected:
            row = self.cardListWidget.row(item)
            self.cardListWidget.takeItem(row)
            self.cardListWidget.insertItem(row + 1, item)
            item.setSelected(True)
            self.cardListWidget.scrollToItem(item)

    def _moveToBottom(self):
        selected = self._getSelected()
        if not selected:
            showInfo("Please select one or several items.")
            return

        for item in selected:
            self.cardListWidget.takeItem(self.cardListWidget.row(item))
            self.cardListWidget.insertItem(self.cardListWidget.count(), item)
            item.setSelected(True)

        self.cardListWidget.scrollToBottom()

    def _getSelected(self):
        return [
            self.cardListWidget.item(i)
            for i in range(self.cardListWidget.count())
            if self.cardListWidget.item(i).isSelected()
        ]

    def _randomize(self):
        allItems = [
            self.cardListWidget.takeItem(0) for _ in range(self.cardListWidget.count())
        ]
        if self.settings["prioEnabled"]:
            maxPrio = len(self.settings["priorities"]) - 1
            for item in allItems:
                priority = item.data(Qt.UserRole)["priority"]
                if priority != "":
                    item.contNewPos = gauss(maxPrio - int(priority), maxPrio / 20)
                else:
                    item.contNewPos = float("inf")
            allItems.sort(key=lambda item: item.contNewPos)

        else:
            shuffle(allItems)

        for item in allItems:
            self.cardListWidget.addItem(item)

    def answer(self, card, ease, old_func):
        if self.settings["prioEnabled"]:
            # reposition the card at the end of the organizer
            cardCount = len(self._getCardInfo(card.did))
            self.reposition(card, cardCount)
            return

        if ease == SCHEDULE_EXTRACT:
            value = self.settings["extractValue"]
            randomize = self.settings["extractRandom"]
            method = self.settings["extractMethod"]
        elif ease == SCHEDULE_SOON:  # 1
            value = self.settings["soonValue"]
            randomize = self.settings["soonRandom"]
            method = self.settings["soonMethod"]
        elif ease == SCHEDULE_SOONISH:  # 2
            value = self.settings["soonishValue"]
            randomize = self.settings["soonishRandom"]
            method = self.settings["soonishMethod"]
        elif ease == SCHEDULE_LATER:  # 3
            value = self.settings["laterValue"]
            randomize = self.settings["laterRandom"]
            method = self.settings["laterMethod"]
        elif ease == SCHEDULE_MUCHLATER:  # 4
            value = self.settings["muchLaterValue"]
            randomize = self.settings["muchLaterRandom"]
            method = self.settings["muchLaterMethod"]
        elif ease == SCHEDULE_NEVER:  # 5 (shortcut does not work)
            value = 90
            randomize = True
            method = "percent"
        elif ease == SCHEDULE_CUSTOM:  # 6 (shortcut also does not work)
            self.reposition(card, 1)
            self.showDialog(card)
            return

        if ease > 4:
            ease = 4

        old_func(ease)

        if method == "percent":
            totalCards = len([c["id"] for c in self._getCardInfo(card.did)])
            newPos = totalCards * (value / 100)
        elif method == "count":
            newPos = value

        if randomize:
            newPos = gauss(newPos, newPos / 10)

        newPos = max(1, round(newPos))
        self.reposition(card, newPos)

        if ease != SCHEDULE_EXTRACT:
            tooltip("Card moved to position {}".format(newPos))

    def reposition(self, card, newPos):
        cids = [c["id"] for c in self._getCardInfo(card.did)]
        mw.col.sched.forgetCards(cids)
        cids.remove(card.id)
        newOrder = cids[: newPos - 1] + [card.id] + cids[newPos - 1 :]
        mw.col.sched.sortCards(newOrder)

    def reorder(self, cids):
        mw.col.sched.forgetCards(cids)
        mw.col.sched.sortCards(cids)

    def get_button_interval(self, ease):
        # XXX Hardcoded values, maybe allow setting in gui?
        # withot knowing how many cards the user reviws per day
        # and how often he presses each button, it is hard to
        # come up with good values
        # Q: Could I get that info fram stats and deck options?
        if ease == SCHEDULE_SOON:  # 1
            return "1d"
        if ease == SCHEDULE_SOONISH:  # 2
            return "2-4d"
        if ease == SCHEDULE_LATER:  # 3
            return "8-12d"
        if ease == SCHEDULE_MUCHLATER:  # 4
            return "~20d"
        if ease == SCHEDULE_NEVER:  # 5 (shortcut does not work)
            return "Never"
        if ease == SCHEDULE_CUSTOM:  # 6 (shortcut also does not work)
            return "Custom"
        return "&nbsp;"

    def buttonTime(self, i):
        if not mw.col.conf["estTimes"]:
            return "<div class=spacer></div>"
        txt = self.get_button_interval(i)
        return f"<span class=nobold>{txt}</span><br>"

    def _getCardInfo(self, did):
        cardInfo = []

        for cid, nid in mw.col.db.execute(
            f"select id, nid from cards where did = ? and queue <> {QUEUE_TYPE_SUSPENDED}",
            did,
        ):
            note = mw.col.getNote(nid)
            if note.model()["name"] == self.settings["modelName"]:
                if self.settings["prioEnabled"]:
                    prio = note[self.settings["prioField"]]
                else:
                    prio = None

                cardInfo.append(
                    {
                        "id": cid,
                        "nid": nid,
                        "title": note[self.settings["titleField"]],
                        "priority": prio,
                    }
                )

        return cardInfo
