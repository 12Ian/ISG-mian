import QtQuick
import QtQuick.Controls
import "."

SpinBox {
    id: control

    implicitWidth: 120
    implicitHeight: 40

    contentItem: Item {
        Text {
            anchors.fill: parent
            anchors.leftMargin: control.down.indicator.width
            anchors.rightMargin: control.up.indicator.width
            text: control.textFromValue(control.value, control.locale)
            color: Theme.text
            font.pixelSize: 13
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }
    }

    up.indicator: Rectangle {
        implicitWidth: 40
        implicitHeight: control.height
        x: control.width - width
        color: control.up.pressed ? Theme.hover : Theme.panel
        border.color: Theme.border
        border.width: 1
        radius: 4

        Text {
            anchors.centerIn: parent
            text: "+"
            color: Theme.text
            font.pixelSize: 24
        }
    }

    down.indicator: Rectangle {
        implicitWidth: 40
        implicitHeight: control.height
        color: control.down.pressed ? Theme.hover : Theme.panel
        border.color: Theme.border
        border.width: 1
        radius: 4

        Text {
            anchors.centerIn: parent
            text: "-"
            color: Theme.text
            font.pixelSize: 24
        }
    }

    background: Rectangle {
        color: Theme.control
        border.color: Theme.border
        border.width: 1
        radius: 4
    }
}
