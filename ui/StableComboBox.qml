pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import "."

ComboBox {
    id: control
    implicitHeight: 40

    background: Rectangle {
        color: Theme.control
        border.color: Theme.border
        border.width: 1
        radius: 4
    }

    contentItem: Text {
        text: control.displayText
        color: Theme.text
        font.pixelSize: 13
        verticalAlignment: Text.AlignVCenter
        leftPadding: 12
        rightPadding: 36
        elide: Text.ElideRight
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

        width: control.width - 20
        height: 36

        contentItem: Text {
            text: control.textAt(optionDelegate.index)
            color: Theme.text
            font.pixelSize: 13
            verticalAlignment: Text.AlignVCenter
            leftPadding: 12
            elide: Text.ElideRight
        }

        background: Rectangle {
            radius: 4
            color: optionDelegate.highlighted || optionDelegate.hovered ? Theme.hover : "transparent"
        }
    }
}
