pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import "."

ComboBox {
    id: control
    implicitHeight: 40
    property bool marqueeText: false

    background: Rectangle {
        color: Theme.control
        border.color: Theme.border
        border.width: 1
        radius: 4
    }

    contentItem: Item {
        id: selectedClip
        clip: true
        Item {
            id: selectedViewport
            x: 12
            width: Math.max(0, selectedClip.width - 48)
            height: selectedClip.height
            clip: true

            Text {
                id: selectedText
                property bool shouldMarquee: control.marqueeText && implicitWidth > selectedViewport.width
                property real scrollDistance: Math.max(0, implicitWidth - selectedViewport.width)
                property int scrollDuration: Math.max(3200, Math.round(scrollDistance * 36))
                text: control.displayText
                color: Theme.text
                font.pixelSize: 13
                width: shouldMarquee ? implicitWidth : selectedViewport.width
                height: selectedViewport.height
                verticalAlignment: Text.AlignVCenter
                elide: control.marqueeText ? Text.ElideNone : Text.ElideRight
                SequentialAnimation on x {
                    id: selectedMarquee
                    loops: Animation.Infinite
                    running: selectedText.shouldMarquee
                    PauseAnimation { duration: 900 }
                    NumberAnimation {
                        to: selectedViewport.width - selectedText.implicitWidth
                        duration: selectedText.scrollDuration
                        easing.type: Easing.Linear
                    }
                    PauseAnimation { duration: 900 }
                    NumberAnimation { to: 0; duration: selectedText.scrollDuration; easing.type: Easing.Linear }
                }
            }

            Connections {
                target: control
                function onCurrentTextChanged() {
                    selectedMarquee.stop()
                    selectedText.x = 0
                    if (selectedText.shouldMarquee) selectedMarquee.start()
                }
            }
        }
    }

    indicator: Canvas {
        id: indicatorCanvas
        x: control.width - width - 12
        y: (control.height - height) / 2
        width: 12
        height: 8
        contextType: "2d"

        Connections {
            target: control
            function onPressedChanged() { indicatorCanvas.requestPaint() }
        }

        Connections {
            target: Theme
            function onTextChanged() { indicatorCanvas.requestPaint() }
        }

        onPaint: {
            var ctx = getContext("2d")
            if (!ctx)
                return
            ctx.clearRect(0, 0, width, height)
            ctx.strokeStyle = Theme.text
            ctx.lineWidth = 2
            ctx.lineCap = "round"
            ctx.beginPath()
            ctx.moveTo(1, 1)
            ctx.lineTo(width / 2, height - 1)
            ctx.lineTo(width - 1, 1)
            ctx.stroke()
        }
    }

    popup: Popup {
        y: control.height + 2
        width: control.width
        padding: 4
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutsideParent

        background: Rectangle {
            color: Theme.panel
            border.color: Theme.border
            radius: 6
        }

        contentItem: ListView {
            id: popupList
            clip: true
            implicitHeight: Math.min(contentHeight, 300)
            model: control.delegateModel
            currentIndex: control.highlightedIndex
            boundsBehavior: Flickable.StopAtBounds

            ScrollBar.vertical: ScrollBar {
                id: popupScrollBar
                width: 12
                policy: popupList.contentHeight > popupList.height ? ScrollBar.AlwaysOn : ScrollBar.AlwaysOff
                interactive: true
                hoverEnabled: true
                active: true
            }
        }
    }

    delegate: ItemDelegate {
        id: optionDelegate
        required property int index

        width: popupList.width
        height: 36

        contentItem: Item {
            id: optionClip
            clip: true
            Item {
                id: optionViewport
                x: 12
                width: Math.max(0, optionClip.width - 24)
                height: optionClip.height
                clip: true

                Text {
                    id: optionText
                    property bool shouldMarquee: control.marqueeText && implicitWidth > optionViewport.width
                    property real scrollDistance: Math.max(0, implicitWidth - optionViewport.width)
                    property int scrollDuration: Math.max(3200, Math.round(scrollDistance * 36))
                    text: control.textAt(optionDelegate.index)
                    color: Theme.text
                    font.pixelSize: 13
                    width: shouldMarquee ? implicitWidth : optionViewport.width
                    height: optionViewport.height
                    verticalAlignment: Text.AlignVCenter
                    elide: control.marqueeText ? Text.ElideNone : Text.ElideRight
                    SequentialAnimation on x {
                        loops: Animation.Infinite
                        running: optionText.shouldMarquee
                        PauseAnimation { duration: 700 }
                        NumberAnimation {
                            to: optionViewport.width - optionText.implicitWidth
                            duration: optionText.scrollDuration
                            easing.type: Easing.Linear
                        }
                        PauseAnimation { duration: 700 }
                        NumberAnimation { to: 0; duration: optionText.scrollDuration; easing.type: Easing.Linear }
                    }
                }
            }
        }

        background: Rectangle {
            radius: 4
            color: optionDelegate.highlighted || optionDelegate.hovered ? Theme.hover : "transparent"
        }
    }
}
