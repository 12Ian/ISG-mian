import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import ".."

Item {
    id: root
    anchors.fill: parent

    // ==========================================
    // 全局简洁主题规范
    // ==========================================
    readonly property color bgDark: Theme.bg
    readonly property color panelBg: Theme.panel
    readonly property color devAccentColor: Theme.primary
    readonly property color devAccentMuted: Theme.secondary

    readonly property color primaryColor: Theme.primary
    readonly property color textColor: Theme.text
    readonly property color textMuted: Theme.muted
    readonly property color borderColor: Theme.border
    readonly property color successColor: Theme.success
    readonly property color dangerColor: Theme.danger
    readonly property color tableHoverBg: Theme.hover
    readonly property color cleanTagColor: Theme.cleanTag
    readonly property color genTagColor: Theme.genTag

    HelpIcon {
        anchors.top: parent.top
        anchors.right: parent.right
        anchors.topMargin: -16
        anchors.rightMargin: -16
        title: "算法配置帮助"
        body: "在本页注册、修改或卸载自定义算法插件。左侧选择算法，右侧查看脚本路径、接口说明、使用说明和参数快照；完整规范见 docs/ALGORITHM_USAGE_GUIDE.md。"
    }

    // 状态控制
    property int pendingEditIndex: -1
    property int pendingDeleteIndex: -1

    // 分类折叠面板状态
    property int selectedAlgoId: -1
    property bool cleaningExpanded: true
    property bool generationExpanded: true
    property bool evaluationExpanded: true
    property bool trainingExpanded: true
    property int cleaningCount: 0
    property int generationCount: 0
    property int evaluationCount: 0
    property int trainingCount: 0
    property int totalAlgoCount: 0

    function findAlgoIndexById(algoId) {
        for (var i = 0; i < algoListModel.count; i++) {
            if (algoListModel.get(i).id === algoId) return i
        }
        return -1
    }

    readonly property int selectedAlgoIndex: root.findAlgoIndexById(root.selectedAlgoId)

    function selectedAlgoField(field) {
        var idx = root.selectedAlgoIndex
        if (idx === -1) return ""
        var d = algoListModel.get(idx)
        return d[field] !== undefined ? d[field] : ""
    }

    // ================= 背景 =================
    Rectangle {
        anchors.fill: parent
        color: root.bgDark
        Canvas {
            anchors.fill: parent
            visible: Theme.mode === "dark"
            opacity: 0.02
            onPaint: {
                var ctx = getContext("2d");
                ctx.strokeStyle = root.devAccentColor;
                ctx.lineWidth = 1;
                for (var x = 0; x < width; x += 30) {
                    ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, height); ctx.stroke();
                }
                for (var y = 0; y < height; y += 30) {
                    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(width, y); ctx.stroke();
                }
            }
        }
    }

    // ================= 数据模型 =================
    ListModel {
        id: algoListModel
    }

    ListModel { id: cleaningAlgoModel }
    ListModel { id: generationAlgoModel }
    ListModel { id: evaluationAlgoModel }
    ListModel { id: trainingAlgoModel }

    ListModel {
        id: editingParamsModel
    }

    // 共享算法列表项委托
    Component {
        id: algoItemDelegate
        Rectangle {
            width: parent ? parent.width : 260
            height: 64
            radius: 0
            color: {
                if (model.id === root.selectedAlgoId) return Qt.rgba(29/255, 78/255, 216/255, 0.10)
                if (itemMa.containsMouse) return root.tableHoverBg
                return "transparent"
            }
            border.color: model.id === root.selectedAlgoId ? root.devAccentColor : "transparent"
            border.width: 1

            MouseArea {
                id: itemMa
                anchors.fill: parent
                hoverEnabled: true
                onClicked: root.selectedAlgoId = model.id
            }

            RowLayout {
                anchors.fill: parent
                anchors.margins: 10
                spacing: 12

                Rectangle {
                    width: 34; height: 34; radius: 5
                    color: root.bgDark
                    border.color: model.id === root.selectedAlgoId ? root.devAccentColor : root.borderColor
                    border.width: 1
                    Text {
                        text: {
                            var c = model.category
                            if (c === "清洗算法") return "清"
                            if (c === "生成算法") return "生"
                            if (c === "评估算法") return "评"
                            if (c === "训练算法") return "训"
                            return "?"
                        }
                        color: {
                            var c = model.category
                            if (c === "清洗算法") return root.cleanTagColor
                            if (c === "生成算法") return root.genTagColor
                            return root.devAccentColor
                        }
                        font.pixelSize: 14; font.bold: true; anchors.centerIn: parent
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 3
                    Text {
                        text: model.name
                        color: model.id === root.selectedAlgoId ? root.devAccentColor : root.textColor
                        font.pixelSize: 13; font.bold: true
                        elide: Text.ElideRight; Layout.fillWidth: true
                    }
                    Text {
                        text: model.subCategory
                        color: root.textMuted
                        font.pixelSize: 11
                    }
                }
            }
        }
    }

    // ================= 全局提示 Toast =================
    property string toastMessage: "✅ 操作成功"

    Popup {
        id: toastMsg
        modal: false
        closePolicy: Popup.NoAutoClose
        z: 2147483647
        x: Math.round((root.width - width) / 2)
        y: 40
        height: 40
        leftPadding: 20
        rightPadding: 20
        opacity: 0
        background: Rectangle { color: root.successColor; radius: 20 }
        contentItem: Text {
            id: toastText
            text: root.toastMessage
            color: "black"
            font.pixelSize: 14; font.bold: true
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }
        SequentialAnimation {
            id: toastAnim
            NumberAnimation { target: toastMsg; property: "opacity"; to: 1.0; duration: 300 }
        }
    }

    Timer {
        id: toastCloseTimer
        interval: 2300
        onTriggered: {
            toastMsg.opacity = 0
            toastMsg.close()
        }
    }

    function showToast(msg) {
        root.toastMessage = msg
        toastMsg.open()
        toastAnim.restart()
        toastCloseTimer.restart()
    }

    function categoryLabel(category) {
        if (category === "cleaning") return "清洗算法"
        if (category === "generation") return "生成算法"
        if (category === "evaluation") return "评估算法"
        if (category === "training") return "训练算法"
        return category || "未分类"
    }

    function categoryValue(label) {
        if (label === "清洗算法") return "cleaning"
        if (label === "生成算法") return "generation"
        if (label === "评估算法") return "evaluation"
        return label || "generation"
    }

    function modalityFromSubCategory(text) {
        if (text.indexOf("文本") !== -1) return "text"
        if (text.indexOf("音频") !== -1) return "audio"
        if (text.indexOf("表格") !== -1) return "tabular"
        if (text.indexOf("视频") !== -1) return "video"
        return "image"
    }

    function subtypeLabel(category, modality) {
        if (category === "cleaning") {
            if (modality === "text") return "文本清洗策略"
            if (modality === "audio") return "音频清洗策略"
            if (modality === "tabular") return "表格数据清洗"
            return "图像清洗策略"
        }
        if (modality === "text") return "文本增强方法"
        if (modality === "audio") return "音频增强方法"
        return "图像增强方法"
    }

    function loadAlgorithms() {
        backendService.getAlgorithms("", "")
    }

    function buildAlgorithmPayload(paramsJson) {
        var subCatStr = inputSubCategory.editText.trim() !== "" ? inputSubCategory.editText : inputSubCategory.currentText
        var category = root.categoryValue(inputCategory.currentText)
        var modality = root.modalityFromSubCategory(subCatStr)
        var rawParams = JSON.parse(paramsJson || "[]")
        var params = []
        for (var i = 0; i < rawParams.length; i++) {
            var p = rawParams[i]
            var ptype = p.type || "string"
            var paramDef = {
                name: p.n,
                label: p.label || p.n,
                type: ptype,
                required: false,
                default_value: p.v,
                description: p.desc || ""
            }
            if (ptype === "int" || ptype === "float") {
                paramDef.min_value = p.min !== undefined && p.min !== "" ? parseFloat(p.min) : null
                paramDef.max_value = p.max !== undefined && p.max !== "" ? parseFloat(p.max) : null
            }
            if (ptype === "select" && p.options) {
                paramDef.options = p.options.split(",").map(function(s) { return s.trim() }).filter(function(s) { return s !== "" })
            }
            params.push(paramDef)
        }
        return {
            key: inputAlgoName.text.trim().replace(/\s+/g, "_").toLowerCase(),
            name: inputAlgoName.text.trim(),
            category: category,
            modality: modality,
            entry_type: "python_function",
            script_path: inputScriptPath.text.trim(),
            callable_name: "run",
            description: inputDesc.text,
            input_contract: {"dataset_required": true, "sample_required": true},
            output_contract: {"produces": category === "cleaning" ? ["suggestions"] : ["outputs"], "artifact_types": []},
            parameters: params
        }
    }

    Component.onCompleted: root.loadAlgorithms()
    onVisibleChanged: { if (visible) root.loadAlgorithms() }

    Connections {
        target: backendService
        function onAlgorithmsUpdated(items) {
            if (!root.visible) return  // 只在当前页面可见时处理
            algoListModel.clear()
            cleaningAlgoModel.clear()
            generationAlgoModel.clear()
            evaluationAlgoModel.clear()
            trainingAlgoModel.clear()
            var cCount = 0, gCount = 0, eCount = 0, tCount = 0
            for (var i = 0; i < items.length; i++) {
                var item = items[i]
                var params = []
                var sourceParams = item.parameters || []
                for (var p = 0; p < sourceParams.length; p++) {
                    var sp = sourceParams[p]
                    params.push({
                        "n": sp.name || "",
                        "label": sp.label || sp.name || "",
                        "v": String(sp.default_value !== undefined ? sp.default_value : ""),
                        "type": sp.type || "string",
                        "min": String(sp.min_value !== undefined && sp.min_value !== null ? sp.min_value : ""),
                        "max": String(sp.max_value !== undefined && sp.max_value !== null ? sp.max_value : ""),
                        "options": (sp.options || []).join(", "),
                        "desc": sp.description || ""
                    })
                }
                var entry = {
                    id: item.id,
                    key: item.key,
                    name: item.name,
                    category: root.categoryLabel(item.category),
                    subCategory: root.subtypeLabel(item.category, item.modality),
                    modality: item.modality,
                    script: item.script_path || item.module_path || "",
                    desc: item.description || "",
                    paramsJson: JSON.stringify(params),
                    enabled: item.status === "enabled"
                }
                algoListModel.append(entry)
                if (item.category === "cleaning") {
                    cleaningAlgoModel.append(entry)
                    cCount++
                } else if (item.category === "generation") {
                    generationAlgoModel.append(entry)
                    gCount++
                } else if (item.category === "evaluation") {
                    evaluationAlgoModel.append(entry)
                    eCount++
                } else {
                    trainingAlgoModel.append(entry)
                    tCount++
                }
            }
            root.cleaningCount = cCount
            root.generationCount = gCount
            root.evaluationCount = eCount
            root.trainingCount = tCount
            root.totalAlgoCount = items.length
            if (items.length > 0 && root.selectedAlgoId === -1) {
                root.selectedAlgoId = items[0].id
            }
        }
    }

    function algorithmUsageText(category) {
        if (root.selectedAlgoIndex === -1) {
            return "选择算法后可查看使用说明。完整文档: docs/ALGORITHM_USAGE_GUIDE.md"
        }
        if (category === "清洗算法") {
            return "清洗算法用于发现重复、低质、异常或需脱敏的样本。输入为数据集样本路径和参数字典，输出为清洗建议、置信度和可选处理结果。上线前需确认参数默认值、输出建议类型和失败日志。"
        }
        return "生成算法用于对图像、音频或文本样本做扩增。输入为源样本路径、输出目录和参数字典，输出为新增样本文件及增强元数据。上线前需确认生成数量、输出格式、资源占用和可复现实验参数。"
    }

    // ================= 弹窗：文件选择器 =================
    FileDialog {
        id: scriptFileDialog
        title: "选择算法脚本/程序文件"
        nameFilters: ["Python 脚本 (*.py)"]
        onAccepted: {
            var path = selectedFile.toString()
            var cleanPath = decodeURIComponent(path.replace(/^(file:\/{2,3})/, ""))
            inputScriptPath.text = cleanPath
            var result = backendService.reflectParameters(cleanPath)
            if (result.ok) {
                editingParamsModel.clear()
                var params = result.parameters || []
                for (var i = 0; i < params.length; i++) {
                    var p = params[i]
                    editingParamsModel.append({
                        "n": p.name || "",
                        "label": p.label || p.name || "",
                        "v": String(p.default !== undefined ? p.default : ""),
                        "type": p.type || "string",
                        "min": String(p.min !== undefined && p.min !== null ? p.min : ""),
                        "max": String(p.max !== undefined && p.max !== null ? p.max : ""),
                        "options": (p.options || []).join(", "),
                        "desc": p.description || ""
                    })
                }
                root.showToast("✅ 已自动加载 " + params.length + " 个参数")
            } else {
                root.showToast("⚠️ 参数反射失败: " + (result.error || result.message || "未知错误"))
            }
        }
    }

    // ================= 弹窗：二次确认删除 =================
    Popup {
        id: deleteConfirmPopup
        width: 320
        height: 190
        modal: true
        focus: true
        x: Math.round((root.width - width) / 2)
        y: Math.round((root.height - height) / 2)
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: Rectangle {
            color: root.panelBg
            radius: 8
            border.color: root.dangerColor
            border.width: 1
        }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 20
            spacing: 15

            RowLayout {
                spacing: 10
                Text { text: "⚠️"; font.pixelSize: 20 }
                Text { text: "确认卸载此算法吗？"; color: root.textColor; font.pixelSize: 15; font.bold: true }
            }

            Text {
                text: "卸载后，清洗或生成模块将无法再调用此自定义算法。"
                color: root.textMuted
                font.pixelSize: 12
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }

            Item { Layout.fillHeight: true }

            RowLayout {
                Layout.fillWidth: true
                spacing: 15
                Item { Layout.fillWidth: true }
                Button {
                    text: "取消"
                    Layout.preferredWidth: 80
                    Layout.preferredHeight: 30
                    background: Rectangle { color: "transparent"; border.color: root.borderColor; border.width: 1; radius: 4 }
                    contentItem: Text { text: parent.text; color: root.textMuted; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                    onClicked: deleteConfirmPopup.close()
                }
                Button {
                    text: "确认卸载"
                    Layout.preferredWidth: 80
                    Layout.preferredHeight: 30
                    background: Rectangle { color: root.dangerColor; radius: 4 }
                    contentItem: Text { text: parent.text; color: "black"; font.bold: true; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                    onClicked: {
                        if (root.pendingDeleteIndex !== -1) {
                            var result = backendService.deleteAlgorithm(algoListModel.get(root.pendingDeleteIndex).id)
                            if (result.ok) {
                                root.selectedAlgoId = -1
                                root.loadAlgorithms()
                                root.showToast("🗑️ 算法已成功卸载")
                            } else {
                                root.showToast("⚠️ 算法卸载失败")
                            }
                        }
                        deleteConfirmPopup.close()
                    }
                }
            }
        }
    }

    // ================= 核心弹窗：配置新算法/修改算法 =================
    Popup {
        id: algoConfigPopup
        width: 800
        height: 600
        modal: true
        focus: true
        x: Math.round((root.width - width) / 2)
        y: Math.round((root.height - height) / 2)
        closePolicy: Popup.CloseOnEscape | Popup.NoAutoClose
        background: Rectangle {
            color: root.panelBg
            radius: 8
            border.color: root.devAccentMuted
            border.width: 1
            Rectangle { anchors.fill: parent; color: root.devAccentColor; opacity: 0.02; radius: 8 }
        }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 25
            spacing: 20

            // 标题栏
            RowLayout {
                Layout.fillWidth: true
                Text {
                    text: root.pendingEditIndex === -1 ? "🧩 接入自定义新插件" : "⚙️ 修改插件底层配置"
                    color: root.devAccentColor
                    font.pixelSize: 18
                    font.bold: true
                }
                Item { Layout.fillWidth: true }
                Rectangle {
                    width: 30; height: 30; color: "transparent"; radius: 4
                    Text { text: "✕"; color: root.textMuted; font.pixelSize: 18; anchors.centerIn: parent }
                    MouseArea {
                        anchors.fill: parent; cursorShape: Qt.PointingHandCursor; hoverEnabled: true
                        onEntered: { parent.color = root.tableHoverBg }
                        onExited: { parent.color = "transparent" }
                        onClicked: algoConfigPopup.close()
                    }
                }
            }

            Rectangle { Layout.fillWidth: true; height: 1; color: root.borderColor }

            // 左右分栏：左侧基础信息，右侧动态参数配置
            RowLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 30

                // === 左栏：基础信息 ===
                ColumnLayout {
                    Layout.preferredWidth: 320
                    Layout.fillHeight: true
                    spacing: 15

                    Text { text: "📝 基础映射信息"; color: root.textColor; font.pixelSize: 14; font.bold: true }

                    ColumnLayout {
                        spacing: 6; Layout.fillWidth: true
                        Text { text: "插件名称:"; color: root.textMuted; font.pixelSize: 12 }
                        Rectangle {
                            Layout.fillWidth: true; height: 36; color: root.bgDark; radius: 4; border.color: root.borderColor; border.width: 1
                            TextInput { id: inputAlgoName; color: root.textColor; font.pixelSize: 13; anchors.fill: parent; leftPadding: 10; verticalAlignment: TextInput.AlignVCenter }
                        }
                    }

                    ColumnLayout {
                        spacing: 6; Layout.fillWidth: true
                        Text { text: "所属应用类别:"; color: root.textMuted; font.pixelSize: 12 }
                        ComboBox {
                            id: inputCategory
                            model: ["清洗算法", "生成算法"]
                            Layout.fillWidth: true; Layout.preferredHeight: 36
                            background: Rectangle { color: root.bgDark; border.color: root.borderColor; border.width: 1; radius: 4 }
                            contentItem: Text { text: parent.currentText; color: root.textColor; verticalAlignment: Text.AlignVCenter; padding: 10 }
                        }
                    }

                    ColumnLayout {
                        spacing: 6; Layout.fillWidth: true
                        Text { text: "细分策略类别 (可直接输入新增):"; color: root.textMuted; font.pixelSize: 12 }
                        ComboBox {
                            id: inputSubCategory
                            editable: true
                            model: inputCategory.currentIndex === 0 ? ["图像清洗策略", "文本清洗策略", "音频清洗策略", "表格数据清洗"] : ["图像增强方法", "文本增强方法", "音频增强方法", "深度学习生成"]
                            Layout.fillWidth: true; Layout.preferredHeight: 36
                            background: Rectangle { color: root.bgDark; border.color: root.borderColor; border.width: 1; radius: 4 }
                            contentItem: TextInput {
                                leftPadding: 10; rightPadding: 30; text: inputSubCategory.editText
                                color: root.textColor; font.pixelSize: 13; verticalAlignment: TextInput.AlignVCenter
                                onTextChanged: inputSubCategory.editText = text
                            }
                        }
                    }

                    ColumnLayout {
                        spacing: 6; Layout.fillWidth: true
                        Text { text: "挂载脚本/程序物理路径:"; color: root.textMuted; font.pixelSize: 12 }
                        RowLayout {
                            Layout.fillWidth: true; spacing: 8
                            Rectangle {
                                Layout.fillWidth: true; height: 36; color: root.bgDark; radius: 4; border.color: root.borderColor; border.width: 1
                                TextInput { id: inputScriptPath; color: root.devAccentColor; font.pixelSize: 13; font.family: "Courier"; anchors.fill: parent; leftPadding: 10; verticalAlignment: TextInput.AlignVCenter; clip: true }
                            }
                            Button {
                                text: "浏览..."; Layout.preferredHeight: 36; Layout.preferredWidth: 60
                                background: Rectangle { color: root.tableHoverBg; border.color: root.borderColor; border.width: 1; radius: 4 }
                                contentItem: Text { text: parent.text; color: root.textColor; font.pixelSize: 12; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                                onClicked: scriptFileDialog.open()
                            }
                        }
                    }

                    ColumnLayout {
                        spacing: 6; Layout.fillWidth: true
                        Text { text: "底层功能简述:"; color: root.textMuted; font.pixelSize: 12 }
                        Rectangle {
                            Layout.fillWidth: true; Layout.preferredHeight: 60; color: root.bgDark; radius: 4; border.color: root.borderColor; border.width: 1
                            TextEdit { id: inputDesc; color: root.textColor; font.pixelSize: 13; anchors.fill: parent; padding: 10; wrapMode: TextEdit.Wrap }
                        }
                    }

                    Item { Layout.fillHeight: true }
                }

                Rectangle { Layout.fillHeight: true; width: 1; color: root.borderColor }

                // === 右栏：动态参数配置引擎 ===
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    spacing: 15

                    RowLayout {
                        Layout.fillWidth: true
                        Text { text: "⚙️ 动态反射参数列表"; color: root.textColor; font.pixelSize: 14; font.bold: true }
                        Item { Layout.fillWidth: true }
                        Text { text: "这些参数将在功能面板中动态生成输入框"; color: root.textMuted; font.pixelSize: 11 }
                    }

                    // 参数列表视图
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        color: root.bgDark
                        border.color: root.borderColor
                        border.width: 1
                        radius: 6
                        clip: true

                        ColumnLayout {
                            anchors.fill: parent
                            spacing: 0

                            Rectangle {
                                Layout.fillWidth: true; height: 36; color: Theme.rowAlt
                                Rectangle { width: parent.width; height: 1; color: root.borderColor; anchors.bottom: parent.bottom }
                                RowLayout {
                                    anchors.fill: parent; anchors.leftMargin: 10; anchors.rightMargin: 10; spacing: 6
                                    Text { text: "参数名"; color: root.textMuted; font.pixelSize: 11; font.bold: true; Layout.preferredWidth: 90 }
                                    Text { text: "标签"; color: root.textMuted; font.pixelSize: 11; font.bold: true; Layout.preferredWidth: 90 }
                                    Text { text: "类型"; color: root.textMuted; font.pixelSize: 11; font.bold: true; Layout.preferredWidth: 70 }
                                    Text { text: "默认值"; color: root.textMuted; font.pixelSize: 11; font.bold: true; Layout.fillWidth: true }
                                    Item { Layout.preferredWidth: 32 }
                                }
                            }

                            ListView {
                                id: paramListView
                                Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                                model: editingParamsModel

                                Text {
                                    visible: editingParamsModel.count === 0
                                    text: "此插件无动态参数配置"
                                    color: root.textMuted; font.pixelSize: 12; anchors.centerIn: parent
                                }

                                delegate: Rectangle {
                                    width: paramListView.width
                                    height: (model.type === "int" || model.type === "float" || model.type === "select") ? 82 : 50
                                    color: index % 2 === 0 ? "transparent" : root.tableHoverBg

                                    ColumnLayout {
                                        anchors.fill: parent
                                        anchors.leftMargin: 10
                                        anchors.rightMargin: 10
                                        spacing: 2

                                        // 第一行：参数名 + 标签 + 类型 + 默认值 + 删除
                                        RowLayout {
                                            Layout.fillWidth: true
                                            Layout.preferredHeight: 36
                                            spacing: 6
                                            // 参数名
                                            Rectangle {
                                                Layout.preferredWidth: 90; height: 28; color: "transparent"; border.color: root.borderColor; border.width: 1; radius: 3
                                                TextInput {
                                                    text: model.n; color: root.textColor; font.pixelSize: 11; anchors.fill: parent; leftPadding: 5; verticalAlignment: TextInput.AlignVCenter
                                                    onTextChanged: editingParamsModel.setProperty(index, "n", text)
                                                }
                                            }
                                            // 显示标签
                                            Rectangle {
                                                Layout.preferredWidth: 90; height: 28; color: "transparent"; border.color: root.borderColor; border.width: 1; radius: 3
                                                TextInput {
                                                    text: model.label; color: root.textColor; font.pixelSize: 11; anchors.fill: parent; leftPadding: 5; verticalAlignment: TextInput.AlignVCenter
                                                    onTextChanged: editingParamsModel.setProperty(index, "label", text)
                                                }
                                            }
                                            // 类型选择
                                            ComboBox {
                                                id: paramTypeCombo
                                                Layout.preferredWidth: 70; Layout.preferredHeight: 28
                                                model: ["string", "int", "float", "bool", "select"]
                                                currentIndex: {
                                                    var t = model.type || "string"
                                                    if (t === "int") return 1
                                                    if (t === "float") return 2
                                                    if (t === "bool") return 3
                                                    if (t === "select") return 4
                                                    return 0
                                                }
                                                onCurrentTextChanged: editingParamsModel.setProperty(index, "type", currentText)
                                                background: Rectangle { color: root.bgDark; border.color: root.borderColor; border.width: 1; radius: 3 }
                                                contentItem: Text {
                                                    text: paramTypeCombo.currentText; color: root.devAccentColor; font.pixelSize: 11
                                                    verticalAlignment: Text.AlignVCenter; leftPadding: 5
                                                }
                                            }
                                            // 默认值
                                            Rectangle {
                                                Layout.fillWidth: true; height: 28; color: "transparent"; border.color: root.borderColor; border.width: 1; radius: 3
                                                TextInput {
                                                    text: model.v; color: root.devAccentColor; font.pixelSize: 11; anchors.fill: parent; leftPadding: 5; verticalAlignment: TextInput.AlignVCenter
                                                    onTextChanged: editingParamsModel.setProperty(index, "v", text)
                                                }
                                            }
                                            // 删除按钮
                                            Rectangle {
                                                Layout.preferredWidth: 26; height: 26; radius: 3
                                                color: delMa2.containsMouse ? root.dangerColor : "transparent"
                                                border.color: delMa2.containsMouse ? "transparent" : root.borderColor; border.width: 1
                                                Text { text: "✕"; font.pixelSize: 11; anchors.centerIn: parent; color: delMa2.containsMouse ? "white" : root.textMuted }
                                                MouseArea { id: delMa2; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: editingParamsModel.remove(index) }
                                            }
                                        }

                                        // 第二行：min/max (int/float) 或 options (select)
                                        RowLayout {
                                            Layout.fillWidth: true
                                            Layout.preferredHeight: 30
                                            visible: model.type === "int" || model.type === "float" || model.type === "select"
                                            spacing: 6

                                            // int/float: min + max
                                            Text {
                                                visible: model.type === "int" || model.type === "float"
                                                text: "min"; color: root.textMuted; font.pixelSize: 10
                                                Layout.preferredWidth: 24
                                            }
                                            Rectangle {
                                                visible: model.type === "int" || model.type === "float"
                                                Layout.preferredWidth: 65; height: 24; color: "transparent"; border.color: root.borderColor; border.width: 1; radius: 3
                                                TextInput {
                                                    text: model.min; color: root.textMuted; font.pixelSize: 10; anchors.fill: parent; leftPadding: 4; verticalAlignment: TextInput.AlignVCenter
                                                    onTextChanged: editingParamsModel.setProperty(index, "min", text)
                                                }
                                            }
                                            Text {
                                                visible: model.type === "int" || model.type === "float"
                                                text: "max"; color: root.textMuted; font.pixelSize: 10
                                                Layout.preferredWidth: 28
                                            }
                                            Rectangle {
                                                visible: model.type === "int" || model.type === "float"
                                                Layout.preferredWidth: 65; height: 24; color: "transparent"; border.color: root.borderColor; border.width: 1; radius: 3
                                                TextInput {
                                                    text: model.max; color: root.textMuted; font.pixelSize: 10; anchors.fill: parent; leftPadding: 4; verticalAlignment: TextInput.AlignVCenter
                                                    onTextChanged: editingParamsModel.setProperty(index, "max", text)
                                                }
                                            }

                                            // select: options
                                            Text {
                                                visible: model.type === "select"
                                                text: "选项"; color: root.textMuted; font.pixelSize: 10
                                                Layout.preferredWidth: 28
                                            }
                                            Rectangle {
                                                visible: model.type === "select"
                                                Layout.fillWidth: true; height: 24; color: "transparent"; border.color: root.borderColor; border.width: 1; radius: 3
                                                TextInput {
                                                    text: model.options; color: root.textMuted; font.pixelSize: 10; anchors.fill: parent; leftPadding: 4; verticalAlignment: TextInput.AlignVCenter
                                                    onTextChanged: editingParamsModel.setProperty(index, "options", text)
                                                }
                                            }
                                        }
                                    }
                                }
                            }

                            // 底部新增参数区
                            Rectangle {
                                Layout.fillWidth: true; height: 50; color: Theme.rowAlt
                                Rectangle { width: parent.width; height: 1; color: root.borderColor; anchors.top: parent.top }
                                RowLayout {
                                    anchors.fill: parent; anchors.leftMargin: 10; anchors.rightMargin: 10; spacing: 6
                                    TextField {
                                        id: newParamName; Layout.preferredWidth: 80; Layout.preferredHeight: 28
                                        color: root.textColor; font.pixelSize: 11; leftPadding: 5; verticalAlignment: TextInput.AlignVCenter
                                        placeholderText: "参数名"; placeholderTextColor: root.textMuted
                                        background: Rectangle { color: root.panelBg; border.color: root.borderColor; border.width: 1; radius: 3 }
                                    }
                                    TextField {
                                        id: newParamLabel; Layout.preferredWidth: 80; Layout.preferredHeight: 28
                                        color: root.textColor; font.pixelSize: 11; leftPadding: 5; verticalAlignment: TextInput.AlignVCenter
                                        placeholderText: "标签"; placeholderTextColor: root.textMuted
                                        background: Rectangle { color: root.panelBg; border.color: root.borderColor; border.width: 1; radius: 3 }
                                    }
                                    ComboBox {
                                        id: newParamType; Layout.preferredWidth: 65; Layout.preferredHeight: 28
                                        model: ["string", "int", "float", "bool", "select"]
                                        currentIndex: 0
                                        background: Rectangle { color: root.panelBg; border.color: root.borderColor; border.width: 1; radius: 3 }
                                        contentItem: Text { text: newParamType.currentText; color: root.devAccentColor; font.pixelSize: 11; verticalAlignment: Text.AlignVCenter; leftPadding: 5 }
                                    }
                                    TextField {
                                        id: newParamVal; Layout.fillWidth: true; Layout.preferredHeight: 28
                                        color: root.devAccentColor; font.pixelSize: 11; leftPadding: 5; verticalAlignment: TextInput.AlignVCenter
                                        placeholderText: "默认值"; placeholderTextColor: root.textMuted
                                        background: Rectangle { color: root.panelBg; border.color: root.borderColor; border.width: 1; radius: 3 }
                                    }
                                    Button {
                                        text: "添加"; Layout.preferredWidth: 45; Layout.preferredHeight: 28
                                        background: Rectangle { color: root.devAccentMuted; radius: 3 }
                                        contentItem: Text { text: parent.text; color: "black"; font.pixelSize: 11; font.bold: true; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                                        onClicked: {
                                            if (newParamName.text.trim() !== "") {
                                                editingParamsModel.append({
                                                    "n": newParamName.text.trim(),
                                                    "label": newParamLabel.text.trim() || newParamName.text.trim(),
                                                    "v": newParamVal.text,
                                                    "type": newParamType.currentText,
                                                    "min": "",
                                                    "max": "",
                                                    "options": "",
                                                    "desc": ""
                                                })
                                                newParamName.text = ""; newParamLabel.text = ""; newParamVal.text = ""
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // 底部操作按钮
            RowLayout {
                Layout.fillWidth: true; spacing: 15
                Item { Layout.fillWidth: true }
                Button {
                    text: "取消"; Layout.preferredWidth: 90; Layout.preferredHeight: 36
                    background: Rectangle { color: "transparent"; border.color: root.borderColor; border.width: 1; radius: 4 }
                    contentItem: Text { text: parent.text; color: root.textMuted; font.pixelSize: 14; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                    onClicked: algoConfigPopup.close()
                }
                Button {
                    text: root.pendingEditIndex === -1 ? "确认注册" : "保存修改"
                    Layout.preferredWidth: 140; Layout.preferredHeight: 36
                    background: Rectangle { color: root.devAccentColor; radius: 4 }
                    contentItem: Text { text: parent.text; color: root.bgDark; font.bold: true; font.pixelSize: 14; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                    onClicked: {
                        if (inputAlgoName.text.trim() === "" || inputScriptPath.text.trim() === "") {
                            root.showToast("⚠️ 插件名称和路径不能为空")
                            return
                        }
                        // 收集参数（含完整元数据）
                        var pArray = []
                        for(var i=0; i<editingParamsModel.count; i++) {
                            var m = editingParamsModel.get(i)
                            pArray.push({
                                "n": m.n, "label": m.label, "v": m.v, "type": m.type,
                                "min": m.min || "", "max": m.max || "",
                                "options": m.options || "", "desc": m.desc || ""
                            })
                        }
                        var pJsonStr = JSON.stringify(pArray)

                        // 复制 .py 到 plugins/user/（如已在目录中则跳过）
                        var scriptPath = inputScriptPath.text.trim()
                        var importResult = backendService.importPluginFile(scriptPath)
                        if (!importResult.ok) {
                            root.showToast("⚠️ 文件复制失败: " + (importResult.message || "未知错误"))
                            return
                        }
                        scriptPath = importResult.path

                        var payload = root.buildAlgorithmPayload(pJsonStr)
                        payload.script_path = scriptPath

                        var result = root.pendingEditIndex === -1
                            ? backendService.createAlgorithm(payload)
                            : backendService.updateAlgorithm(algoListModel.get(root.pendingEditIndex).id, payload)
                        if (root.pendingEditIndex === -1) {
                            if (result.ok) root.showToast("✅ 新插件引擎已接入")
                            else root.showToast("⚠️ 插件注册失败: " + (result.message || "未知错误"))
                        } else {
                            if (result.ok) root.showToast("✅ 底层配置已更新")
                            else root.showToast("⚠️ 配置保存失败: " + (result.message || "未知错误"))
                        }
                        if (result.ok) {
                            root.loadAlgorithms()
                            algoConfigPopup.close()
                        }
                    }
                }
            }
        }
    }


    // ========================================================================
    // ======================== 全新界面主体：Master-Detail 控制台 ================
    // ========================================================================
    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 20
        spacing: 20

        // 顶栏栏：控制台 Header
        RowLayout {
            Layout.fillWidth: true
            spacing: 15

            Rectangle { width: 4; height: 24; color: root.devAccentColor; radius: 2 }

            Label {
                text: "算法引擎与二次插件控制台"
                font.pixelSize: 22
                font.bold: true
                color: root.textColor
            }

            Item { Layout.fillWidth: true }

            Button {
                text: "+ 注册新插件环境"
                font.bold: true
                font.pixelSize: 14
                background: Rectangle {
                    color: parent.pressed ? "#1A00838F" : parent.hovered ? "#1A00E5FF" : "transparent"
                    border.color: root.devAccentColor
                    border.width: 1
                    radius: 4
                }
                contentItem: Text {
                    text: parent.text
                    color: root.devAccentColor
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
                onClicked: {
                    root.pendingEditIndex = -1
                    inputAlgoName.text = ""
                    inputCategory.currentIndex = 0
                    inputSubCategory.editText = ""
                    inputScriptPath.text = ""
                    inputDesc.text = ""
                    editingParamsModel.clear()
                    algoConfigPopup.open()
                }
            }
        }

        // ================= Master-Detail 左右分栏核心 =================
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 20

            // ---------------- 左侧 (Master)：分类折叠算法列表 ----------------
            Rectangle {
                Layout.preferredWidth: 280
                Layout.fillHeight: true
                color: root.panelBg
                border.color: root.borderColor
                border.width: 1
                radius: 8
                clip: true

                Text {
                    anchors.centerIn: parent
                    text: "暂无自定义算法注册"
                    color: root.textMuted
                    font.pixelSize: 14
                    visible: algoListModel.count === 0
                }

                Flickable {
                    anchors.fill: parent
                    contentHeight: Math.max(sectionColumn.implicitHeight, 52 + root.totalAlgoCount * 68 + 200)
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    visible: algoListModel.count > 0

                    ColumnLayout {
                        id: sectionColumn
                        width: parent.width
                        spacing: 0

                        // ---- 统计概览 ----
                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 52
                            color: Qt.rgba(29/255, 78/255, 216/255, 0.06)

                            RowLayout {
                                anchors.centerIn: parent
                                spacing: 16
                                Text {
                                    text: "总计 " + root.totalAlgoCount
                                    color: root.textColor; font.pixelSize: 13; font.bold: true
                                }
                                Rectangle { width: 1; height: 14; color: root.borderColor }
                                Rectangle {
                                    Layout.preferredWidth: Math.max(22, cleanStatText.implicitWidth + 10)
                                    Layout.preferredHeight: 18; radius: 9
                                    color: Qt.rgba(47/255, 133/255, 90/255, 0.15)
                                    Text { id: cleanStatText; anchors.centerIn: parent; text: "清 " + root.cleaningCount; color: root.cleanTagColor; font.pixelSize: 10; font.bold: true }
                                }
                                Rectangle {
                                    Layout.preferredWidth: Math.max(22, genStatText.implicitWidth + 10)
                                    Layout.preferredHeight: 18; radius: 9
                                    color: Qt.rgba(194/255, 125/255, 14/255, 0.15)
                                    Text { id: genStatText; anchors.centerIn: parent; text: "生 " + root.generationCount; color: root.genTagColor; font.pixelSize: 10; font.bold: true }
                                }
                                Rectangle {
                                    Layout.preferredWidth: Math.max(22, evalStatText.implicitWidth + 10)
                                    Layout.preferredHeight: 18; radius: 9
                                    color: Qt.rgba(29/255, 78/255, 216/255, 0.15)
                                    Text { id: evalStatText; anchors.centerIn: parent; text: "评 " + root.evaluationCount; color: root.devAccentColor; font.pixelSize: 10; font.bold: true }
                                }
                                Rectangle {
                                    Layout.preferredWidth: Math.max(22, trainStatText.implicitWidth + 10)
                                    Layout.preferredHeight: 18; radius: 9
                                    color: Qt.rgba(180/255, 83/255, 9/255, 0.15)
                                    Text { id: trainStatText; anchors.centerIn: parent; text: "训 " + root.trainingCount; color: root.genTagColor; font.pixelSize: 10; font.bold: true }
                                }
                            }
                        }

                            Rectangle { Layout.fillWidth: true; height: 1; color: root.borderColor }

                        // ===== 清洗算法 =====
                        Rectangle {
                            Layout.fillWidth: true; height: 38
                            color: root.cleaningExpanded ? Qt.rgba(47/255, 133/255, 90/255, 0.04) : "transparent"
                            MouseArea {
                                anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                                onClicked: root.cleaningExpanded = !root.cleaningExpanded
                            }
                            RowLayout {
                                anchors.fill: parent; anchors.leftMargin: 12; anchors.rightMargin: 12; spacing: 8
                                Text {
                                    text: root.cleaningExpanded ? "▼" : "▶"
                                    color: root.cleanTagColor; font.pixelSize: 10; Layout.preferredWidth: 14
                                }
                                Text {
                                    text: "清洗算法"; color: root.textColor; font.pixelSize: 13; font.bold: true
                                }
                                Rectangle {
                                    Layout.preferredWidth: Math.max(22, s1cnt.implicitWidth + 10)
                                    Layout.preferredHeight: 18; radius: 9
                                    color: Qt.rgba(47/255, 133/255, 90/255, 0.15)
                                    Text { id: s1cnt; anchors.centerIn: parent; text: root.cleaningCount; color: root.cleanTagColor; font.pixelSize: 10; font.bold: true }
                                }
                            }
                        }
                        Column {
                            visible: root.cleaningExpanded
                            Layout.fillWidth: true
                            Repeater {
                                model: cleaningAlgoModel
                                delegate: algoItemDelegate
                            }
                        }
                        Rectangle { Layout.fillWidth: true; height: 1; color: root.borderColor }

                        // ===== 生成算法 =====
                        Rectangle {
                            Layout.fillWidth: true; height: 38
                            color: root.generationExpanded ? Qt.rgba(194/255, 125/255, 14/255, 0.04) : "transparent"
                            MouseArea {
                                anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                                onClicked: root.generationExpanded = !root.generationExpanded
                            }
                            RowLayout {
                                anchors.fill: parent; anchors.leftMargin: 12; anchors.rightMargin: 12; spacing: 8
                                Text {
                                    text: root.generationExpanded ? "▼" : "▶"
                                    color: root.genTagColor; font.pixelSize: 10; Layout.preferredWidth: 14
                                }
                                Text {
                                    text: "生成算法"; color: root.textColor; font.pixelSize: 13; font.bold: true
                                }
                                Rectangle {
                                    Layout.preferredWidth: Math.max(22, s2cnt.implicitWidth + 10)
                                    Layout.preferredHeight: 18; radius: 9
                                    color: Qt.rgba(194/255, 125/255, 14/255, 0.15)
                                    Text { id: s2cnt; anchors.centerIn: parent; text: root.generationCount; color: root.genTagColor; font.pixelSize: 10; font.bold: true }
                                }
                            }
                        }
                        Column {
                            visible: root.generationExpanded
                            Layout.fillWidth: true
                            Repeater {
                                model: generationAlgoModel
                                delegate: algoItemDelegate
                            }
                        }
                        Rectangle { Layout.fillWidth: true; height: 1; color: root.borderColor }

                        // ===== 评估算法 =====
                        Rectangle {
                            Layout.fillWidth: true; height: 38
                            color: root.evaluationExpanded ? Qt.rgba(29/255, 78/255, 216/255, 0.04) : "transparent"
                            MouseArea {
                                anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                                onClicked: root.evaluationExpanded = !root.evaluationExpanded
                            }
                            RowLayout {
                                anchors.fill: parent; anchors.leftMargin: 12; anchors.rightMargin: 12; spacing: 8
                                Text {
                                    text: root.evaluationExpanded ? "▼" : "▶"
                                    color: root.devAccentColor; font.pixelSize: 10; Layout.preferredWidth: 14
                                }
                                Text {
                                    text: "评估算法"; color: root.textColor; font.pixelSize: 13; font.bold: true
                                }
                                Rectangle {
                                    Layout.preferredWidth: Math.max(22, s3cnt.implicitWidth + 10)
                                    Layout.preferredHeight: 18; radius: 9
                                    color: Qt.rgba(29/255, 78/255, 216/255, 0.15)
                                    Text { id: s3cnt; anchors.centerIn: parent; text: root.evaluationCount; color: root.devAccentColor; font.pixelSize: 10; font.bold: true }
                                }
                            }
                        }
                        Column {
                            visible: root.evaluationExpanded
                            Layout.fillWidth: true
                            Repeater {
                                model: evaluationAlgoModel
                                delegate: algoItemDelegate
                            }
                        }
                        Rectangle { Layout.fillWidth: true; height: 1; color: root.borderColor }

                        // ===== 训练算法 =====
                        Rectangle {
                            Layout.fillWidth: true; height: 38
                            color: root.trainingExpanded ? Qt.rgba(180/255, 83/255, 9/255, 0.04) : "transparent"
                            MouseArea {
                                anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                                onClicked: root.trainingExpanded = !root.trainingExpanded
                            }
                            RowLayout {
                                anchors.fill: parent; anchors.leftMargin: 12; anchors.rightMargin: 12; spacing: 8
                                Text {
                                    text: root.trainingExpanded ? "▼" : "▶"
                                    color: root.genTagColor; font.pixelSize: 10; Layout.preferredWidth: 14
                                }
                                Text {
                                    text: "训练算法"; color: root.textColor; font.pixelSize: 13; font.bold: true
                                }
                                Rectangle {
                                    Layout.preferredWidth: Math.max(22, s4cnt.implicitWidth + 10)
                                    Layout.preferredHeight: 18; radius: 9
                                    color: Qt.rgba(180/255, 83/255, 9/255, 0.15)
                                    Text { id: s4cnt; anchors.centerIn: parent; text: root.trainingCount; color: root.genTagColor; font.pixelSize: 10; font.bold: true }
                                }
                            }
                        }
                        Column {
                            visible: root.trainingExpanded
                            Layout.fillWidth: true
                            Repeater {
                                model: trainingAlgoModel
                                delegate: algoItemDelegate
                            }
                        }
                    }
                }
            }

            // ---------------- 右侧 (Detail)：插件详情配置台 ----------------
            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                color: root.panelBg
                border.color: root.borderColor
                border.width: 1
                radius: 8
                clip: true

                Text {
                    anchors.centerIn: parent
                    text: "请在左侧选择或注册新算法插件"
                    color: root.textMuted
                    font.pixelSize: 16
                    visible: root.selectedAlgoIndex === -1
                }

                // 详情面板主体
                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 25
                    spacing: 20
                    visible: root.selectedAlgoIndex !== -1

                    // 1. 顶部 Header
                    RowLayout {
                        Layout.fillWidth: true
                        ColumnLayout {
                            spacing: 8
                            Text {
                                text: root.selectedAlgoField("name")
                                color: root.textColor
                                font.pixelSize: 22
                                font.bold: true
                            }

                            Label {
                                id: tagCatText
                                text: root.selectedAlgoIndex !== -1 ? (root.selectedAlgoField("category") + " > " + root.selectedAlgoField("subCategory")) : ""
                                color: {
                                    var c = root.selectedAlgoField("category")
                                    if (c === "清洗算法") return root.cleanTagColor
                                    if (c === "生成算法") return root.genTagColor
                                    return root.devAccentColor
                                }
                                font.pixelSize: 11
                                font.bold: true
                                leftPadding: 8
                                rightPadding: 8
                                topPadding: 3
                                bottomPadding: 3

                                background: Rectangle {
                                    color: "transparent"
                                    border.color: tagCatText.color
                                    border.width: 1
                                    radius: 4
                                }
                            }
                        }

                        Item { Layout.fillWidth: true }

                        // 操作按钮组 (已修复 color 属性重复设置导致的报错问题)
                        RowLayout {
                            spacing: 10
                            Button {
                                text: "✏️ 调参修改"
                                Layout.preferredHeight: 32
                                background: Rectangle { border.color: root.borderColor; border.width: 1; radius: 4; color: parent.hovered ? root.tableHoverBg : "transparent" }
                                contentItem: Text { text: parent.text; color: root.textColor; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                                onClicked: {
                                    if(root.selectedAlgoIndex === -1) return;
                                    var idx = root.selectedAlgoIndex;
                                    var modelData = algoListModel.get(idx);

                                    root.pendingEditIndex = idx;
                                    inputAlgoName.text = modelData.name;
                                    inputCategory.currentIndex = modelData.category === "清洗算法" ? 0 : 1;

                                    var catIdx = inputSubCategory.find(modelData.subCategory);
                                    if (catIdx !== -1) { inputSubCategory.currentIndex = catIdx; }
                                    else { inputSubCategory.editText = modelData.subCategory; }

                                    inputScriptPath.text = modelData.script;
                                    inputDesc.text = modelData.desc;

                                    editingParamsModel.clear();
                                    if (modelData.paramsJson && modelData.paramsJson !== "") {
                                        var pArr = JSON.parse(modelData.paramsJson);
                                        for(var i=0; i<pArr.length; i++) editingParamsModel.append(pArr[i]);
                                    }
                                    algoConfigPopup.open();
                                }
                            }
                            Button {
                                text: "🗑️ 卸载环境"
                                Layout.preferredHeight: 32
                                background: Rectangle { border.color: root.dangerColor; border.width: 1; radius: 4; color: parent.hovered ? "#33F53F3F" : "transparent" }
                                contentItem: Text { text: parent.text; color: root.dangerColor; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                                onClicked: {
                                    if(root.selectedAlgoIndex !== -1) {
                                        root.pendingDeleteIndex = root.selectedAlgoIndex;
                                        deleteConfirmPopup.open();
                                    }
                                }
                            }
                        }
                    }

                    Rectangle { Layout.fillWidth: true; height: 1; color: root.borderColor }

                    // 2. 脚本映射展示
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        Text { text: "脚本物理挂载路径 (Target Script)"; color: root.devAccentMuted; font.pixelSize: 12; font.family: "Courier"; font.bold: true }
                        Rectangle {
                            Layout.fillWidth: true; height: 46; color: Theme.control; border.color: root.borderColor; border.width: 1; radius: 6
                            Text {
                                text: root.selectedAlgoField("script")
                                color: root.textColor
                                font.family: "Courier"
                                font.pixelSize: 14
                                anchors.verticalCenter: parent.verticalCenter; anchors.left: parent.left; anchors.leftMargin: 15
                            }
                        }
                    }

                    // 3. 描述
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        Text { text: "接口简述"; color: root.textMuted; font.pixelSize: 12; font.bold: true }
                        Text {
                            text: root.selectedAlgoField("desc")
                            color: root.textColor; font.pixelSize: 14; wrapMode: Text.WordWrap; Layout.fillWidth: true; lineHeight: 1.4
                        }
                    }

                    // 4. 算法使用说明
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        Text { text: "算法使用说明"; color: root.primaryColor; font.pixelSize: 13; font.bold: true }
                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 88
                            color: Theme.control
                            border.color: root.borderColor
                            border.width: 1
                            radius: 6
                            Text {
                                anchors.fill: parent
                                anchors.margins: 12
                                color: root.textMuted
                                font.pixelSize: 13
                                lineHeight: 1.3
                                wrapMode: Text.WordWrap
                                text: algorithmUsageText(root.selectedAlgoField("category"))
                            }
                        }
                        Text {
                            text: "完整文档: docs/ALGORITHM_USAGE_GUIDE.md"
                            color: root.textMuted
                            font.pixelSize: 12
                        }
                    }

                    // 5. 解析并展示动态 JSON 参数
                    ColumnLayout {
                        Layout.fillWidth: true; Layout.fillHeight: true; spacing: 8
                        Text { text: "动态反射参数快照 (Read-Only)"; color: root.devAccentColor; font.pixelSize: 12; font.family: "Courier"; font.bold: true }

                        Rectangle {
                            Layout.fillWidth: true; Layout.fillHeight: true; color: root.bgDark; border.color: root.borderColor; border.width: 1; radius: 6; clip: true

                            Flickable {
                                anchors.fill: parent; anchors.margins: 15; contentHeight: paramText.contentHeight; clip: true
                                Text {
                                    id: paramText
                                    color: root.textColor; font.family: "Courier"; font.pixelSize: 14; lineHeight: 1.5
                                    text: {
                                        var rawParams = root.selectedAlgoField("paramsJson")
                                        if(!rawParams) return "[]\n// 无环境参数传入";
                                        try {
                                            var arr = JSON.parse(rawParams);
                                            if(arr.length === 0) return "[]\n// 无环境参数传入";
                                            var str = "[\n";
                                            for(var i=0; i<arr.length; i++) {
                                                var p = arr[i];
                                                str += '  { name: "' + p.n + '", label: "' + (p.label || p.n) + '", type: ' + (p.type || "string");
                                                str += ', default: <font color="' + root.devAccentColor + '">' + (p.v !== undefined ? p.v : "") + '</font>';
                                                if (p.min) str += ", min: " + p.min;
                                                if (p.max) str += ", max: " + p.max;
                                                if (p.options) str += ", options: [" + p.options + "]";
                                                str += " }";
                                                if(i < arr.length - 1) str += ",";
                                                str += "\n";
                                            }
                                            str += "]";
                                            return str;
                                        } catch(e) { return "JSON Parse Error"; }
                                    }
                                    textFormat: Text.RichText
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}



