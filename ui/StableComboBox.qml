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
        Text {
            id: selectedText
            text: control.displayText
            color: Theme.text
            font.pixelSize: 13
            width: Math.max(selectedClip.width - 48, implicitWidth)
            height: selectedClip.height
            verticalAlignment: Text.AlignVCenter
            x: 12
            SequentialAnimation on x {
                loops: Animation.Infinite
                running: control.marqueeText && selectedText.implicitWidth > selectedClip.width - 48
                PauseAnimation { duration: 900 }
                NumberAnimation { to: -(selectedText.implicitWidth - selectedClip.width + 36); duration: 1800; easing.type: Easing.InOutQuad }
                PauseAnimation { duration: 900 }
                NumberAnimation { to: 12; duration: 500; easing.type: Easing.InOutQuad }
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
        width: Math.max(control.width, 280)
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

        width: popupList.width - 8
        height: 36

        contentItem: Item {
            id: optionClip
            clip: true
            Text {
                id: optionText
                text: control.textAt(optionDelegate.index)
                color: Theme.text
                font.pixelSize: 13
                width: implicitWidth
                height: optionClip.height
                verticalAlignment: Text.AlignVCenter
                x: 12
                SequentialAnimation on x {
                    loops: Animation.Infinite
                    running: control.marqueeText && optionText.implicitWidth > optionClip.width - 24
                    PauseAnimation { duration: 700 }
                    NumberAnimation { to: -(optionText.implicitWidth - optionClip.width + 24); duration: 1800; easing.type: Easing.InOutQuad }
                    PauseAnimation { duration: 700 }
                    NumberAnimation { to: 12; duration: 500; easing.type: Easing.InOutQuad }
                }
            }
        }

        background: Rectangle {
            radius: 4
            color: optionDelegate.highlighted || optionDelegate.hovered ? Theme.hover : "transparent"
        }
    }
}
