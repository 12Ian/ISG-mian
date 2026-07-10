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
            context.clearRect(0, 0, width, height)
            context.strokeStyle = Theme.text
            context.lineWidth = 2
            context.lineCap = "round"
            context.beginPath()
            context.moveTo(1, 1)
            context.lineTo(width / 2, height - 1)
            context.lineTo(width - 1, 1)
            context.stroke()
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
            clip: true
            implicitHeight: Math.min(contentHeight, 300)
            model: control.delegateModel
            currentIndex: control.highlightedIndex
            ScrollIndicator.vertical: ScrollIndicator {}
        }
    }

    delegate: ItemDelegate {
        id: optionDelegate
        required property int index

        width: control.width - 8
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
