pragma Singleton

import QtQuick

QtObject {
    id: theme

    property string mode: "light"

    readonly property color bg: mode === "light" ? "#F5F7FA" : (mode === "blue" ? "#EEF4FF" : "#0F172A")
    readonly property color panel: mode === "light" ? "#FFFFFF" : (mode === "blue" ? "#F8FBFF" : "#1E293B")
    readonly property color panelAlt: mode === "light" ? "#EEF2F7" : (mode === "blue" ? "#E7EEF9" : "#162032")
    readonly property color primary: "#1D4ED8"
    readonly property color primaryHover: "#2563EB"
    readonly property color secondary: mode === "dark" ? "#38BDF8" : "#0F766E"
    readonly property color text: mode === "dark" ? "#E2E8F0" : "#111827"
    readonly property color muted: mode === "dark" ? "#94A3B8" : "#64748B"
    readonly property color border: mode === "dark" ? "#334155" : "#D6DEE8"
    readonly property color hover: mode === "dark" ? "#252F45" : "#E8EEF7"
    readonly property color success: "#15803D"
    readonly property color warning: "#B45309"
    readonly property color danger: "#DC2626"
    readonly property color cleanTag: "#0F766E"
    readonly property color genTag: "#B45309"
    readonly property color header: mode === "dark" ? "#1E293B" : "#FFFFFF"
    readonly property color sidebar: mode === "dark" ? "#1E293B" : "#F8FAFC"
    readonly property color control: mode === "dark" ? "#111827" : "#FFFFFF"
    readonly property color row: mode === "dark" ? "#131722" : "#FFFFFF"
    readonly property color rowAlt: mode === "dark" ? "#1A202C" : "#F3F6FA"

    function setMode(nextMode) {
        if (nextMode === "light" || nextMode === "dark" || nextMode === "blue") {
            mode = nextMode
        }
    }
}
