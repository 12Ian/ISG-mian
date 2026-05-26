import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import ".."

Item {
    id: root
    anchors.fill: parent

    readonly property color bgDark: Theme.bg
    readonly property color panelBg: Theme.panel
    readonly property color primaryColor: Theme.primary
    readonly property color textColor: Theme.text
    readonly property color textMuted: Theme.muted
    readonly property color borderColor: Theme.border
    readonly property color successColor: Theme.success
    readonly property color warningColor: Theme.warning
    readonly property color dangerColor: Theme.danger
    readonly property color tableHoverBg: Theme.hover

    HelpIcon {
        anchors.top: parent.top
        anchors.right: parent.right
        anchors.topMargin: -16
        anchors.rightMargin: -16
        title: "仿真评估帮助"
        body: "选择场景、数据集和骨干网络，先训练后评估比对。评估算法加载训练checkpoint完成MAV收集、Weibull拟合与OpenMax开放集识别。"
    }

    property string viewMode: "history"
    property bool isTraining: false
    property bool isEvaluating: false
    property bool isAllSelected: false
    property int taskCounter: 1
    property int currentTrainingTaskId: 0
    property int currentEvalTaskId: 0
    property var currentHistoryItem: null
    property int pendingDeleteIndex: -1
    property int pendingEditIndex: -1

    property var algorithmNameMap: ({})
    property var evalAlgorithmMap: ({})
    property var algoParamsMap: ({})
    property string pendingAlgoKey: ""
    property var evalMetricHeaders: []

    // 访问主窗口的全局状态管理器 (跨页面切换保持数据)
    property var appState: typeof window !== "undefined" && window ? window.appState : null

    // 训练算法 -> 评估算法 绑定表 (key -> key)
    property var trainingToEvalKey: ({
        "training.image.sonar_oltr_classifier": "evaluation.multimodal.sonar_oltr_plud",
        "training.image.yolov5_detector": "evaluation.image.yolov5_evaluator",
        "training.timeseries.ship_predictor": "evaluation.timeseries.ship_evaluator",
        "training.timeseries.hyfd_fault_diagnosis": "evaluation.timeseries.hyfd_fault_evaluator",
        "training.multimodal.fusion_detector": "evaluation.multimodal.fusion_evaluator",
        "training.multimodal.seg": "evaluation.multimodal.seg_evaluator"
    })

    // 场景 → 算法 绑定表 (按场景key过滤算法key)
    property var scenarioAlgoMap: ({
        "underwater_target_detection_recognition": [
            "training.image.sonar_oltr_classifier",
            "training.image.ship_classifier",
            "training.demo_classifier"
        ],
        "ship_target_recognition_tracking": [
            "training.image.yolov5_detector"
        ],
        "system_health_fault_diagnosis": [
            "training.timeseries.hyfd_fault_diagnosis"
        ],
        "intelligent_decision_command_control": [
            "training.timeseries.ship_predictor"
        ],
        "multimodal_data_fusion": [
            "training.multimodal.fusion_detector",
            "training.multimodal.seg"
        ]
    })
    // 所有训练算法的完整列表 (用于场景过滤)
    property var allTrainingAlgos: []

    ListModel { id: scenarioModel }
    ListModel { id: datasetModel }
    ListModel { id: algoModel }
    ListModel { id: taskQueueModel }
    ListModel { id: evalResultModel }
    ListModel { id: evalHistoryModel }
    ListModel { id: currentDetailModel }

    function checkStates() {
        var _allSel = taskQueueModel.count > 0
        for (var i = 0; i < taskQueueModel.count; i++) {
            if (!taskQueueModel.get(i).isSelected) _allSel = false
        }
        root.isAllSelected = _allSel
    }

    function filterAlgorithmsByScenario() {
        algoModel.clear()
        var scIdx = scenarioCombo.currentIndex
        var scKey = scIdx >= 0 ? (scenarioModel.get(scIdx).key || "") : ""
        var allowedKeys = root.scenarioAlgoMap[scKey] || []
        for (var i = 0; i < root.allTrainingAlgos.length; i++) {
            var algo = root.allTrainingAlgos[i]
            // 无场景映射时显示所有算法，有映射则只显示匹配的
            if (allowedKeys.length === 0 || allowedKeys.indexOf(algo.key) >= 0) {
                algoModel.append(algo)
            }
        }
        if (algoModel.count > 0) algoCombo.currentIndex = 0
    }

    function getCurrentTime() {
        var d = new Date()
        return d.getFullYear() + "-" + String(d.getMonth()+1).padStart(2,'0') + "-" + String(d.getDate()).padStart(2,'0')
               + " " + String(d.getHours()).padStart(2,'0') + ":" + String(d.getMinutes()).padStart(2,'0')
    }

    function algorithmName(algoId) {
        var id = Number(algoId)
        for (var i = 0; i < algoModel.count; i++) {
            var a = algoModel.get(i)
            if (Number(a.id) === id) return a.name
        }
        return root.algorithmNameMap[String(algoId)] || ("算法#" + algoId)
    }

    // ================= 后端信号 =================
    Connections {
        target: backendService

        function onEvaluationScenariosUpdated(scenarios) {
            scenarioModel.clear()
            for (var i = 0; i < scenarios.length; i++) {
                scenarioModel.append({id: scenarios[i].id || 0, name: scenarios[i].name || scenarios[i].key || "", key: scenarios[i].key || ""})
            }
            if (scenarioModel.count > 0) scenarioCombo.currentIndex = 0
            // 场景加载完后检查是否有待恢复的训练任务
            root.restoreTrainingTasksFromBackend()
        }

        function onDatasetsUpdated(data) {
            var items = []
            if (data && data.items) items = data.items
            datasetModel.clear()
            for (var j = 0; j < items.length; j++) {
                var item = items[j]
                var n = item.name || ""
                var idx = n.indexOf("|Status:")
                var s = idx !== -1 ? n.substring(idx + 8) : (item.status || "")
                if (s !== "扩增文件" && s !== "扩展文件" && s !== "generated") {
                    datasetModel.append({
                        id: item.id || 0,
                        name: (item.name || "未命名").split("|Status:")[0],
                        modality: item.modality || ""
                    })
                }
            }
            if (datasetModel.count === 0) datasetModel.append({id: 0, name: "无可用数据集 (请先导入)", modality: ""})
        }

        function onAlgorithmsUpdated(algorithms) {
            if (!algorithms || !algorithms.length) return
            var map = {}
            var old = root.algorithmNameMap
            if (old) { var oks = Object.keys(old); for (var kk = 0; kk < oks.length; kk++) map[oks[kk]] = old[oks[kk]] }
            var oldEvalMap = root.evalAlgorithmMap || {}
            var evalMap = {}
            for (var ek in oldEvalMap) { if (oldEvalMap.hasOwnProperty(ek)) evalMap[ek] = oldEvalMap[ek] }
            var paramsMap = {}
            var trainingList = []
            for (var i = 0; i < algorithms.length; i++) {
                var a = algorithms[i]
                map[String(a.id)] = a.name || a.key || ""
                if (a.parameters && a.parameters.length > 0) {
                    paramsMap[a.key || ""] = a.parameters
                    paramsMap[String(a.id)] = a.parameters
                }
                if (a.category === "evaluation") {
                    evalMap[a.key || a.name] = {id: a.id || 0, name: a.name || a.key || ""}
                } else if (a.category === "training") {
                    trainingList.push({id: a.id || 0, name: a.name || a.key || "", modality: a.modality || "", key: a.key || ""})
                }
            }
            root.algorithmNameMap = map
            root.evalAlgorithmMap = evalMap
            root.algoParamsMap = paramsMap
            root.allTrainingAlgos = trainingList
            // 根据当前场景过滤算法列表
            root.filterAlgorithmsByScenario()
        }

        function onTrainingTasksUpdated(data) {
            var items = []
            if (data && data.items) items = data.items
            for (var i = 0; i < items.length; i++) {
                var task = items[i]
                var found = false
                for (var j = 0; j < taskQueueModel.count; j++) {
                    var t = taskQueueModel.get(j)
                    if (t.taskId === (task.id || 0)) {
                        taskQueueModel.setProperty(j, "trainStatus", task.status === "completed" ? 2 : (task.status === "running" ? 1 : (task.status === "failed" ? 3 : (task.status === "interrupted" ? 4 : 0))))
                        taskQueueModel.setProperty(j, "dbStatus", task.status || "")
                        taskQueueModel.setProperty(j, "trainProgress", (task.progress || 0) / 100.0)
                        taskQueueModel.setProperty(j, "progressMessage", task.progress_message || "")
                        taskQueueModel.setProperty(j, "resultJson", task.result || {})
                        taskQueueModel.setProperty(j, "outputDir", task.output_dir || "")
                        found = true
                        break
                    }
                }
                if (!found && task.status === "running") {
                    root.isTraining = true
                }
            }
            if (root.isTraining) {
                var allDone = true
                for (var k = 0; k < taskQueueModel.count; k++) {
                    if (taskQueueModel.get(k).isSelected && taskQueueModel.get(k).trainStatus === 1) allDone = false
                }
                if (allDone) root.isTraining = false
            }
            // 同步到全局状态
            root.saveToAppState()
        }

        function onTrainingStatusUpdated(message, success, progressVal) {
            root.showToast(success ? "✅ " + message : "⚠️ " + message)
            if (!success) root.isTraining = false
        }

        function onEvaluationStatusUpdated(message, success) {
            root.showToast(success ? "✅ " + message : "⚠️ " + message)
            root.isEvaluating = false
            if (success && root.currentEvalTaskId > 0) {
                backendService.getEvaluationResults(root.currentEvalTaskId)
            }
        }

        function onEvaluationTasksUpdated(data) {
            if (root.isEvaluating) {
                var items = data.items || []
                for (var i = 0; i < items.length; i++) {
                    var it = items[i]
                    if ((it.id || 0) === root.currentEvalTaskId) {
                        if (it.status === "completed") {
                            backendService.getEvaluationResults(root.currentEvalTaskId)
                        } else if (it.status === "failed") {
                            root.isEvaluating = false
                            root.showToast("⚠️ 评估失败: " + (it.error_message || it.progress_message || "未知错误"))
                        }
                        break
                    }
                }
            }
        }

        function onEvaluationResultsUpdated(data) {
            // 不clear，多个评估任务的结果累加显示
            if (!evalMetricHeaders || evalMetricHeaders.length === 0) {
                evalMetricHeaders = []
            }
            var items = data && data.data ? data.data.items || [] : (data && data.items ? data.items : [])
            if (items.length === 0) return

            // 合并新旧指标键
            var existingKeys = evalMetricHeaders.length > 0 ? evalMetricHeaders.slice() : []
            var newKeys = []
            for (var i = 0; i < items.length; i++) {
                var mk = Object.keys(items[i].metrics || {})
                for (var k = 0; k < mk.length; k++) {
                    if (newKeys.indexOf(mk[k]) < 0 && existingKeys.indexOf(mk[k]) < 0) {
                        newKeys.push(mk[k])
                    }
                }
            }
            var skipKeys = ["num_classes", "class_names", "per_class_ap", "model_type", "num_test_sequences",
                           "label_distribution", "train_count", "val_count", "test_count", "feature_cols"]
            function filterKeys(keys) {
                var out = []
                for (var fi = 0; fi < keys.length; fi++) {
                    if (skipKeys.indexOf(keys[fi]) < 0) out.push(keys[fi])
                }
                return out
            }
            var allKeys = filterKeys(existingKeys.concat(newKeys))
            if (allKeys.length === 0) allKeys = ["accuracy", "macro_f1"]
            evalMetricHeaders = allKeys

            // 追加新结果行
            for (var i = 0; i < items.length; i++) {
                var r = items[i]
                var m = r.metrics || {}
                var vals = []
                for (var k = 0; k < allKeys.length; k++) {
                    var v = m[allKeys[k]]
                    if (v !== undefined && v !== null) {
                        if (typeof v === "number") vals.push(v < 10 ? Number(v).toFixed(4) : Number(v).toFixed(2))
                        else vals.push(String(v))
                    } else {
                        vals.push("-")
                    }
                }
                evalResultModel.append({
                    taskId: r.task_id || 0,
                    modelName: r.model_name || "",
                    evalMethod: r.model_name || r.method || "评估算法",
                    metricValues: vals,
                    metricValuesJson: JSON.stringify(vals),
                    summary: r.summary || ""
                })
            }
            root.isEvaluating = false
            root.saveToAppState()
            root.showToast("✅ 新增 " + items.length + " 条评估结果 (共 " + evalResultModel.count + " 条)")
        }
    }

    Component.onCompleted: {
        // 从全局状态恢复评估历史和训练队列
        root.restoreFromAppState()
        backendService.getScenarios()
        backendService.getDatasets(1, 100, "")
        backendService.getAlgorithms("", "")
        root.restoreTrainingTasksFromBackend()
    }

    Component.onDestruction: {
        root.saveToAppState()
    }

    // ================= 全局状态保存/恢复 =================
    function saveToAppState() {
        if (!root.appState) return
        // 把 ListModel 序列化为 JSON 数组保存
        var histArr = []
        for (var hi = 0; hi < evalHistoryModel.count; hi++) {
            var h = evalHistoryModel.get(hi)
            histArr.push({projectName: h.projectName, scenario: h.scenario, datasets: h.datasets,
                          algos: h.algos, trainStatus: h.trainStatus, evalReport: h.evalReport,
                          time: h.time, detailsJson: h.detailsJson})
        }
        root.appState.evalHistoryJson = JSON.stringify(histArr)

        var queueArr = []
        for (var qi = 0; qi < taskQueueModel.count; qi++) {
            var q = taskQueueModel.get(qi)
            queueArr.push({taskId: q.taskId, evalTaskId: q.evalTaskId, scenario: q.scenario,
                           dataset: q.dataset, datasetId: q.datasetId, algo: q.algo,
                           algoId: q.algoId, algoKey: q.algoKey, params: q.params,
                           isSelected: q.isSelected, trainStatus: q.trainStatus,
                           trainProgress: q.trainProgress, progressMessage: q.progressMessage,
                           dbStatus: q.dbStatus, resultJson: q.resultJson, outputDir: q.outputDir})
        }
        root.appState.evalTaskQueueJson = JSON.stringify(queueArr)

        var resArr = []
        for (var ri = 0; ri < evalResultModel.count; ri++) {
            var r = evalResultModel.get(ri)
            resArr.push({taskId: r.taskId, modelName: r.modelName, evalMethod: r.evalMethod,
                         metricValues: r.metricValues, metricValuesJson: r.metricValuesJson, summary: r.summary})
        }
        root.appState.evalResultJson = JSON.stringify(resArr)
        root.appState.evalMetricHeadersJson = JSON.stringify(root.evalMetricHeaders)
        root.appState.evalIsTraining = root.isTraining
        root.appState.evalTaskCounter = root.taskCounter
    }

    function restoreFromAppState() {
        if (!root.appState) return
        root.isTraining = root.appState.evalIsTraining || false
        root.taskCounter = root.appState.evalTaskCounter || 1

        // 恢复评估历史
        try {
            var histArr = JSON.parse(root.appState.evalHistoryJson || "[]")
            for (var hi = 0; hi < histArr.length; hi++) {
                evalHistoryModel.append(histArr[hi])
            }
        } catch(e) {}

        // 恢复训练任务队列
        try {
            var queueArr = JSON.parse(root.appState.evalTaskQueueJson || "[]")
            for (var qi = 0; qi < queueArr.length; qi++) {
                taskQueueModel.append(queueArr[qi])
            }
        } catch(e) {}

        // 恢复评估结果
        try {
            var resArr = JSON.parse(root.appState.evalResultJson || "[]")
            for (var ri = 0; ri < resArr.length; ri++) {
                evalResultModel.append(resArr[ri])
            }
        } catch(e) {}

        // 恢复评估指标表头
        try {
            root.evalMetricHeaders = JSON.parse(root.appState.evalMetricHeadersJson || "[]")
        } catch(e) {}
    }

    function restoreTrainingTasksFromBackend() {
        // 当场景下拉框有数据且没有本地队列时，查后端补充正在训练/已完成的任务
        if (scenarioModel.count === 0) return
        if (taskQueueModel.count > 0) return  // 已有队列不重复查询
        backendService.getTrainingTasks(0, "")
    }

    // ================= Toast =================
    property string toastMessage: ""
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

    // ================= 保存评估工程弹窗 =================
    Popup {
        id: saveProjectPopup
        width: 460; height: 300
        modal: true; focus: true
        x: Math.round((root.width - width) / 2)
        y: Math.round((root.height - height) / 2)
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: Rectangle { color: root.panelBg; radius: 8; border.color: root.borderColor; border.width: 1 }

        ColumnLayout {
            anchors.fill: parent; anchors.margins: 20; spacing: 15
            Text { text: "💾 确认保存评估结果"; color: root.textColor; font.pixelSize: 16; font.bold: true }
            Rectangle { Layout.fillWidth: true; height: 1; color: root.borderColor }
            ColumnLayout { spacing: 5; Layout.fillWidth: true
                Text { text: "评估工程名称:"; color: root.textMuted; font.pixelSize: 12 }
                Rectangle {
                    Layout.fillWidth: true; height: 36; color: root.bgDark; radius: 4; border.color: root.borderColor; border.width: 1
                    TextInput {
                        id: saveProjectInput
                        text: "评估任务_" + root.getCurrentTime().replace(/[- :]/g, "")
                        color: root.primaryColor; font.pixelSize: 13; font.bold: true
                        anchors.fill: parent; leftPadding: 10; verticalAlignment: TextInput.AlignVCenter; selectByMouse: true
                    }
                }
            }
            Text {
                text: "保存路径由系统自动管理 (data/datasets/...)"
                color: root.textMuted; font.pixelSize: 11; Layout.fillWidth: true; wrapMode: Text.WordWrap
            }

            Item { Layout.fillHeight: true }
            RowLayout { Layout.fillWidth: true; spacing: 15
                Item { Layout.fillWidth: true }
                Button {
                    text: "取消"; Layout.preferredWidth: 80; Layout.preferredHeight: 34
                    background: Rectangle { color: "transparent"; border.color: root.borderColor; border.width: 1; radius: 4 }
                    contentItem: Text { text: parent.text; color: root.textMuted; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                    onClicked: saveProjectPopup.close()
                }
                Button {
                    text: "确认保存"; Layout.preferredWidth: 100; Layout.preferredHeight: 34
                    background: Rectangle { color: root.primaryColor; radius: 4 }
                    contentItem: Text { text: parent.text; color: "black"; font.bold: true; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                    onClicked: {
                        var dsSet = {}; var algoSet = {}; var detailsArr = []; var scenarioName = ""
                        var headers = root.evalMetricHeaders || []
                        for (var i = 0; i < taskQueueModel.count; i++) {
                            var t = taskQueueModel.get(i)
                            dsSet[t.dataset] = true; algoSet[t.algo] = true
                            if (!scenarioName) scenarioName = t.scenario || ""
                            var detail = {dataset: t.dataset, algo: t.algo}
                            for (var hj = 0; hj < evalResultModel.count; hj++) {
                                var r = evalResultModel.get(hj)
                                if (r.taskId === t.evalTaskId) {
                                    try {
                                        var vals = JSON.parse(r.metricValuesJson || "[]")
                                        for (var vi = 0; vi < headers.length && vi < vals.length; vi++) {
                                            detail[headers[vi]] = vals[vi]
                                        }
                                    } catch(e) {}
                                    break
                                }
                            }
                            detailsArr.push(detail)
                        }
                        var allDone = evalResultModel.count > 0
                        evalHistoryModel.insert(0, {
                            projectName: saveProjectInput.text,
                            scenario: scenarioName,
                            datasets: Object.keys(dsSet).join(", ") || "无",
                            algos: Object.keys(algoSet).join(", ") || "无",
                            trainStatus: allDone ? "已完成" : "包含未完成",
                            evalReport: allDone ? ("共 " + evalResultModel.count + " 条评估结果") : "暂无报告",
                            time: root.getCurrentTime(),
                            detailsJson: JSON.stringify(detailsArr)
                        })
                        root.saveToAppState()
                        saveProjectPopup.close()
                        root.showToast("✅ 评估工程已归档")
                        taskQueueModel.clear(); evalResultModel.clear()
                        root.taskCounter = 1; root.viewMode = "history"
                        root.saveToAppState()
                    }
                }
            }
        }
    }

    // ================= 修改/删除弹窗 =================
    Popup {
        id: editProjectPopup
        width: 360; height: 180; modal: true; focus: true
        x: Math.round((root.width - width) / 2); y: Math.round((root.height - height) / 2)
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: Rectangle { color: root.panelBg; radius: 8; border.color: root.borderColor; border.width: 1 }
        ColumnLayout { anchors.fill: parent; anchors.margins: 20; spacing: 15
            Text { text: "✏️ 修改工程名称"; color: root.textColor; font.pixelSize: 16; font.bold: true }
            Rectangle { Layout.fillWidth: true; height: 36; color: root.bgDark; radius: 4; border.color: root.borderColor; border.width: 1
                TextInput { id: editProjectNameInput; color: root.primaryColor; font.pixelSize: 13; font.bold: true
                    anchors.fill: parent; leftPadding: 10; verticalAlignment: TextInput.AlignVCenter; selectByMouse: true }
            }
            Item { Layout.fillHeight: true }
            RowLayout { Layout.fillWidth: true; spacing: 15; Item { Layout.fillWidth: true }
                Button { text: "取消"; Layout.preferredWidth: 80; Layout.preferredHeight: 32
                    background: Rectangle { color: "transparent"; border.color: root.borderColor; border.width: 1; radius: 4 }
                    contentItem: Text { text: parent.text; color: root.textMuted; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                    onClicked: editProjectPopup.close() }
                Button { text: "保存"; Layout.preferredWidth: 80; Layout.preferredHeight: 32
                    background: Rectangle { color: root.primaryColor; radius: 4 }
                    contentItem: Text { text: parent.text; color: "black"; font.bold: true; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                    onClicked: {
                        if (root.pendingEditIndex !== -1 && editProjectNameInput.text.trim() !== "") {
                            evalHistoryModel.setProperty(root.pendingEditIndex, "projectName", editProjectNameInput.text)
                            root.showToast("✅ 工程名称已更新")
                        }
                        editProjectPopup.close()
                    }
                }
            }
        }
    }

    Popup {
        id: deleteConfirmPopup
        width: 320; height: 190; modal: true; focus: true
        x: Math.round((root.width - width) / 2); y: Math.round((root.height - height) / 2)
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: Rectangle { color: root.panelBg; radius: 8; border.color: root.dangerColor; border.width: 1 }
        ColumnLayout { anchors.fill: parent; anchors.margins: 20; spacing: 15
            RowLayout { spacing: 10
                Text { text: "⚠️"; font.pixelSize: 20 }
                Text { text: "确认删除此评估工程吗？"; color: root.textColor; font.pixelSize: 15; font.bold: true }
            }
            Text { text: "删除后历史记录将无法恢复。"; color: root.textMuted; font.pixelSize: 12; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            Item { Layout.fillHeight: true }
            RowLayout { Layout.fillWidth: true; spacing: 15; Item { Layout.fillWidth: true }
                Button { text: "取消"; Layout.preferredWidth: 80; Layout.preferredHeight: 30
                    background: Rectangle { color: "transparent"; border.color: root.borderColor; border.width: 1; radius: 4 }
                    contentItem: Text { text: parent.text; color: root.textMuted; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                    onClicked: deleteConfirmPopup.close() }
                Button { text: "确认删除"; Layout.preferredWidth: 80; Layout.preferredHeight: 30
                    background: Rectangle { color: root.dangerColor; radius: 4 }
                    contentItem: Text { text: parent.text; color: "black"; font.bold: true; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                    onClicked: {
                        if (root.pendingDeleteIndex !== -1) { evalHistoryModel.remove(root.pendingDeleteIndex); root.showToast("🗑️ 记录已删除") }
                        deleteConfirmPopup.close()
                    }
                }
            }
        }
    }

    // ========================================================================
    // 视图 A: 评估历史列表
    // ========================================================================
    ColumnLayout {
        anchors.fill: parent; anchors.margins: 20; spacing: 15
        visible: root.viewMode === "history"

        RowLayout { Layout.fillWidth: true; spacing: 15
            Label { text: "模型训练与评估历史"; font.pixelSize: 18; font.bold: true; color: root.textColor }
            Item { Layout.fillWidth: true }
            Button {
                text: "+ 添加评估任务"; font.bold: true; font.pixelSize: 14
                background: Rectangle { color: parent.pressed ? "#0277BD" : parent.hovered ? "#0288D1" : "#039BE5"; radius: 4 }
                contentItem: Text { text: parent.text; color: "black"; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                onClicked: {
                    // Preserve running tasks when re-entering the evaluate view
                    var hasRunning = false
                    for (var i = 0; i < taskQueueModel.count; i++) {
                        if (taskQueueModel.get(i).trainStatus === 1) hasRunning = true
                    }
                    if (!hasRunning) {
                        taskQueueModel.clear()
                        evalResultModel.clear()
                        root.taskCounter = 1
                    }
                    backendService.getScenarios(); backendService.getDatasets(1, 100, ""); backendService.getAlgorithms("", "")
                    root.viewMode = "evaluating"
                }
            }
        }

        Rectangle { Layout.fillWidth: true; Layout.fillHeight: true; color: "transparent"; clip: true
            ListView {
                id: historyListView
                anchors.fill: parent; clip: true; spacing: 12; model: evalHistoryModel

                delegate: Rectangle {
                    width: historyListView.width; height: 130; radius: 8; color: Theme.panel
                    border.color: rowMa.containsMouse ? Theme.primary : root.borderColor; border.width: 1
                    MouseArea { id: rowMa; anchors.fill: parent; hoverEnabled: true }
                    RowLayout { anchors.fill: parent; anchors.margins: 15; spacing: 20
                        ColumnLayout { Layout.fillWidth: true; spacing: 6
                            RowLayout { Layout.fillWidth: true; spacing: 8
                                Label { text: "🚀 " + model.projectName; color: root.primaryColor; font.pixelSize: 16; font.bold: true; elide: Text.ElideRight; Layout.maximumWidth: 400 }
                                Item { Layout.fillWidth: true }
                                Label { text: "🕒 " + model.time; color: root.textMuted; font.pixelSize: 12 }
                            }
                            RowLayout { Layout.fillWidth: true; spacing: 10
                                Label { text: "应用场景: "; color: root.textMuted; font.pixelSize: 13 }
                                Label { text: model.scenario; color: root.textColor; font.pixelSize: 13; Layout.maximumWidth: 200; elide: Text.ElideRight }
                                Rectangle { width: 1; height: 12; color: root.borderColor }
                                Label { text: "挂载数据: "; color: root.textMuted; font.pixelSize: 13 }
                                Label { text: model.datasets; color: root.textColor; font.pixelSize: 13; Layout.fillWidth: true; elide: Text.ElideRight }
                            }
                            RowLayout { Layout.fillWidth: true
                                Label { text: "算法模型: "; color: root.textMuted; font.pixelSize: 13 }
                                Label { text: model.algos; color: "#4DD0E1"; font.pixelSize: 13; Layout.fillWidth: true; elide: Text.ElideRight }
                            }
                            RowLayout { Layout.fillWidth: true; spacing: 10
                                Label { text: "训练状态: "; color: root.textMuted; font.pixelSize: 12 }
                                Label { text: model.trainStatus; color: model.trainStatus === "已完成" ? root.successColor : root.warningColor; font.pixelSize: 12; font.bold: true }
                                Rectangle { width: 1; height: 12; color: root.borderColor }
                                Label { text: "评估报告: "; color: root.textMuted; font.pixelSize: 12 }
                                Label { text: model.evalReport; color: root.primaryColor; font.pixelSize: 12; font.family: "Courier"; font.bold: true; Layout.fillWidth: true }
                            }
                        }
                        ColumnLayout { Layout.alignment: Qt.AlignVCenter | Qt.AlignRight; spacing: 10
                            Button {
                                text: "查看"; Layout.preferredWidth: 90; Layout.preferredHeight: 30
                                background: Rectangle { color: parent.hovered ? Theme.hover : Theme.control; radius: 4; border.color: Theme.border }
                                contentItem: Text { text: parent.text; color: "#D1D5DB"; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                                onClicked: {
                                    root.currentHistoryItem = { projectName: model.projectName, scenario: model.scenario, datasets: model.datasets, algos: model.algos, trainStatus: model.trainStatus, evalReport: model.evalReport }
                                    currentDetailModel.clear()
                                    if (model.detailsJson && model.detailsJson !== "") {
                                        var arr = JSON.parse(model.detailsJson)
                                        for (var i = 0; i < arr.length; i++) currentDetailModel.append(arr[i])
                                    }
                                    root.viewMode = "detail"
                                }
                            }
                            Button {
                                text: "修改"; Layout.preferredWidth: 90; Layout.preferredHeight: 30
                                background: Rectangle { color: parent.hovered ? Theme.hover : Theme.control; radius: 4; border.color: Theme.border }
                                contentItem: Text { text: parent.text; color: "#D1D5DB"; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                                onClicked: { root.pendingEditIndex = index; editProjectNameInput.text = model.projectName; editProjectPopup.open() }
                            }
                            Button {
                                text: "删除"; Layout.preferredWidth: 90; Layout.preferredHeight: 30
                                background: Rectangle { color: parent.hovered ? "#BE123C" : "transparent"; border.color: root.dangerColor; border.width: 1; radius: 4 }
                                contentItem: Text { text: parent.text; color: parent.parent.hovered ? "white" : root.dangerColor; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                                onClicked: { root.pendingDeleteIndex = index; deleteConfirmPopup.open() }
                            }
                        }
                    }
                }

                Text { anchors.centerIn: parent; text: "暂无评估历史记录"; color: Theme.muted; font.pixelSize: 16; visible: evalHistoryModel.count === 0 }
            }
        }
    }

    // ========================================================================
    // 视图 B: 评估工程详情
    // ========================================================================
    ColumnLayout {
        anchors.fill: parent; anchors.margins: 20; spacing: 15
        visible: root.viewMode === "detail"

        RowLayout { Layout.fillWidth: true; spacing: 15
            Button {
                text: "⬅ 返回历史"; font.bold: true; font.pixelSize: 14
                background: Rectangle { color: "transparent"; border.color: Theme.border; border.width: 1; radius: 4 }
                contentItem: Text { text: parent.text; color: "#4DD0E1"; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                onClicked: root.viewMode = "history"
            }
            Label { text: root.currentHistoryItem ? "📂 工程详情: " + root.currentHistoryItem.projectName : ""; font.pixelSize: 16; font.bold: true; color: root.primaryColor; Layout.leftMargin: 10 }
            Item { Layout.fillWidth: true }
        }

        Rectangle { Layout.fillWidth: true; Layout.fillHeight: true; color: Theme.row; border.color: Theme.border; border.width: 1; radius: 8; clip: true
            ColumnLayout { anchors.fill: parent; spacing: 0
                Rectangle { Layout.fillWidth: true; height: 45; color: Theme.rowAlt
                    RowLayout { anchors.fill: parent; anchors.leftMargin: 20; anchors.rightMargin: 20; spacing: 10
                        Label { text: "使用数据集"; font.bold: true; color: "#A0AEC0"; Layout.preferredWidth: 160 }
                        Label { text: "匹配算法模型"; font.bold: true; color: "#A0AEC0"; Layout.preferredWidth: 140 }
                        Label { text: "评估指标"; font.bold: true; color: "#A0AEC0"; Layout.fillWidth: true }
                    }
                }
                ListView { id: detailListView; Layout.fillWidth: true; Layout.fillHeight: true; clip: true; spacing: 1; model: currentDetailModel
                    delegate: Rectangle { width: detailListView.width; height: 45; color: index % 2 === 0 ? Theme.panel : "transparent"
                        MouseArea { anchors.fill: parent; hoverEnabled: true; onEntered: parent.color = Theme.hover; onExited: parent.color = index % 2 === 0 ? Theme.panel : "transparent" }
                        RowLayout { anchors.fill: parent; anchors.leftMargin: 20; anchors.rightMargin: 20; spacing: 10
                            Label { text: "📁 " + model.dataset; color: Theme.text; font.pixelSize: 13; Layout.preferredWidth: 160; elide: Text.ElideRight }
                            Label { text: model.algo; color: root.primaryColor; font.pixelSize: 13; font.bold: true; Layout.preferredWidth: 140; elide: Text.ElideRight }
                            Label {
                                property var _detailObj: { try { return JSON.parse(model.detailsJson || "{}") } catch(e) { return {} } }
                                property var _metricText: {
                                    var str = "";
                                    var keys = Object.keys(_detailObj);
                                    for (var mi = 0; mi < keys.length; mi++) {
                                        if (keys[mi] === "dataset" || keys[mi] === "algo") continue;
                                        if (str !== "") str += " | ";
                                        str += keys[mi] + ": " + _detailObj[keys[mi]];
                                    }
                                    return str || "暂无指标";
                                }
                                text: _metricText; color: root.textColor; font.pixelSize: 12; font.family: "Courier"; font.bold: true
                                Layout.fillWidth: true; elide: Text.ElideRight
                            }
                        }
                    }
                }
            }
        }
    }

    // ========================================================================
    // 视图 C: 评估任务操作台
    // ========================================================================
    ColumnLayout {
        anchors.fill: parent; anchors.margins: 20; spacing: 15
        visible: root.viewMode === "evaluating"

        // 顶部控制栏
        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 80; color: root.panelBg; radius: 8; border.color: root.borderColor; border.width: 1
            RowLayout { anchors.fill: parent; anchors.margins: 15; spacing: 20
                Button { text: "⬅ 返回历史"; font.bold: true; font.pixelSize: 13
                    background: Rectangle { color: "transparent"; border.color: Theme.border; border.width: 1; radius: 4 }
                    contentItem: Text { text: parent.text; color: "#4DD0E1"; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                    onClicked: root.viewMode = "history" }
                Rectangle { width: 1; height: 20; color: root.borderColor }
                ColumnLayout { spacing: 5
                    Text { text: "1. 任务场景"; color: root.textMuted; font.pixelSize: 12; font.bold: true }
                    ComboBox { id: scenarioCombo; model: scenarioModel; textRole: "name"; Layout.preferredWidth: 160
                        background: Rectangle { color: root.bgDark; border.color: root.borderColor; radius: 4 }
                        contentItem: Text { text: parent.currentText; color: root.textColor; verticalAlignment: Text.AlignVCenter; padding: 10 }
                        onCurrentIndexChanged: root.filterAlgorithmsByScenario()
                    }
                }
                Text { text: "➡"; color: root.borderColor; font.pixelSize: 16 }
                ColumnLayout { spacing: 5
                    Text { text: "2. 挂载数据集"; color: root.textMuted; font.pixelSize: 12; font.bold: true }
                    ComboBox { id: datasetCombo; model: datasetModel; textRole: "name"; Layout.preferredWidth: 160
                        background: Rectangle { color: root.bgDark; border.color: root.borderColor; radius: 4 }
                        contentItem: Text { text: parent.currentText; color: root.textColor; verticalAlignment: Text.AlignVCenter; padding: 10; elide: Text.ElideRight }
                    }
                }
                Text { text: "➡"; color: root.borderColor; font.pixelSize: 16 }
                ColumnLayout { spacing: 5
                    Text { text: "3. 骨干算法网络"; color: root.textMuted; font.pixelSize: 12; font.bold: true }
                    ComboBox { id: algoCombo; model: algoModel; textRole: "name"; Layout.preferredWidth: 160
                        background: Rectangle { color: root.bgDark; border.color: root.borderColor; radius: 4 }
                        contentItem: Text { text: parent.currentText; color: root.textColor; verticalAlignment: Text.AlignVCenter; padding: 10; elide: Text.ElideRight }
                    }
                }
                Item { Layout.fillWidth: true }
                Rectangle { width: 140; height: 38; radius: 4
                    color: (scenarioCombo.currentText && datasetCombo.currentIndex >= 0 && datasetCombo.currentText !== "无可用数据集 (请先导入)" && algoCombo.currentText) ? root.primaryColor : root.bgDark
                    border.color: (scenarioCombo.currentText && datasetCombo.currentIndex >= 0 && datasetCombo.currentText !== "无可用数据集 (请先导入)" && algoCombo.currentText) ? "transparent" : root.borderColor
                    border.width: 1
                    Text { text: "+ 追加至队列"; color: (scenarioCombo.currentText && datasetCombo.currentIndex >= 0 && datasetCombo.currentText !== "无可用数据集 (请先导入)" && algoCombo.currentText) ? "white" : root.textMuted; font.bold: true; font.pixelSize: 13; anchors.centerIn: parent }
                    MouseArea { anchors.fill: parent
                        cursorShape: (scenarioCombo.currentText && datasetCombo.currentIndex >= 0 && datasetCombo.currentText !== "无可用数据集 (请先导入)" && algoCombo.currentText) ? Qt.PointingHandCursor : Qt.ForbiddenCursor
                        enabled: scenarioCombo.currentText && datasetCombo.currentIndex >= 0 && datasetCombo.currentText !== "无可用数据集 (请先导入)" && algoCombo.currentText
                        onClicked: {
                            var algoItem = algoModel.get(algoCombo.currentIndex)
                            root.pendingAlgoKey = algoItem ? (algoItem.key || "") : ""
                            algoParamsPopup.open()
                        }
                    }
                }
            }
        }

        // 中部：训练任务队列
        Rectangle { Layout.fillWidth: true; Layout.fillHeight: true; color: "transparent"; clip: true
            ColumnLayout { anchors.fill: parent; spacing: 12
                // 队列头部操作栏
                Rectangle { Layout.fillWidth: true; height: 45; color: root.panelBg; radius: 8; border.color: root.borderColor; border.width: 1
                    RowLayout { anchors.fill: parent; anchors.leftMargin: 15; anchors.rightMargin: 15; spacing: 15
                        Rectangle { width: 18; height: 18; radius: 4; color: root.isAllSelected ? root.primaryColor : root.bgDark; border.color: root.isAllSelected ? root.primaryColor : root.textMuted
                            Text { text: "✓"; color: "white"; font.pixelSize: 12; font.bold: true; anchors.centerIn: parent; visible: root.isAllSelected }
                            MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    if (taskQueueModel.count === 0) return
                                    var ns = !root.isAllSelected
                                    for (var i = 0; i < taskQueueModel.count; i++) taskQueueModel.setProperty(i, "isSelected", ns)
                                    root.checkStates()
                                }
                            }
                        }
                        Text { text: "全选"; color: root.textMuted; font.pixelSize: 13; font.bold: true }
                        Rectangle { width: 1; height: 16; color: root.borderColor }
                        Text { text: "📋 模型训练任务队列"; color: root.textColor; font.pixelSize: 15; font.bold: true }
                        Item { Layout.fillWidth: true }
                        // 启动训练按钮
                        Rectangle { width: 130; height: 32; radius: 4
                            visible: !root.isTraining
                            color: root.canStartTraining() ? root.primaryColor : root.bgDark
                            border.color: root.canStartTraining() ? "transparent" : root.borderColor
                            Text { text: "▶ 启动选中训练"; color: root.canStartTraining() ? "white" : root.textMuted; font.bold: true; font.pixelSize: 12; anchors.centerIn: parent }
                            MouseArea { anchors.fill: parent
                                cursorShape: root.canStartTraining() ? Qt.PointingHandCursor : Qt.ForbiddenCursor
                                enabled: root.canStartTraining()
                                onClicked: root.startSelectedTraining()
                            }
                        }
                        // 取消训练按钮
                        Rectangle { width: 130; height: 32; radius: 4
                            visible: root.isTraining
                            color: "#E11D48"
                            border.color: "transparent"
                            Text { text: "⏹ 取消训练"; color: "black"; font.bold: true; font.pixelSize: 12; anchors.centerIn: parent }
                            MouseArea { anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    for (var ci = 0; ci < taskQueueModel.count; ci++) {
                                        var ct = taskQueueModel.get(ci)
                                        if (ct.trainStatus === 1 && ct.taskId > 0) {
                                            backendService.cancelTask(ct.taskId)
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                // 表头
                Rectangle { Layout.fillWidth: true; height: 40; color: root.bgDark
                    Rectangle { width: parent.width; height: 1; color: root.borderColor; anchors.bottom: parent.bottom }
                    Rectangle { width: parent.width; height: 1; color: root.borderColor; anchors.top: parent.top }
                    RowLayout { anchors.fill: parent; anchors.leftMargin: 15; anchors.rightMargin: 15; spacing: 10
                        Item { Layout.preferredWidth: 60 }
                        Label { text: "任务ID"; color: root.textMuted; font.pixelSize: 12; font.bold: true; Layout.preferredWidth: 60 }
                        Label { text: "应用场景"; color: root.textMuted; font.pixelSize: 12; font.bold: true; Layout.preferredWidth: 160 }
                        Label { text: "使用数据集"; color: root.textMuted; font.pixelSize: 12; font.bold: true; Layout.fillWidth: true }
                        Label { text: "算法模型"; color: root.textMuted; font.pixelSize: 12; font.bold: true; Layout.preferredWidth: 160 }
                        Label { text: "训练状态"; color: root.textMuted; font.pixelSize: 12; font.bold: true; Layout.preferredWidth: 150 }
                        Label { text: "操作"; color: root.textMuted; font.pixelSize: 12; font.bold: true; Layout.preferredWidth: 80; horizontalAlignment: Text.AlignRight }
                    }
                }

                ListView { Layout.fillWidth: true; Layout.fillHeight: true; clip: true; model: taskQueueModel; spacing: 0
                    Text { visible: taskQueueModel.count === 0; text: "暂无训练任务，请在上方配置并追加至队列"; color: root.textMuted; font.pixelSize: 14; anchors.centerIn: parent }

                    delegate: Rectangle { width: ListView.view ? ListView.view.width : 0; height: 50; color: index % 2 === 0 ? Theme.panel : "transparent"
                        property bool rowHov: rowMa.containsMouse
                        Rectangle { anchors.fill: parent; color: isSelected ? root.tableHoverBg : (rowHov ? Theme.hover : "transparent") }
                        Rectangle { width: parent.width; height: 1; color: root.borderColor; anchors.bottom: parent.bottom }
                        MouseArea { id: rowMa; anchors.fill: parent; hoverEnabled: true
                            onClicked: { taskQueueModel.setProperty(index, "isSelected", !isSelected); root.checkStates() }
                        }
                        RowLayout { anchors.fill: parent; anchors.leftMargin: 15; anchors.rightMargin: 15; spacing: 10
                            Item { Layout.preferredWidth: 60
                                Rectangle { width: 16; height: 16; radius: 2; anchors.centerIn: parent; color: isSelected ? root.primaryColor : root.bgDark; border.color: isSelected ? root.primaryColor : root.borderColor
                                    Text { text: "✓"; color: "white"; font.pixelSize: 12; anchors.centerIn: parent; visible: isSelected }
                                    MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; hoverEnabled: true
                                        onClicked: { taskQueueModel.setProperty(index, "isSelected", !isSelected); root.checkStates() }
                                    }
                                }
                            }
                            Text { text: "T" + (index + 1); color: root.primaryColor; font.pixelSize: 13; font.bold: true; font.family: "Courier"; Layout.preferredWidth: 60 }
                            Text { text: scenario; color: root.textColor; font.pixelSize: 13; Layout.preferredWidth: 160; elide: Text.ElideRight }
                            Text { text: dataset; color: root.textColor; font.pixelSize: 13; Layout.fillWidth: true; elide: Text.ElideRight }
                            Text { text: algo; color: "#4DD0E1"; font.pixelSize: 13; font.bold: true; Layout.preferredWidth: 160; elide: Text.ElideRight }
                            Item { Layout.preferredWidth: 150; height: 30
                                Text { text: "待训练"; color: root.textMuted; font.pixelSize: 13; font.bold: true; anchors.verticalCenter: parent.verticalCenter; visible: trainStatus === 0 }
                                ColumnLayout {
                                    anchors.verticalCenter: parent.verticalCenter
                                    RowLayout { spacing: 8; visible: trainStatus === 1
                                        Rectangle { Layout.fillWidth: true; height: 6; radius: 3; color: root.bgDark
                                            Rectangle { width: parent.width * trainProgress; height: parent.height; radius: 3; color: root.primaryColor }
                                        }
                                        Text { text: Math.floor(trainProgress * 100) + "%"; color: root.primaryColor; font.pixelSize: 12; font.bold: true; font.family: "Courier" }
                                    }
                                    Text {
                                        visible: trainStatus === 1 && (progressMessage || "")
                                        text: progressMessage || ""
                                        color: root.textMuted
                                        font.pixelSize: 11
                                        font.family: "Courier"
                                        elide: Text.ElideRight
                                        Layout.fillWidth: true
                                    }
                                }
                                Rectangle { anchors.verticalCenter: parent.verticalCenter; height: 26; width: 70; radius: 4; color: Qt.rgba(0, 180, 42, 0.1); border.color: root.successColor; border.width: 1; visible: trainStatus === 2
                                    Text { text: "✓ 已完成"; color: root.successColor; font.pixelSize: 12; font.bold: true; anchors.centerIn: parent }
                                }
                                Rectangle { anchors.verticalCenter: parent.verticalCenter; height: 26; width: 70; radius: 4; color: Qt.rgba(245, 63, 63, 0.1); border.color: root.dangerColor; border.width: 1; visible: trainStatus === 3
                                    Text { text: "✗ 失败"; color: root.dangerColor; font.pixelSize: 12; font.bold: true; anchors.centerIn: parent }
                                }
                                Rectangle { anchors.verticalCenter: parent.verticalCenter; height: 26; width: 70; radius: 4; color: Qt.rgba(245, 158, 11, 0.1); border.color: root.warningColor; border.width: 1; visible: trainStatus === 4
                                    Text { text: "⏸ 中断"; color: root.warningColor; font.pixelSize: 12; font.bold: true; anchors.centerIn: parent }
                                }
                            }
                            Item { Layout.preferredWidth: 80; height: 30
                                Rectangle { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; height: 26; width: 60; radius: 4; color: btnHov ? Theme.hover : root.bgDark; border.color: root.borderColor; border.width: 1; visible: trainStatus === 0 || trainStatus === 3 || trainStatus === 4
                                    property bool btnHov: delBtnMa.containsMouse
                                    Text { text: "删除"; color: root.dangerColor; font.pixelSize: 11; anchors.centerIn: parent }
                                    MouseArea { id: delBtnMa; anchors.fill: parent; cursorShape: Qt.PointingHandCursor; hoverEnabled: true
                                        onClicked: { taskQueueModel.remove(index); root.checkStates(); root.saveToAppState() }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        // 底部：评估比对
        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 260; color: root.panelBg; radius: 8; border.color: root.borderColor; border.width: 1
            ColumnLayout { anchors.fill: parent; anchors.margins: 15; spacing: 10
                RowLayout { Layout.fillWidth: true
                    Text { text: "📊 模型评估比对"; color: root.textColor; font.pixelSize: 16; font.bold: true }
                    Item { Layout.fillWidth: true }
                }
                Rectangle { Layout.fillWidth: true; height: 1; color: root.borderColor }

                // 启动评估
                RowLayout { Layout.fillWidth: true
                    Text { text: "4. 评估比对:"; color: root.textMuted; font.pixelSize: 13; font.bold: true }
                    Text { text: "加载训练checkpoint进行开放集识别评估（MAV收集 → Weibull拟合 → OpenMax）"; color: root.textMuted; font.pixelSize: 11; Layout.fillWidth: true; elide: Text.ElideRight }
                    Rectangle { width: 160; height: 36; radius: 4
                        color: root.canRunEvaluation() && !root.isEvaluating ? root.primaryColor : root.bgDark
                        border.color: root.canRunEvaluation() && !root.isEvaluating ? "transparent" : root.borderColor
                        opacity: root.canRunEvaluation() && !root.isEvaluating ? 1.0 : 0.4
                        Text { text: root.isEvaluating ? "⏳ 评估中..." : "🚀 启动评估比对"; color: root.canRunEvaluation() && !root.isEvaluating ? "white" : root.textMuted; font.bold: true; font.pixelSize: 13; anchors.centerIn: parent }
                        MouseArea { anchors.fill: parent
                            cursorShape: root.canRunEvaluation() && !root.isEvaluating ? Qt.PointingHandCursor : Qt.ForbiddenCursor
                            enabled: root.canRunEvaluation() && !root.isEvaluating
                            onClicked: root.startEvaluation()
                        }
                    }
                }

                // 评估比对表格
                Rectangle { Layout.fillWidth: true; Layout.fillHeight: true; color: "transparent"
                    Text { visible: evalResultModel.count === 0; text: root.isEvaluating ? "⏳ 正在执行评估比对..." : "请先完成训练，然后点击启动评估比对"; color: root.isEvaluating ? root.primaryColor : root.textMuted; font.pixelSize: 13; font.family: "Courier"; anchors.centerIn: parent }

                    ColumnLayout { anchors.fill: parent; spacing: 0; visible: evalResultModel.count > 0
                        // 表头 - 动态列 (可横向滚动)
                        Rectangle { Layout.fillWidth: true; height: 40; color: root.bgDark
                            Flickable {
                                anchors.fill: parent
                                contentWidth: headerRow.implicitWidth + 24
                                clip: true; boundsBehavior: Flickable.StopAtBounds
                                Row {
                                    id: headerRow; anchors.leftMargin: 12; anchors.verticalCenter: parent.verticalCenter
                                    spacing: 8
                                    Label { text: "模型"; color: root.textMuted; font.pixelSize: 12; font.bold: true; width: 120 }
                                    Repeater {
                                        model: evalMetricHeaders
                                        Label {
                                            text: String(modelData).length > 10 ? String(modelData).substring(0, 10) + "…" : modelData
                                            color: root.textMuted; font.pixelSize: 11; font.bold: true
                                            width: Math.max(75, String(modelData).length * 10)
                                            elide: Text.ElideRight; horizontalAlignment: Text.AlignRight
                                        }
                                    }
                                }
                            }
                        }
                        Rectangle { Layout.fillWidth: true; height: 1; color: root.borderColor }

                        // 数据行
                        ListView {
                            Layout.fillWidth: true; Layout.fillHeight: true; clip: true; model: evalResultModel; spacing: 0
                            delegate: Rectangle {
                                width: ListView.view ? ListView.view.width : 0; height: 40
                                color: index % 2 === 0 ? Theme.panel : "transparent"
                                Rectangle { width: parent.width; height: 1; color: root.borderColor; anchors.bottom: parent.bottom }
                                property var _vals: JSON.parse(metricValuesJson || "[]")

                                Flickable {
                                    anchors.fill: parent; anchors.leftMargin: 12; anchors.rightMargin: 12
                                    contentWidth: dataRow.implicitWidth
                                    clip: true; boundsBehavior: Flickable.StopAtBounds
                                    Row {
                                        id: dataRow; spacing: 8; anchors.verticalCenter: parent.verticalCenter
                                        Label { text: modelName; color: root.primaryColor; font.pixelSize: 13; font.bold: true; width: 120; elide: Text.ElideRight }
                                        Repeater {
                                            model: root.evalMetricHeaders.length
                                            Label {
                                                text: index < _vals.length ? _vals[index] : "-"
                                                color: root.textColor; font.pixelSize: 13; font.family: "Courier"; font.bold: true
                                                width: Math.max(75, String(root.evalMetricHeaders[index] || "").length * 10)
                                                horizontalAlignment: Text.AlignRight
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                // 底部保存/清空
                RowLayout { Layout.fillWidth: true; Layout.preferredHeight: 36; spacing: 15
                    Item { Layout.fillWidth: true }
                    Rectangle { width: 150; height: 36; radius: 4; color: root.bgDark; border.color: root.borderColor; border.width: 1; opacity: evalResultModel.count > 0 ? 1.0 : 0.4
                        RowLayout { anchors.centerIn: parent; spacing: 5
                            Text { text: "✗"; color: root.dangerColor; font.pixelSize: 14; font.bold: true }
                            Text { text: "清空评估面板"; color: root.dangerColor; font.pixelSize: 12; font.bold: true }
                        }
                        MouseArea { anchors.fill: parent; cursorShape: evalResultModel.count > 0 ? Qt.PointingHandCursor : Qt.ForbiddenCursor; enabled: evalResultModel.count > 0
                            onClicked: { taskQueueModel.clear(); evalResultModel.clear(); root.saveToAppState() }
                        }
                    }
                    Rectangle { width: 160; height: 36; radius: 4
                        color: evalResultModel.count > 0 ? root.primaryColor : root.bgDark
                        border.color: evalResultModel.count > 0 ? "transparent" : root.borderColor
                        border.width: 1; opacity: evalResultModel.count > 0 ? 1.0 : 0.4
                        RowLayout { anchors.centerIn: parent; spacing: 5
                            Text { text: "💾"; color: "white"; font.pixelSize: 14 }
                            Text { text: "保存评估工程"; color: evalResultModel.count > 0 ? "white" : root.textMuted; font.pixelSize: 13; font.bold: true }
                        }
                        MouseArea { anchors.fill: parent; cursorShape: evalResultModel.count > 0 ? Qt.PointingHandCursor : Qt.ForbiddenCursor; enabled: evalResultModel.count > 0
                            onClicked: saveProjectPopup.open()
                        }
                    }
                }
            }
        }
    }

    // ================= 轮询定时器 =================
    Timer {
        id: progressPollTimer
        interval: 1000; repeat: true
        running: root.isTraining
        onTriggered: backendService.getTrainingTasks(0, "")
    }

    // ================= 状态判断函数 =================
    function canStartTraining() {
        for (var i = 0; i < taskQueueModel.count; i++) {
            var t = taskQueueModel.get(i)
            if (t.isSelected && t.trainStatus === 0 && t.datasetId > 0 && t.algoId > 0) return true
        }
        return false
    }

    function startSelectedTraining() {
        for (var i = 0; i < taskQueueModel.count; i++) {
            var t = taskQueueModel.get(i)
            if (t.isSelected && t.trainStatus === 0 && t.datasetId > 0 && t.algoId > 0) {
                var scId = root.findScenarioId(t.scenario)
                var params = t.params || {}
                var result = backendService.createTrainingTask(scId, t.datasetId, t.algoId, params)
                if (!result || result.status !== "success") {
                    root.showToast("⚠️ " + (result && result.message ? result.message : "训练任务创建失败"))
                    return
                }
                taskQueueModel.setProperty(i, "taskId", result.id || 0)
                taskQueueModel.setProperty(i, "trainStatus", 1)
                taskQueueModel.setProperty(i, "trainProgress", 0.0)
                backendService.startTrainingTask(result.id)
            }
        }
        root.isTraining = true
        root.showToast("✅ 训练任务已启动")
    }

    function findScenarioId(name) {
        for (var i = 0; i < scenarioModel.count; i++) {
            if (scenarioModel.get(i).name === name) return scenarioModel.get(i).id || 0
        }
        return 0
    }

    function collectEditedParams() {
        var result = {}
        for (var i = 0; i < paramEditModel.count; i++) {
            var item = paramEditModel.get(i)
            var val = item.value
            if (val === "true") { result[item.name] = true }
            else if (val === "false") { result[item.name] = false }
            else if (!isNaN(val) && val.trim() !== "") { result[item.name] = Number(val) }
            else { result[item.name] = val }
        }
        return result
    }

    function appendTaskToQueue() {
        var dsItem = datasetModel.get(datasetCombo.currentIndex)
        var algoItem = algoModel.get(algoCombo.currentIndex)
        var taskParams = root.collectEditedParams()

        taskQueueModel.append({
            taskId: 0,
            evalTaskId: 0,
            scenario: scenarioCombo.currentText,
            dataset: dsItem ? dsItem.name : "",
            datasetId: dsItem ? (dsItem.id || 0) : 0,
            algo: algoItem ? algoItem.name : "",
            algoId: algoItem ? (algoItem.id || 0) : 0,
            algoKey: algoItem ? (algoItem.key || "") : "",
            params: taskParams,
            isSelected: true,
            trainStatus: 0,
            trainProgress: 0.0,
            progressMessage: "",
            dbStatus: "",
            resultJson: ({}),
            outputDir: ""
        })
        root.taskCounter++
        root.checkStates()
        root.pendingAlgoKey = ""
        algoParamsPopup.close()
        root.saveToAppState()
        root.showToast("✅ 已追加训练任务至队列")
    }

    function canRunEvaluation() {
        if (root.isTraining) return false
        var hasCompleted = false
        for (var i = 0; i < taskQueueModel.count; i++) {
            if (taskQueueModel.get(i).isSelected && taskQueueModel.get(i).trainStatus === 2) hasCompleted = true
        }
        return hasCompleted
    }

    function startEvaluation() {
        evalResultModel.clear()

        var totalTasks = taskQueueModel.count
        var selectedDone = 0
        var noEvalBind = 0
        var noCheckpoint = 0
        var startedCount = 0

        for (var i = 0; i < taskQueueModel.count; i++) {
            var t = taskQueueModel.get(i)
            if (!t.isSelected) continue
            if (t.trainStatus !== 2) continue
            if (!t.taskId || t.taskId <= 0) continue
            selectedDone++

            var scId = root.findScenarioId(t.scenario)
            var evalAlgoId = 0
            var evalKey = root.trainingToEvalKey[t.algoKey || ""]
            if (evalKey && root.evalAlgorithmMap[evalKey]) {
                evalAlgoId = root.evalAlgorithmMap[evalKey].id
            }
            if (!evalAlgoId) {
                noEvalBind++
                continue
            }

            var checkpointPath = ""
            var rj = t.resultJson || {}
            if (rj.artifacts && rj.artifacts.length > 0) {
                checkpointPath = rj.artifacts[0] || ""
            }
            if (!checkpointPath) {
                noCheckpoint++
                continue
            }

            var evalParams = {}
            evalParams.model_checkpoint_path = checkpointPath

            var evalResult = backendService.createEvaluationTask(scId, t.datasetId, t.datasetId, evalAlgoId, evalParams)
            if (evalResult && evalResult.status === "success") {
                taskQueueModel.setProperty(i, "evalTaskId", evalResult.id || 0)
                backendService.startEvaluationTask(evalResult.id)
                root.currentEvalTaskId = evalResult.id || 0
                startedCount++
            } else {
                root.showToast("⚠️ 创建评估任务失败: " + (evalResult ? (evalResult.message || "未知") : "无响应"))
            }
        }

        if (startedCount > 0) {
            root.isEvaluating = true
        } else {
            var reason = "总任务:" + totalTasks + " 已完成选中:" + selectedDone
            if (selectedDone === 0) reason += " (请勾选已完成训练的任务)"
            else if (noEvalBind > 0) reason += " 缺评估绑定:" + noEvalBind
            else if (noCheckpoint > 0) reason += " 缺模型文件:" + noCheckpoint
            root.showToast("⚠️ 无可评估任务 - " + reason)
        }
    }

    // ================= 弹窗：算法参数配置 (追加任务前) =================
    Popup {
        id: algoParamsPopup
        width: 500; height: 400
        modal: true; focus: true
        x: Math.round((root.width - width) / 2)
        y: Math.round((root.height - height) / 2)
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: Rectangle { color: root.panelBg; radius: 8; border.color: root.primaryColor; border.width: 1 }

        onOpened: {
            var key = root.pendingAlgoKey
            var rawParams = root.algoParamsMap[key] || []
            var editable = []
            for (var i = 0; i < rawParams.length; i++) {
                var rp = rawParams[i]
                var val = rp.default_value
                if (typeof val !== "string") val = JSON.stringify(val)
                var opts = rp.options || rp.options_json || []
                editable.push({name: rp.name, label: rp.label || rp.name, value: val, defaultValue: val, optionsJson: JSON.stringify(opts)})
            }
            paramEditModel.clear()
            for (var j = 0; j < editable.length; j++) {
                paramEditModel.append(editable[j])
            }
        }

        ColumnLayout {
            anchors.fill: parent; anchors.margins: 20; spacing: 15
            RowLayout {
                Layout.fillWidth: true
                Text { text: "算法参数配置"; color: root.primaryColor; font.pixelSize: 16; font.bold: true }
                Item { Layout.fillWidth: true }
                Rectangle {
                    width: 28; height: 28; radius: 4; color: "transparent"
                    Text { text: "x"; color: root.textMuted; font.pixelSize: 16; anchors.centerIn: parent }
                    MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; hoverEnabled: true
                        onEntered: parent.color = root.tableHoverBg
                        onExited: parent.color = "transparent"
                        onClicked: algoParamsPopup.close()
                    }
                }
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: root.borderColor }

            Text { text: "以下参数将从算法默认值预填充，您可按需修改："; color: root.textMuted; font.pixelSize: 12 }

            ListModel { id: paramEditModel }
            Rectangle {
                Layout.fillWidth: true; Layout.fillHeight: true
                color: root.bgDark; border.color: root.borderColor; border.width: 1; radius: 6; clip: true

                Rectangle { width: parent.width; height: 32; color: Theme.rowAlt
                    RowLayout { anchors.fill: parent; anchors.leftMargin: 12; anchors.rightMargin: 12; spacing: 10
                        Text { text: "参数名"; color: root.textMuted; font.pixelSize: 12; font.bold: true; Layout.fillWidth: true }
                        Text { text: "值"; color: root.textMuted; font.pixelSize: 12; font.bold: true; Layout.preferredWidth: 200 }
                    }
                }

                ListView {
                    id: paramEditList
                    anchors.fill: parent; anchors.topMargin: 32; clip: true
                    model: paramEditModel
                    delegate: Rectangle {
                        width: paramEditList.width; height: 40
                        color: index % 2 === 0 ? "transparent" : root.tableHoverBg
                        property var _opts: { try { return JSON.parse(model.optionsJson || "[]") } catch(e) { return [] } }
                        RowLayout {
                            anchors.fill: parent; anchors.leftMargin: 12; anchors.rightMargin: 12; spacing: 10
                            Text {
                                text: model.label; color: root.textColor; font.pixelSize: 13
                                Layout.fillWidth: true; verticalAlignment: Text.AlignVCenter
                            }
                            // 有 options = 下拉框
                            ComboBox {
                                visible: _opts.length > 0
                                Layout.preferredWidth: 200
                                model: _opts
                                currentIndex: {
                                    var cv = model.value !== undefined ? String(model.value) : ""
                                    for (var oi = 0; oi < _opts.length; oi++) { if (String(_opts[oi]) === cv) return oi }
                                    return 0
                                }
                                onCurrentIndexChanged: {
                                    if (currentIndex >= 0 && currentIndex < _opts.length)
                                        paramEditModel.setProperty(index, "value", _opts[currentIndex])
                                }
                                background: Rectangle { color: "transparent"; border.color: root.borderColor; border.width: 1; radius: 4 }
                                contentItem: Text { text: parent.currentText || ""; color: root.primaryColor; font.pixelSize: 13; verticalAlignment: Text.AlignVCenter; padding: 8 }
                            }
                            // 无 options = 文本输入
                            Rectangle {
                                visible: _opts.length === 0
                                Layout.preferredWidth: 200; height: 30
                                color: "transparent"; border.color: root.borderColor; border.width: 1; radius: 4
                                TextInput {
                                    text: model.value
                                    color: root.primaryColor; font.pixelSize: 13; font.family: "Courier"
                                    anchors.fill: parent; leftPadding: 8; verticalAlignment: TextInput.AlignVCenter
                                    onTextChanged: paramEditModel.setProperty(index, "value", text)
                                }
                            }
                        }
                    }
                }
            }

            RowLayout { Layout.fillWidth: true; spacing: 15
                Item { Layout.fillWidth: true }
                Button {
                    text: "恢复默认"; Layout.preferredWidth: 100; Layout.preferredHeight: 32
                    background: Rectangle { color: "transparent"; border.color: root.borderColor; border.width: 1; radius: 4 }
                    contentItem: Text { text: parent.text; color: root.textMuted; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                    onClicked: {
                        for (var ri = 0; ri < paramEditModel.count; ri++) {
                            var defVal = paramEditModel.get(ri).defaultValue
                            if (defVal !== undefined) paramEditModel.setProperty(ri, "value", defVal)
                        }
                    }
                }
                Button {
                    text: "确认追加"; Layout.preferredWidth: 100; Layout.preferredHeight: 32
                    background: Rectangle { color: root.primaryColor; radius: 4 }
                    contentItem: Text { text: parent.text; color: "black"; font.bold: true; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                    onClicked: root.appendTaskToQueue()
                }
            }
        }
    }
}
