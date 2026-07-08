import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import QtMultimedia
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
    readonly property color dangerColor: Theme.danger
    readonly property color tableHoverBg: Theme.hover

    HelpIcon {
        anchors.top: parent.top
        anchors.right: parent.right
        anchors.topMargin: -16
        anchors.rightMargin: -16
        title: "数据生成帮助"
        body: "本页用于基于已有数据集生成扩增样本，并管理生成任务历史。\n\n1. 左侧历史区展示已创建的生成任务，可按任务卡片查看任务状态、目标数据集、使用算法、参数和生成结果。\n2. 点击“新建生成任务”进入配置流程。先选择基础数据集，可通过阶段筛选切换原始、清洗后或生成数据集。\n3. 选择数据集后，系统会按模态加载可用生成算法，例如图像增强、文本增强、音频增强等。可以同时勾选多个算法。\n4. 每个算法会显示动态参数表，参数来自算法注册信息。修改参数后会随任务一起提交，例如生成数量、强度、噪声类型、线性倍率等。\n5. 设置目标生成数量后启动任务。运行过程中可以查看进度；任务失败时会弹出错误原因，便于检查算法配置、源数据或依赖环境。\n6. 任务完成后，右侧详情区可查看生成输出列表、源样本、生成样本、算法名称和状态。点击样本可打开预览。\n7. 可对历史任务重命名、删除，或批量选择后导出生成工程记录。生成结果会写入目标数据集，可继续用于清洗、训练或评估。"
    }

    property string viewMode: "history"
    property bool isGenerating: false
    property bool isCompleted: false
    property int currentCount: 0
    property int totalCount: 1000
    property real progress: totalCount > 0 ? currentCount / totalCount : 0
    property int currentTaskId: 0
    property int currentTargetDatasetId: 0
    property int lastFailureTaskId: 0
    property string generationErrorMessage: ""

    property var selectedStrategies: []
    property var generationAlgorithms: []
    property var generationAlgorithmGroups: []

    property var sourceDatasets: []
    property var allSourceDatasets: []
    property string datasetTypeFilter: "all"
    property var currentHistoryItem: null
    property var currentFileList: []
    property var detailAlgorithmIds: []
    property var detailAlgorithmItems: []
    property var detailParameters: ({})
    property bool hasDetailCustomParams: false

    property string previewKind: ""
    property string previewTitle: ""
    property string previewText: ""
    property string previewSource: ""
    property bool comparisonPreviewMode: false
    property var previewLeftData: ({})
    property var previewRightData: ({})
    property bool previewHasGenerated: false
    property string currentTargetDatasetName: ""

    property int pendingPreviewId: -1
    property int pendingEditIndex: -1
    property int pendingDeleteIndex: -1
    property int selectedExportCount: 0
    property var generationParameterPresets: []
    property var hoveredParameterPreset: null
    property bool parameterPresetPreviewVisible: false
    property var allGenerationHistoryItems: []
    property string historySearchText: ""

    function updateExportCount() {
        var count = 0
        for (var i = 0; i < generationHistoryModel.count; i++) {
            if (generationHistoryModel.get(i).isSelected) count++
        }
        root.selectedExportCount = count
    }

    function loadGenerationParameterPresets() {
        var result = backendService.getGenerationParameterPresets()
        if (result && result.status === "success") {
            root.generationParameterPresets = result.items || []
        }
    }

    function parameterPresetOptions() {
        var items = [{ name: root.generationParameterPresets.length > 0 ? "选择已保存参数" : "暂无已保存参数" }]
        for (var i = 0; i < root.generationParameterPresets.length; i++) {
            var preset = root.generationParameterPresets[i]
            items.push({ name: preset.name || ("参数记录 " + (i + 1)) })
        }
        return items
    }

    function generationHistoryMatches(item, keyword) {
        if (!keyword) return true
        var text = [
            item.projectName || "",
            item.algos || "",
            item.algorithmNames || "",
            item.sourceDataset || "",
            item.generatedDataset || ""
        ].join(" ").toLowerCase()
        return text.indexOf(keyword) !== -1
    }

    function applyGenerationHistoryFilter() {
        var keyword = String(root.historySearchText || "").trim().toLowerCase()
        generationHistoryModel.clear()
        for (var i = 0; i < root.allGenerationHistoryItems.length; i++) {
            var item = root.allGenerationHistoryItems[i]
            if (root.generationHistoryMatches(item, keyword)) {
                generationHistoryModel.append(item)
            }
        }
        root.updateExportCount()
    }

    function modalityFromLabel(label) {
        if (label === "图像") return "image"
        if (label === "文本") return "text"
        if (label === "音频") return "audio"
        if (label === "表格") return "tabular"
        if (label === "视频") return "video"
        if (label === "多模态") return "multimodal"
        return label || ""
    }

    function modalityTitle(modality) {
        if (modality === "image") return "图像增强方法"
        if (modality === "text") return "文本增强方法"
        if (modality === "audio") return "音频增强方法"
        if (modality === "tabular") return "表格增强方法"
        if (modality === "video") return "视频增强方法"
        if (modality === "multimodal") return "通用生成方法"
        return "其他生成方法"
    }

    function stageLabel(stage) {
        if (stage === "raw") return "原始"
        if (stage === "cleaned") return "清洗"
        if (stage === "generated") return "生成"
        return stage || "原始"
    }

    function stageColor(stage) {
        if (stage === "raw") return "#4DD0E1"
        if (stage === "cleaned") return "#34D399"
        if (stage === "generated") return "#F59E0B"
        return root.textMuted
    }

    function applyDatasetFilter() {
        var filtered = []
        for (var i = 0; i < root.allSourceDatasets.length; i++) {
            var ds = root.allSourceDatasets[i]
            if (root.datasetTypeFilter === "all" || ds.stage === root.datasetTypeFilter) {
                filtered.push(ds)
            }
        }
        if (filtered.length === 0) filtered.push({ id: 0, name: "无可用数据集", modality: "", stage: root.datasetTypeFilter })
        root.sourceDatasets = filtered
    }

    function currentSourceDataset() {
        if (sourceDataCombo.currentIndex < 0 || sourceDataCombo.currentIndex >= root.sourceDatasets.length)
            return null
        return root.sourceDatasets[sourceDataCombo.currentIndex]
    }

    function loadGenerationAlgorithms() {
        var source = root.currentSourceDataset()
        var modality = source ? (source.modality || "") : ""
        backendService.getAlgorithms("generation", modality)
    }

    function imageStrongDefaultValue(algo, param) {
        if (!algo || algo.modality !== "image" || !param || !param.name) return undefined
        var key = String(algo.key || "")
        var name = String(param.name || "")
        var defaults = {
            "generation.image.crop": {
                "crop_ratio": 0.7,
                "crop_mode": "random"
            },
            "generation.image.geometric_transform": {
                "rotation_degrees": 15,
                "scale": 0.92,
                "translate_x_pct": 6,
                "translate_y_pct": -4,
                "flip_horizontal": false,
                "flip_vertical": false
            },
            "generation.image.style_transfer": {
                "strength": 0.85
            },
            "generation.image.texture_enhancement": {
                "texture_strength": 0.75,
                "detail_sigma": 1.2,
                "detail_gain": 1.8
            },
            "generation.image.lighting_direction": {
                "light_direction": "left_to_right",
                "light_strength": 0.75,
                "ambient_level": 0.1
            },
            "generation.image.temperature_calibration": {
                "stretch_low_pct": 4,
                "stretch_high_pct": 96,
                "clahe_clip": 3.5,
                "clahe_tile": 8
            },
            "generation.image.halo_effect": {
                "mode": "simulate",
                "halo_strength": 0.75,
                "halo_radius": 36,
                "dehalo_clip": 0.7
            },
            "generation.image.color_space": {
                "brightness": 14,
                "contrast": 1.18,
                "saturation": 1.25,
                "hue": 8,
                "pca_jitter": 0.08
            },
            "generation.image.clarity": {
                "blur_strength": 0,
                "blur_kernel": 5,
                "sharpen_strength": 1.2,
                "sharpen_amount": 0.55
            },
            "generation.image.occlusion": {
                "occlusion_type": "random_erase",
                "erase_count": 2,
                "area_ratio": 0.35
            },
            "generation.image.environment_simulation": {
                "fog_intensity": 0.45,
                "snow_intensity": 0.35,
                "shadow_intensity": 0.35
            },
            "generation.image.deformation_distortion": {
                "elastic_strength": 8,
                "elastic_gaussian_kernel": 10,
                "distortion_k1": 0.18,
                "distortion_k2": 0.03
            },
            "generation.image.imaging_simulation": {
                "blur_kernel": 5,
                "downsample": 0.5
            },
            "generation.image.linear_transform": {
                "alpha": 1.6,
                "beta": 35,
                "gamma": 1.1
            },
            "generation.image.channel_shuffle": {
                "shuffle": true
            },
            "generation.image.cross_modal_fusion": {
                "clahe_clip": 4,
                "ir_weight": 0.75
            },
            "generation.image.wgan_gp": {
                "gradient_penalty": 10,
                "discriminator_iterations": 5,
                "learning_rate": 0.0001,
                "enhance_strength": 1.3
            },
            "generation.image.diffusion": {
                "diffusion_steps": 60,
                "cfg_guidance_scale": 1,
                "noise_strength": 0.35,
                "blend_strength": 0.65
            },
            "generation.image.vit_mae": {
                "mask_ratio": 0.45,
                "learning_rate": 0.0001,
                "training_steps": 160,
                "patch_size": 4,
                "blend_strength": 0.75
            },
            "噪声注入": {
                "noise_type": "gaussian",
                "noise_intensity": 0.16,
                "salt_pepper_ratio": 0.5,
                "shot_noise": 0.06,
                "read_noise": 0.03
            }
        }
        var values = defaults[key]
        if (!values || values[name] === undefined) return undefined
        return values[name]
    }

    function buildParamsDataMap(algorithms) {
        var map = {}
        for (var i = 0; i < algorithms.length; i++) {
            var algo = algorithms[i]
            var params = []
            var rawParams = algo.parameters || []
            for (var p = 0; p < rawParams.length; p++) {
                var param = rawParams[p]
                var opts = param.options || param.options_json || []
                var strongDefault = root.imageStrongDefaultValue(algo, param)
                var defaultValue = strongDefault !== undefined ? strongDefault : param.default_value
                params.push({
                    n: param.name || "",
                    label: param.label || param.name || "",
                    v: defaultValue !== undefined && defaultValue !== null ? String(defaultValue) : "",
                    type: param.type || "string",
                    options: opts,
                    optionsJson: JSON.stringify(opts)
                })
            }
            map[String(algo.id)] = params
        }
        return map
    }

    function groupGenerationAlgorithms(algorithms) {
        var order = ["multimodal", "image", "text", "audio", "tabular", "video", "other"]
        var grouped = {}
        for (var i = 0; i < algorithms.length; i++) {
            var algo = algorithms[i]
            var mod = algo.modality || "other"
            if (!grouped[mod]) grouped[mod] = []
            grouped[mod].push(algo)
        }
        var result = []
        for (var j = 0; j < order.length; j++) {
            var key = order[j]
            if (grouped[key] && grouped[key].length > 0)
                result.push({ t: root.modalityTitle(key), m: grouped[key] })
        }
        return result
    }

    function algorithmById(algoId) {
        var id = Number(algoId)
        for (var i = 0; i < root.generationAlgorithms.length; i++) {
            if (Number(root.generationAlgorithms[i].id) === id) return root.generationAlgorithms[i]
        }
        return null
    }

    function algorithmName(algoId) {
        var algo = root.algorithmById(algoId)
        return algo ? algo.name : "未知算法"
    }

    function selectedGenerationParameters() {
        return { algorithm_ids: root.selectedStrategies.slice() }
    }

    property var paramsDataMap: ({})
    property var algorithmNameMap: ({})
    property var parameterLabelMap: ({})
    property var algorithmParameterLabelMap: ({})

    function algorithmNames(ids) {
        if (!ids || ids.length === 0) return ""
        var names = []
        for (var i = 0; i < ids.length; i++) {
            var name = root.algorithmNameMap[String(ids[i])] || ("算法#" + ids[i])
            names.push(name)
        }
        return names.join(", ")
    }

    function formatParameters(ids, paramsJson) {
        var parts = []
        parts.push("算法: " + root.algorithmNames(ids))
        if (paramsJson) {
            var keys = Object.keys(paramsJson)
            for (var i = 0; i < keys.length; i++) {
                var k = keys[i]
                if (k === "algorithm_ids" || k === "target_count") continue
                parts.push(root.parameterDisplayName(k, ids) + "=" + paramsJson[k])
            }
        }
        return parts.join(" | ")
    }

    function parameterDisplayName(key, ids) {
        var name = String(key || "")
        var label = ""
        var algoLabelMap = root.algorithmParameterLabelMap || {}
        if (ids) {
            for (var i = 0; i < ids.length; i++) {
                var labels = algoLabelMap[String(ids[i])] || {}
                if (labels[name]) {
                    label = labels[name]
                    break
                }
            }
        }
        if (!label) label = root.parameterLabelMap[name] || ""
        if (!label || label === name) return name
        return "\uFF08" + label + "\uFF09" + name
    }

    function parameterLabelOnly(key, ids) {
        var name = String(key || "")
        if (name === "target_count") return "目标数量"
        var label = ""
        var algoLabelMap = root.algorithmParameterLabelMap || {}
        if (ids) {
            for (var i = 0; i < ids.length; i++) {
                var labels = algoLabelMap[String(ids[i])] || {}
                if (labels[name]) {
                    label = labels[name]
                    break
                }
            }
        }
        if (!label) label = root.parameterLabelMap[name] || ""
        return label || name
    }

    function cleanPresetParameters(params) {
        var result = {}
        if (!params) return result
        var keys = Object.keys(params)
        for (var i = 0; i < keys.length; i++) {
            var key = keys[i]
            if (key === "algorithm_ids") continue
            result[key] = params[key]
        }
        return result
    }

    function saveCurrentDetailParameterPreset(name) {
        var params = root.cleanPresetParameters(root.detailParameters)
        if (params.target_count === undefined && root.currentHistoryItem && root.currentHistoryItem.targetCount) {
            params.target_count = root.currentHistoryItem.targetCount
        }
        var result = backendService.saveGenerationParameterPreset(name, root.detailAlgorithmIds || [], params)
        if (result && result.status === "success") {
            root.generationParameterPresets = result.items || []
            root.showToast("✅ 参数记录已保存")
            return true
        }
        root.showToast("⚠️ " + (result && result.message ? result.message : "参数记录保存失败"))
        return false
    }

    function applyParameterPreset(preset) {
        if (!preset) return
        var rawIds = root.parseAlgorithmIds(preset.algorithm_ids || preset.algorithmIds || [])
        var availableIds = []
        for (var i = 0; i < rawIds.length; i++) {
            if (root.algorithmById(rawIds[i]) !== null) availableIds.push(rawIds[i])
        }
        if (availableIds.length === 0 && rawIds.length > 0) {
            root.showToast("⚠️ 当前源数据集下没有该参数记录对应的算法")
            return
        }
        if (availableIds.length > 0) root.selectedStrategies = availableIds

        var params = preset.parameters || {}
        if (params.target_count !== undefined) {
            var count = parseInt(params.target_count)
            if (!isNaN(count) && count > 0) root.totalCount = count
        }

        var newMap = {}
        var mapKeys = Object.keys(root.paramsDataMap || {})
        for (var mk = 0; mk < mapKeys.length; mk++) {
            var mapKey = mapKeys[mk]
            var sourceList = root.paramsDataMap[mapKey] || []
            var targetList = []
            for (var p = 0; p < sourceList.length; p++) {
                var item = sourceList[p]
                var copied = {
                    n: item.n,
                    label: item.label,
                    v: params[item.n] !== undefined ? String(params[item.n]) : item.v,
                    type: item.type,
                    options: item.options,
                    optionsJson: item.optionsJson
                }
                targetList.push(copied)
            }
            newMap[mapKey] = targetList
        }
        root.paramsDataMap = newMap
        root.showToast("✅ 已应用参数记录")
    }

    function parameterPresetPreviewItems(preset) {
        var result = []
        if (!preset) return result
        var params = preset.parameters || {}
        var ids = root.parseAlgorithmIds(preset.algorithm_ids || preset.algorithmIds || [])
        var keys = Object.keys(params)
        for (var i = 0; i < keys.length; i++) {
            var key = keys[i]
            if (key === "algorithm_ids") continue
            result.push({ label: root.parameterLabelOnly(key, ids), value: String(params[key]) })
        }
        return result
    }

    function refreshHistoryAlgorithmDescriptions() {
        for (var h = 0; h < root.allGenerationHistoryItems.length; h++) {
            var historyItem = root.allGenerationHistoryItems[h]
            var ids = root.parseAlgorithmIds(historyItem.algorithmIdsText || historyItem.algorithmIds || "")
            var historyParams = root.parseJsonObject(historyItem.parametersJsonText || historyItem.parameters || {})
            historyItem.algos = root.formatParameters(ids, historyParams)
            historyItem.algorithmNames = root.algorithmNames(ids)
        }
        for (var i = 0; i < generationHistoryModel.count; i++) {
            var item = generationHistoryModel.get(i)
            var algorithmIds = root.parseAlgorithmIds(item.algorithmIdsText || item.algorithmIds || "")
            var params = root.parseJsonObject(item.parametersJsonText || item.parameters || {})
            generationHistoryModel.setProperty(i, "algos", root.formatParameters(algorithmIds, params))
            generationHistoryModel.setProperty(i, "algorithmNames", root.algorithmNames(algorithmIds))
        }
        root.applyGenerationHistoryFilter()
    }

    function generationTaskTitle(task, sourceName) {
        var datasetName = sourceName || ("数据集#" + (task.source_dataset_id || ""))
        var taskId = task.id || task.taskId || ""
        return "生成任务_" + datasetName + "_#" + taskId
    }

    function showGenerationFailure(message) {
        root.isGenerating = false
        root.isCompleted = false
        root.generationErrorMessage = message && message !== "" ? message : "生成任务执行失败，请检查算法配置或源数据集。"
        generationFailurePopup.open()
    }

    function parseAlgorithmIds(value) {
        if (Array.isArray(value)) {
            return value.map(function(item) { return Number(item) }).filter(function(item) { return item > 0 })
        }
        return String(value || "").split(",").map(function(item) {
            return Number(String(item).trim())
        }).filter(function(item) {
            return item > 0
        })
    }

    function parseJsonObject(value) {
        if (!value) return {}
        if (typeof value === "object") return value
        try {
            return JSON.parse(String(value))
        } catch (e) {
            return {}
        }
    }

    function normalizeAlgorithmIds(task) {
        var parameters = task.parameters || task.parameters_json || {}
        var payload = task.payload || task.payload_json || {}
        var ids = parameters.algorithm_ids || payload.algorithm_ids || []
        if ((!ids || ids.length === 0) && task.algorithm_id) ids = [task.algorithm_id]
        return root.parseAlgorithmIds(ids)
    }

    function detailParameterItems(params) {
        var result = []
        if (!params) return result
        var keys = Object.keys(params)
        for (var i = 0; i < keys.length; i++) {
            var key = keys[i]
            if (key === "algorithm_ids") continue
            result.push({ k: key, v: params[key] })
        }
        return result
    }

    function localFileUrl(path) {
        var clean = String(path || "").replace(/\\/g, "/")
        if (clean.indexOf("file://") === 0) return clean
        return "file:///" + clean
    }

    function isImagePath(path) {
        var ext = String(path || "").toLowerCase().split(".").pop()
        return ["jpg","jpeg","png","bmp","gif","webp","tif","tiff"].indexOf(ext) >= 0
    }

    function previewKindForPath(path) {
        var ext = String(path || "").toLowerCase().split(".").pop()
        if (["jpg","jpeg","png","bmp","gif","webp","tif","tiff"].indexOf(ext) >= 0) return "image"
        if (["wav","mp3","aac","flac","ogg","m4a"].indexOf(ext) >= 0) return "audio"
        if (["txt","csv","json","md","log","yaml","yml","xml"].indexOf(ext) >= 0) return "text"
        return "file"
    }

    function previewPayloadWithFallback(payload, fallbackPath, fallbackTitle) {
        var data = {}
        var source = payload || {}
        var keys = Object.keys(source)
        for (var i = 0; i < keys.length; i++) data[keys[i]] = source[keys[i]]
        var path = data.file_path || data.path || data.sample_path || fallbackPath || ""
        if (path !== "") {
            data.file_path = path
            data.path = path
            data.sample_path = path
        }
        if (!data.preview_kind || data.preview_kind === "file") data.preview_kind = root.previewKindForPath(path)
        if (!data.name && fallbackTitle) data.name = fallbackTitle
        return data
    }

    function previewFileSource(payload) {
        var path = payload ? (payload.file_path || payload.path || payload.sample_path || "") : ""
        return path ? root.localFileUrl(path) : ""
    }

    function previewDisplayName(payload, fallback) {
        if (!payload) return fallback
        return payload.name || payload.relative_path || fallback
    }

    function openGenerationPreview(sourceSampleId, generatedSampleId, sourceTitle, generatedTitle, sourceFilePath, generatedFilePath) {
        var result = backendService.getSamplePreviewPair(sourceSampleId || 0, generatedSampleId || 0)
        if (!result || result.status !== "success") {
            root.showToast("\u26a0\ufe0f \u6837\u672c\u9884\u89c8\u52a0\u8f7d\u5931\u8d25")
            return
        }
        root.comparisonPreviewMode = true
        root.previewLeftData = root.previewPayloadWithFallback(result.source || {}, sourceFilePath || "", sourceTitle || "\u6e90\u6837\u672c")
        root.previewRightData = root.previewPayloadWithFallback(result.generated || {}, generatedFilePath || "", generatedTitle || "\u751f\u6210\u6837\u672c")
        root.previewHasGenerated = generatedSampleId > 0 && (root.previewFileSource(root.previewRightData) !== "" || !!(result.generated && result.generated.sample_id))
        root.previewTitle = root.previewHasGenerated
                ? ((sourceTitle || "\u6e90\u6837\u672c") + "  ->  " + (generatedTitle || "\u751f\u6210\u6837\u672c"))
                : (sourceTitle || "\u6e90\u6837\u672c")
        previewPlayer.stop()
        samplePreviewPopup.open()
    }

    function openSinglePreview(payload) {
        root.comparisonPreviewMode = false
        root.previewKind = payload.preview_kind || "file"
        root.previewText = payload.text_content || payload.error || ""
        root.previewTitle = payload.name || payload.relative_path || "\u6837\u672c\u9884\u89c8"
        root.previewSource = root.previewFileSource(payload)
        if (root.previewKind === "audio" && root.previewSource !== "") {
            previewPlayer.source = root.previewSource
        }
        samplePreviewPopup.open()
    }

    function computeHasDetailParams(obj) {
        if (!obj) return false
        var keys = Object.keys(obj)
        for (var i = 0; i < keys.length; i++) {
            if (keys[i] !== "algorithm_ids" && keys[i] !== "target_count") return true
        }
        return false
    }

    ListModel { id: generationHistoryModel }
    ListModel { id: previewModel }

    // ================= 后端信号处理 =================
    Connections {
        target: backendService

        function onDatasetsUpdated(data) {
            var rawList = []
            if (data && data.items) rawList = data.items
            else if (Array.isArray(data)) rawList = data

            var sources = []
            for (var i = 0; i < rawList.length; i++) {
                var item = rawList[i]
                var n = item.name || ""
                var idx = n.indexOf("|Status:")
                var s = idx !== -1 ? n.substring(idx + 8) : (item.status || "")
                if (s !== "扩增文件" && s !== "扩展文件") {
                    sources.push({
                        id: item.id || 0,
                        name: (item.name || "未命名").split("|Status:")[0],
                        modality: item.modality || root.modalityFromLabel(item.type || ""),
                        stage: item.stage || "raw"
                    })
                }
            }
            if (sources.length === 0) sources.push({ id: 0, name: "无可用基础数据集 (请先导入)", modality: "", stage: "raw" })
            root.allSourceDatasets = sources
            root.applyDatasetFilter()
            root.loadGenerationAlgorithms()
        }

        function onGenerationStatusUpdated(message, success, progressVal) {
            root.showToast(success ? "✅ " + message : "⚠️ " + message)
            root.progress = progressVal / 100.0
            root.isGenerating = false
            if (success) {
                root.isCompleted = true
                if (root.currentTaskId > 0) {
                    backendService.getGenerationOutputs(root.currentTaskId, "", 1, 200)
                }
            } else {
                root.showGenerationFailure(message)
            }
        }

        function onEnhancementTasksUpdated(data) {
            var items = []
            if (data && data.items) items = data.items
            var historyItems = []
            for (var i = 0; i < items.length; i++) {
                var task = items[i]
                var sourceName = task.source_dataset_name || ("数据集#" + (task.source_dataset_id || ""))
                var targetName = task.target_dataset_name || ""
                var paramsObj = task.parameters || task.parameters_json || {}
                var payloadObj = task.payload || task.payload_json || {}
                var algorithmIds = root.normalizeAlgorithmIds(task)
                var targetCount = paramsObj.target_count || payloadObj.target_count || 0
                var algoDesc = root.formatParameters(algorithmIds, paramsObj)
                var historyItem = {
                    isSelected: false,
                    taskId: task.id || 0,
                    projectName: root.generationTaskTitle(task, sourceName),
                    sourceDataset: sourceName,
                    generatedDataset: targetName,
                    algos: algoDesc,
                    algorithmNames: root.algorithmNames(algorithmIds),
                    algorithmIds: algorithmIds,
                    algorithmIdsText: algorithmIds.join(","),
                    parameters: paramsObj,
                    parametersJsonText: JSON.stringify(paramsObj),
                    payload: payloadObj,
                    targetCount: targetCount,
                    path: task.output_dir || "",
                    time: task.created_at || "",
                    status: task.status || "",
                    progress: task.progress || 0,
                    progressMessage: task.progress_message || "",
                    errorMessage: task.error_message || ""
                }
                historyItems.push(historyItem)
                if (root.isGenerating && (task.id || 0) === root.currentTaskId) {
                    var pct = task.progress || 0
                    root.progress = pct / 100.0
                    root.currentCount = Math.floor(root.progress * root.totalCount)
                    root.currentTargetDatasetId = task.target_dataset_id || root.currentTargetDatasetId
                    if (targetName) {
                        root.currentTargetDatasetName = targetName
                    }
                    if (task.status === "failed" && root.lastFailureTaskId !== task.id) {
                        root.lastFailureTaskId = task.id
                        root.showGenerationFailure(task.error_message || task.progress_message || "生成任务执行失败")
                    }
                }
            }
            root.allGenerationHistoryItems = historyItems
            root.applyGenerationHistoryFilter()
        }

        function onAlgorithmsUpdated(algorithms) {
            if (!algorithms || !algorithms.length) return
            var map = {}
            var labelMap = {}
            var algorithmLabelMap = {}
            var old = root.algorithmNameMap
            if (old) {
                var oldKeys = Object.keys(old)
                for (var j = 0; j < oldKeys.length; j++) {
                    map[oldKeys[j]] = old[oldKeys[j]]
                }
            }
            var oldLabels = root.parameterLabelMap
            if (oldLabels) {
                var oldLabelKeys = Object.keys(oldLabels)
                for (var lk = 0; lk < oldLabelKeys.length; lk++) {
                    labelMap[oldLabelKeys[lk]] = oldLabels[oldLabelKeys[lk]]
                }
            }
            var oldAlgorithmLabels = root.algorithmParameterLabelMap
            if (oldAlgorithmLabels) {
                var oldAlgorithmLabelKeys = Object.keys(oldAlgorithmLabels)
                for (var ak = 0; ak < oldAlgorithmLabelKeys.length; ak++) {
                    algorithmLabelMap[oldAlgorithmLabelKeys[ak]] = oldAlgorithmLabels[oldAlgorithmLabelKeys[ak]]
                }
            }
            for (var i = 0; i < algorithms.length; i++) {
                var algo = algorithms[i]
                map[String(algo.id)] = algo.name || algo.key || ""
                var params = algo.parameters || []
                var perAlgorithmLabels = algorithmLabelMap[String(algo.id)] || {}
                for (var p = 0; p < params.length; p++) {
                    var param = params[p]
                    var paramName = String(param.name || "")
                    var paramLabel = String(param.label || "")
                    if (paramName && paramLabel && paramLabel !== paramName) {
                        labelMap[paramName] = paramLabel
                        perAlgorithmLabels[paramName] = paramLabel
                    }
                }
                algorithmLabelMap[String(algo.id)] = perAlgorithmLabels
            }
            root.algorithmNameMap = map
            root.parameterLabelMap = labelMap
            root.algorithmParameterLabelMap = algorithmLabelMap
            root.generationAlgorithms = algorithms
            root.paramsDataMap = root.buildParamsDataMap(algorithms)
            root.generationAlgorithmGroups = root.groupGenerationAlgorithms(algorithms)
            root.selectedStrategies = root.selectedStrategies.filter(function(id) {
                return root.algorithmById(id) !== null
            })
            root.refreshHistoryAlgorithmDescriptions()
        }

        function onGenerationOutputsUpdated(data) {
            previewModel.clear()
            var items = data.items || []
            for (var i = 0; i < items.length; i++) {
                var item = items[i]
                var srcSample = item.source_sample || {}
                var outSample = item.output_sample || {}
                var hasGenerated = item.status !== "source" && (item.output_sample_id || 0) > 0
                previewModel.append({
                    outputId: item.id || 0,
                    outputSampleId: item.output_sample_id || 0,
                    sourceSampleId: item.source_sample_id || srcSample.id || 0,
                    hasGenerated: hasGenerated,
                    sourceName: srcSample.name || ("\u6e90\u6837\u672c#" + (item.source_sample_id || "")),
                    generatedName: hasGenerated ? (outSample.name || ("\u751f\u6210\u6837\u672c#" + (item.output_sample_id || ""))) : "",
                    sourcePath: srcSample.path || srcSample.sample_path || "",
                    generatedPath: hasGenerated ? (outSample.path || outSample.sample_path || item.output_path || "") : "",
                    algoId: item.algorithm_id || 0,
                    status: item.status || ""
                })
            }
            if (items.length === 0 && root.isCompleted) {
                previewModel.append({
                    outputId: 0,
                    outputSampleId: 0,
                    sourceSampleId: 0,
                    hasGenerated: false,
                    sourceName: "\u751f\u6210\u4efb\u52a1\u5df2\u5b8c\u6210",
                    generatedName: "\u65e0\u751f\u6210\u8f93\u51fa\u8bb0\u5f55",
                    sourcePath: "",
                    generatedPath: "",
                    algoId: 0,
                    status: ""
                })
            }
        }

        function onSamplePreviewUpdated(data) {
            var payload = data && data.data ? data.data : data
            if (!payload || !payload.sample_id) return
            if (root.pendingPreviewId !== payload.sample_id) return
            root.pendingPreviewId = -1
            root.openSinglePreview(payload)
        }
    }

    // ================= 样本预览弹窗 =================
    Popup {
        id: samplePreviewPopup
        width: Math.max(400, Math.min(root.width * 0.92, root.comparisonPreviewMode ? 1040 : 760))
        height: Math.max(300, Math.min(root.height * 0.9, root.comparisonPreviewMode ? 620 : 560))
        x: Math.round((root.width - width) / 2)
        y: Math.round((root.height - height) / 2)
        modal: true
        focus: true
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        onClosed: {
            previewPlayer.stop()
            previewLeftPlayer.stop()
            previewRightPlayer.stop()
        }

        background: Rectangle {
            color: root.panelBg
            border.color: root.borderColor
            border.width: 1
            radius: 8
            clip: true
        }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 18
            spacing: 12

            RowLayout {
                Layout.fillWidth: true
                spacing: 10
                Text {
                    text: root.previewTitle
                    color: root.textColor
                    font.pixelSize: 16
                    font.bold: true
                    Layout.fillWidth: true
                    elide: Text.ElideRight
                }
                Button {
                    text: "\u5173\u95ed"
                    Layout.preferredWidth: 72
                    Layout.preferredHeight: 30
                    background: Rectangle { color: parent.hovered ? root.tableHoverBg : "transparent"; radius: 4; border.color: root.borderColor }
                    contentItem: Text { text: parent.text; color: root.textColor; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                    onClicked: samplePreviewPopup.close()
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                visible: !root.comparisonPreviewMode
                color: root.bgDark
                border.color: root.borderColor
                radius: 6
                clip: true

                Image {
                    anchors.fill: parent
                    anchors.margins: 12
                    visible: root.previewKind === "image" && root.previewSource !== ""
                    source: root.previewKind === "image" ? root.previewSource : ""
                    fillMode: Image.PreserveAspectFit
                    asynchronous: true
                }

                ScrollView {
                    anchors.fill: parent
                    anchors.margins: 12
                    visible: root.previewKind === "text"
                    TextArea {
                        text: root.previewText
                        readOnly: true
                        wrapMode: TextEdit.Wrap
                        color: root.textColor
                        selectByMouse: true
                        background: Rectangle { color: "transparent" }
                    }
                }

                ColumnLayout {
                    anchors.centerIn: parent
                    width: Math.min(parent.width - 60, 520)
                    spacing: 14
                    visible: root.previewKind === "audio"
                    Text {
                        text: root.previewTitle
                        color: root.textColor
                        font.pixelSize: 15
                        font.bold: true
                        Layout.fillWidth: true
                        horizontalAlignment: Text.AlignHCenter
                        elide: Text.ElideRight
                    }
                    Text {
                        text: root.previewSource !== "" ? root.previewSource : "\u65e0\u97f3\u9891\u8def\u5f84"
                        color: root.textMuted
                        font.pixelSize: 12
                        Layout.fillWidth: true
                        horizontalAlignment: Text.AlignHCenter
                        elide: Text.ElideMiddle
                    }
                    RowLayout {
                        Layout.alignment: Qt.AlignHCenter
                        spacing: 10
                        Button {
                            text: previewPlayer.playbackState === MediaPlayer.PlayingState ? "\u6682\u505c" : "\u64ad\u653e"
                            Layout.preferredWidth: 90
                            Layout.preferredHeight: 34
                            background: Rectangle { color: parent.hovered ? "#0288D1" : "#039BE5"; radius: 4 }
                            contentItem: Text { text: parent.text; color: "black"; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                            onClicked: {
                                if (previewPlayer.playbackState === MediaPlayer.PlayingState) previewPlayer.pause()
                                else previewPlayer.play()
                            }
                        }
                        Button {
                            text: "\u505c\u6b62"
                            Layout.preferredWidth: 70
                            Layout.preferredHeight: 34
                            background: Rectangle { color: parent.hovered ? root.tableHoverBg : "transparent"; border.color: root.borderColor; border.width: 1; radius: 4 }
                            contentItem: Text { text: parent.text; color: root.textColor; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                            onClicked: previewPlayer.stop()
                        }
                    }
                }

                ColumnLayout {
                    anchors.centerIn: parent
                    width: Math.min(parent.width - 60, 520)
                    spacing: 14
                    visible: root.previewKind !== "image" && root.previewKind !== "text" && root.previewKind !== "audio"
                    Rectangle {
                        width: 72; height: 72; radius: 12
                        color: root.tableHoverBg
                        Layout.alignment: Qt.AlignHCenter
                        Text { text: root.previewKind === "file" ? "\u6587\u4ef6" : "\u9644\u4ef6"; font.pixelSize: 18; anchors.centerIn: parent }
                    }
                    Text {
                        text: root.previewTitle
                        color: root.textColor
                        font.pixelSize: 15
                        font.bold: true
                        Layout.fillWidth: true
                        horizontalAlignment: Text.AlignHCenter
                        elide: Text.ElideRight
                    }
                    Text {
                        text: root.previewSource !== "" ? root.previewSource : "\u6587\u4ef6\u8def\u5f84\u4e0d\u53ef\u7528"
                        color: root.textMuted
                        font.pixelSize: 12
                        Layout.fillWidth: true
                        horizontalAlignment: Text.AlignHCenter
                        elide: Text.ElideMiddle
                    }
                    Text {
                        visible: root.previewText !== ""
                        text: root.previewText
                        color: root.textMuted
                        font.pixelSize: 12
                        Layout.fillWidth: true
                        horizontalAlignment: Text.AlignHCenter
                        wrapMode: Text.WordWrap
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                visible: root.comparisonPreviewMode
                spacing: 12

                Rectangle {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    color: root.bgDark
                    radius: 6
                    border.color: root.borderColor
                    clip: true
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 12
                        spacing: 8
                        Text { text: "\u6e90\u6837\u672c"; color: root.primaryColor; font.pixelSize: 14; font.bold: true; Layout.fillWidth: true }
                        Loader {
                            id: leftPreviewLoader
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            sourceComponent: previewContentComponent
                            onLoaded: item.setPreviewData(root.previewLeftData, previewLeftPlayer)
                            Connections {
                                target: root
                                function onPreviewLeftDataChanged() {
                                    if (leftPreviewLoader.item) leftPreviewLoader.item.setPreviewData(root.previewLeftData, previewLeftPlayer)
                                }
                            }
                        }
                    }
                }

                Text {
                    text: "\u2192"
                    color: root.primaryColor
                    font.pixelSize: 26
                    font.bold: true
                    visible: root.previewHasGenerated
                    Layout.alignment: Qt.AlignVCenter
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    visible: root.previewHasGenerated
                    color: root.bgDark
                    radius: 6
                    border.color: root.borderColor
                    clip: true
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 12
                        spacing: 8
                        Text { text: "\u751f\u6210\u6837\u672c"; color: root.successColor; font.pixelSize: 14; font.bold: true; Layout.fillWidth: true }
                        Loader {
                            id: rightPreviewLoader
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            sourceComponent: previewContentComponent
                            onLoaded: item.setPreviewData(root.previewRightData, previewRightPlayer)
                            Connections {
                                target: root
                                function onPreviewRightDataChanged() {
                                    if (rightPreviewLoader.item) rightPreviewLoader.item.setPreviewData(root.previewRightData, previewRightPlayer)
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    Component {
        id: previewContentComponent
        Item {
            id: previewContent
            property var payload: ({})
            property var player: null
            property string kind: payload.preview_kind || "file"
            property string fileSource: root.previewFileSource(payload)
            property string title: root.previewDisplayName(payload, "\u6837\u672c\u9884\u89c8")
            property string textBody: payload.text_content || payload.error || ""

            function setPreviewData(data, audioPlayer) {
                payload = data || {}
                player = audioPlayer
                if (kind === "audio" && fileSource !== "" && player) player.source = fileSource
            }

            Image {
                anchors.fill: parent
                visible: previewContent.kind === "image" && previewContent.fileSource !== ""
                source: visible ? previewContent.fileSource : ""
                fillMode: Image.PreserveAspectFit
                asynchronous: true
            }

            ScrollView {
                anchors.fill: parent
                visible: previewContent.kind === "text"
                TextArea {
                    text: previewContent.textBody
                    readOnly: true
                    wrapMode: TextEdit.Wrap
                    color: root.textColor
                    selectByMouse: true
                    background: Rectangle { color: "transparent" }
                }
            }

            ColumnLayout {
                anchors.centerIn: parent
                width: Math.min(parent.width - 36, 360)
                spacing: 12
                visible: previewContent.kind === "audio"
                Text {
                    text: previewContent.title
                    color: root.textColor
                    font.pixelSize: 13
                    font.bold: true
                    Layout.fillWidth: true
                    horizontalAlignment: Text.AlignHCenter
                    elide: Text.ElideRight
                }
                Text {
                    text: previewContent.fileSource !== "" ? previewContent.fileSource : "\u65e0\u97f3\u9891\u8def\u5f84"
                    color: root.textMuted
                    font.pixelSize: 11
                    Layout.fillWidth: true
                    horizontalAlignment: Text.AlignHCenter
                    elide: Text.ElideMiddle
                }
                RowLayout {
                    Layout.alignment: Qt.AlignHCenter
                    spacing: 8
                    Button {
                        text: previewContent.player && previewContent.player.playbackState === MediaPlayer.PlayingState ? "\u6682\u505c" : "\u64ad\u653e"
                        Layout.preferredWidth: 74
                        Layout.preferredHeight: 30
                        enabled: previewContent.player !== null && previewContent.fileSource !== ""
                        background: Rectangle { color: parent.enabled ? (parent.hovered ? "#0288D1" : "#039BE5") : Theme.border; radius: 4 }
                        contentItem: Text { text: parent.text; color: parent.enabled ? "black" : root.textMuted; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                        onClicked: {
                            if (!previewContent.player) return
                            if (previewContent.player.playbackState === MediaPlayer.PlayingState) previewContent.player.pause()
                            else previewContent.player.play()
                        }
                    }
                    Button {
                        text: "\u505c\u6b62"
                        Layout.preferredWidth: 62
                        Layout.preferredHeight: 30
                        enabled: previewContent.player !== null
                        background: Rectangle { color: parent.hovered ? root.tableHoverBg : "transparent"; border.color: root.borderColor; border.width: 1; radius: 4 }
                        contentItem: Text { text: parent.text; color: root.textColor; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                        onClicked: if (previewContent.player) previewContent.player.stop()
                    }
                }
            }

            ColumnLayout {
                anchors.centerIn: parent
                width: Math.min(parent.width - 36, 360)
                spacing: 12
                visible: previewContent.kind !== "image" && previewContent.kind !== "text" && previewContent.kind !== "audio"
                Rectangle {
                    width: 64; height: 64; radius: 8
                    color: root.tableHoverBg
                    Layout.alignment: Qt.AlignHCenter
                    Text { text: "\u6587\u4ef6"; font.pixelSize: 16; anchors.centerIn: parent }
                }
                Text {
                    text: previewContent.title
                    color: root.textColor
                    font.pixelSize: 13
                    font.bold: true
                    Layout.fillWidth: true
                    horizontalAlignment: Text.AlignHCenter
                    elide: Text.ElideRight
                }
                Text {
                    text: previewContent.fileSource !== "" ? previewContent.fileSource : "\u6587\u4ef6\u8def\u5f84\u4e0d\u53ef\u7528"
                    color: root.textMuted
                    font.pixelSize: 11
                    Layout.fillWidth: true
                    horizontalAlignment: Text.AlignHCenter
                    elide: Text.ElideMiddle
                }
                Text {
                    visible: previewContent.textBody !== ""
                    text: previewContent.textBody
                    color: root.textMuted
                    font.pixelSize: 11
                    Layout.fillWidth: true
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.WordWrap
                }
            }
        }
    }

    MediaPlayer {
        id: previewPlayer
        autoPlay: false
        audioOutput: previewAudio
    }

    AudioOutput {
        id: previewAudio
    }

    MediaPlayer {
        id: previewLeftPlayer
        autoPlay: false
        audioOutput: previewLeftAudio
    }

    AudioOutput {
        id: previewLeftAudio
    }

    MediaPlayer {
        id: previewRightPlayer
        autoPlay: false
        audioOutput: previewRightAudio
    }

    AudioOutput {
        id: previewRightAudio
    }

    Timer {
        id: progressPollTimer
        interval: 1000
        repeat: true
        running: root.isGenerating && root.currentTaskId > 0
        onTriggered: {
            backendService.getEnhancementTasks(0, "")
        }
    }

    Component.onCompleted: {
        root.loadGenerationParameterPresets()
        backendService.getDatasets(1, 100, "")
        backendService.getAlgorithms("generation", "")
        backendService.getEnhancementTasks(0, "")
    }

    function getCurrentTime() {
        var date = new Date()
        var y = date.getFullYear()
        var m = (date.getMonth() + 1).toString().padStart(2, '0')
        var d = date.getDate().toString().padStart(2, '0')
        var h = date.getHours().toString().padStart(2, '0')
        var min = date.getMinutes().toString().padStart(2, '0')
        return y + "-" + m + "-" + d + " " + h + ":" + min
    }

    // ================= Toast =================
    property string toastMessage: "✅ 任务执行成功"
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
        background: Rectangle {
            color: root.successColor
            radius: 20
        }
        contentItem: Text {
            id: toastText
            text: root.toastMessage
            color: "black"
            font.pixelSize: 14
            font.bold: true
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }
        SequentialAnimation {
            id: toastAnim
            NumberAnimation { target: toastMsg; property: "opacity"; to: 1.0; duration: 300 }
        }
    }

    function showToast(msg) {
        root.toastMessage = msg
        toastMsg.open()
        toastAnim.restart()
        toastCloseTimer.restart()
    }

    Timer {
        id: toastCloseTimer
        interval: 2300
        onTriggered: {
            toastMsg.opacity = 0
            toastMsg.close()
        }
    }

    Component.onDestruction: {
        toastCloseTimer.stop()
        progressPollTimer.stop()
        previewPlayer.stop()
    }

    // ================= 生成失败弹窗 =================
    Popup {
        id: generationFailurePopup
        width: 460
        height: 240
        modal: true
        focus: true
        x: Math.round((root.width - width) / 2)
        y: Math.round((root.height - height) / 2)
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: Rectangle { color: root.panelBg; radius: 8; border.color: root.dangerColor; border.width: 1 }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 20
            spacing: 14

            Text { text: "生成任务失败"; color: root.dangerColor; font.pixelSize: 18; font.bold: true }
            Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: root.borderColor }
            Text {
                text: root.generationErrorMessage
                color: root.textColor
                font.pixelSize: 13
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
                Layout.fillHeight: true
            }
            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                Button {
                    id: generationFailureOkButton
                    text: "知道了"
                    Layout.preferredWidth: 96
                    Layout.preferredHeight: 34
                    background: Rectangle { color: generationFailureOkButton.hovered ? "#BE123C" : root.dangerColor; radius: 4 }
                    contentItem: Text { text: generationFailureOkButton.text; color: "black"; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; font.bold: true }
                    onClicked: generationFailurePopup.close()
                }
            }
        }
    }

    // ================= 保存生成结果弹窗 =================
    Popup {
        id: savePopup
        width: 460
        height: 300
        modal: true
        focus: true
        x: Math.round((root.width - width) / 2)
        y: Math.round((root.height - height) / 2)
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: Rectangle { color: root.panelBg; radius: 8; border.color: root.borderColor; border.width: 1 }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 20
            spacing: 15
            Text { text: "💾 确认保存生成结果"; color: root.textColor; font.pixelSize: 16; font.bold: true }
            Rectangle { Layout.fillWidth: true; height: 1; color: root.borderColor }

            ColumnLayout {
                spacing: 5
                Layout.fillWidth: true
                Text { text: "生成数据集名称:"; color: root.textMuted; font.pixelSize: 12 }
                Rectangle {
                    Layout.fillWidth: true; height: 36; color: root.bgDark; radius: 4; border.color: root.borderColor; border.width: 1
                    TextInput {
                        id: saveDatasetNameInput
                        color: root.textColor; font.pixelSize: 13
                        anchors.fill: parent; leftPadding: 10; verticalAlignment: TextInput.AlignVCenter; selectByMouse: true
                    }
                }
            }

            Text {
                text: "保存路径由系统自动管理 (data/datasets/...)"
                color: root.textMuted; font.pixelSize: 11; Layout.fillWidth: true; wrapMode: Text.WordWrap
            }

            Item { Layout.fillHeight: true }

            RowLayout {
                Layout.fillWidth: true
                spacing: 15
                Item { Layout.fillWidth: true }
                Button {
                    text: "取消"
                    Layout.preferredWidth: 80; Layout.preferredHeight: 34
                    background: Rectangle { color: "transparent"; border.color: root.borderColor; border.width: 1; radius: 4 }
                    contentItem: Text { text: parent.text; color: root.textMuted; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                    onClicked: savePopup.close()
                }
                Button {
                    text: "确认保存"
                    Layout.preferredWidth: 100; Layout.preferredHeight: 34
                    background: Rectangle { color: root.primaryColor; radius: 4 }
                    contentItem: Text { text: parent.text; color: "black"; font.bold: true; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                    onClicked: {
                        var newDatasetName = saveDatasetNameInput.text.trim()
                        if (root.currentTaskId <= 0 || root.currentTargetDatasetId <= 0) {
                            root.showToast("⚠️ 没有可保存的生成任务")
                            return
                        }
                        if (newDatasetName === "") {
                            root.showToast("⚠️ 请输入生成数据集名称")
                            return
                        }
                        var result = backendService.updateDataset(root.currentTargetDatasetId, newDatasetName, "")
                        if (result && result.status === "success") {
                            root.currentTargetDatasetName = newDatasetName
                            backendService.getDatasets(1, 100, "")
                            backendService.getEnhancementTasks(0, "")
                            root.showToast("✅ 生成结果已保存")
                        } else {
                            root.showToast("⚠️ " + ((result && result.message) ? result.message : "保存失败"))
                            return
                        }
                        savePopup.close()
                        newGenerationTaskPopup.close()
                        previewModel.clear()
                        root.currentCount = 0
                        root.isCompleted = false
                        root.currentTaskId = 0
                        root.currentTargetDatasetId = 0
                        root.currentTargetDatasetName = ""
                    }
                }
            }
        }
    }

    // ================= 保存生成参数记录弹窗 =================
    Popup {
        id: parameterPresetNamePopup
        width: 420
        height: 240
        modal: true
        focus: true
        x: Math.round((root.width - width) / 2)
        y: Math.round((root.height - height) / 2)
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: Rectangle { color: root.panelBg; radius: 8; border.color: root.borderColor; border.width: 1 }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 22
            spacing: 12

            Text { text: "记录生成参数"; color: root.textColor; font.pixelSize: 16; font.bold: true }
            Text {
                text: "为本次任务的参数配置起一个名字，之后可在新建任务中复用。"
                color: root.textMuted
                font.pixelSize: 12
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 36
                color: root.bgDark
                radius: 4
                border.color: root.borderColor
                border.width: 1
                TextInput {
                    id: parameterPresetNameInput
                    color: root.textColor
                    font.pixelSize: 13
                    anchors.fill: parent
                    leftPadding: 10
                    verticalAlignment: TextInput.AlignVCenter
                    selectByMouse: true
                }
            }
            Item { Layout.fillHeight: true; Layout.minimumHeight: 8 }
            RowLayout {
                Layout.fillWidth: true
                Layout.preferredHeight: 34
                spacing: 12
                Item { Layout.fillWidth: true }
                Button {
                    id: cancelParameterPresetButton
                    text: "取消"
                    Layout.preferredWidth: 80
                    Layout.preferredHeight: 32
                    background: Rectangle { color: "transparent"; border.color: root.borderColor; border.width: 1; radius: 4 }
                    contentItem: Text { text: cancelParameterPresetButton.text; color: root.textMuted; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                    onClicked: parameterPresetNamePopup.close()
                }
                Button {
                    id: saveParameterPresetButton
                    text: "保存记录"
                    Layout.preferredWidth: 92
                    Layout.preferredHeight: 32
                    background: Rectangle { color: root.primaryColor; radius: 4 }
                    contentItem: Text { text: saveParameterPresetButton.text; color: "black"; font.bold: true; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                    onClicked: {
                        if (root.saveCurrentDetailParameterPreset(parameterPresetNameInput.text)) {
                            parameterPresetNamePopup.close()
                        }
                    }
                }
            }
        }
    }

    // ================= 修改工程名弹窗 =================
    Popup {
        id: editProjectPopup
        width: 360
        height: 180
        modal: true
        focus: true
        x: Math.round((root.width - width) / 2)
        y: Math.round((root.height - height) / 2)
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: Rectangle { color: root.panelBg; radius: 8; border.color: root.borderColor; border.width: 1 }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 20
            spacing: 15
            Text { text: "✏️ 修改工程名称"; color: root.textColor; font.pixelSize: 16; font.bold: true }
            Rectangle {
                Layout.fillWidth: true; height: 36; color: root.bgDark; radius: 4; border.color: root.borderColor; border.width: 1
                TextInput {
                    id: editProjectNameInput
                    color: root.primaryColor; font.pixelSize: 13; font.bold: true
                    anchors.fill: parent; leftPadding: 10; verticalAlignment: TextInput.AlignVCenter; selectByMouse: true
                }
            }
            Item { Layout.fillHeight: true }
            RowLayout {
                Layout.fillWidth: true
                spacing: 15
                Item { Layout.fillWidth: true }
                Button {
                    text: "取消"
                    Layout.preferredWidth: 80; Layout.preferredHeight: 32
                    background: Rectangle { color: "transparent"; border.color: root.borderColor; border.width: 1; radius: 4 }
                    contentItem: Text { text: parent.text; color: root.textMuted; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                    onClicked: editProjectPopup.close()
                }
                Button {
                    text: "保存"
                    Layout.preferredWidth: 80; Layout.preferredHeight: 32
                    background: Rectangle { color: root.primaryColor; radius: 4 }
                    contentItem: Text { text: parent.text; color: "black"; font.bold: true; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                    onClicked: {
                        if (root.pendingEditIndex !== -1 && editProjectNameInput.text.trim() !== "") {
                            generationHistoryModel.setProperty(root.pendingEditIndex, "projectName", editProjectNameInput.text)
                            root.showToast("✅ 工程名称已更新")
                        }
                        editProjectPopup.close()
                    }
                }
            }
        }
    }

    // ================= 删除确认弹窗 =================
    Popup {
        id: deleteConfirmPopup
        width: 320
        height: 190
        modal: true
        focus: true
        x: Math.round((root.width - width) / 2)
        y: Math.round((root.height - height) / 2)
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: Rectangle { color: root.panelBg; radius: 8; border.color: root.dangerColor; border.width: 1 }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 20
            spacing: 15
            RowLayout {
                spacing: 10
                Text { text: "⚠️"; font.pixelSize: 20 }
                Text { text: "确认删除此生成记录吗？"; color: root.textColor; font.pixelSize: 15; font.bold: true }
            }
            Text { text: "删除后将无法恢复，相关文件依然保留在磁盘中。"; color: root.textMuted; font.pixelSize: 12; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            Item { Layout.fillHeight: true }
            RowLayout {
                Layout.fillWidth: true
                spacing: 15
                Item { Layout.fillWidth: true }
                Button {
                    text: "取消"
                    Layout.preferredWidth: 80; Layout.preferredHeight: 30
                    background: Rectangle { color: "transparent"; border.color: root.borderColor; border.width: 1; radius: 4 }
                    contentItem: Text { text: parent.text; color: root.textMuted; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                    onClicked: deleteConfirmPopup.close()
                }
                Button {
                    text: "确认删除"
                    Layout.preferredWidth: 80; Layout.preferredHeight: 30
                    background: Rectangle { color: root.dangerColor; radius: 4 }
                    contentItem: Text { text: parent.text; color: "black"; font.bold: true; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                    onClicked: {
                        if (root.pendingDeleteIndex !== -1) {
                            var item = generationHistoryModel.get(root.pendingDeleteIndex)
                            if (item && item.taskId > 0) {
                                var result = backendService.deleteTask(item.taskId)
                                if (result && result.status === "success") {
                                    generationHistoryModel.remove(root.pendingDeleteIndex)
                                    root.updateExportCount()
                                    root.showToast("记录已删除")
                                } else {
                                    root.showToast("删除失败: " + ((result && result.message) ? result.message : "未知错误"))
                                }
                            } else {
                                generationHistoryModel.remove(root.pendingDeleteIndex)
                                root.updateExportCount()
                                root.showToast("记录已删除")
                            }
                        }
                        deleteConfirmPopup.close()
                    }
                }
            }
        }
    }

    // ================= 导出弹窗 =================
    FolderDialog {
        id: exportFolderDialog
        title: "选择导出合并的目标文件夹"
        onAccepted: {
            var path = selectedFolder.toString()
            exportPathInput.text = decodeURIComponent(path.replace(/^(file:\/{2,3})/, ""))
        }
    }

    Popup {
        id: exportPopup
        width: 450
        height: 250
        modal: true
        focus: true
        x: Math.round((root.width - width) / 2)
        y: Math.round((root.height - height) / 2)
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: Rectangle { color: root.panelBg; radius: 8; border.color: root.borderColor; border.width: 1 }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 20
            spacing: 15
            Text { text: "📥 导出合并选中的数据集"; color: root.textColor; font.pixelSize: 16; font.bold: true }
            Rectangle { Layout.fillWidth: true; height: 1; color: root.borderColor }
            Text {
                text: "已选中 " + root.selectedExportCount + " 个扩增数据集。"
                color: root.textMuted; font.pixelSize: 13; wrapMode: Text.WordWrap; Layout.fillWidth: true
            }
            ColumnLayout {
                spacing: 5
                Layout.fillWidth: true
                Text { text: "目标导出路径:"; color: root.textMuted; font.pixelSize: 12 }
                RowLayout {
                    Layout.fillWidth: true; spacing: 10
                    Rectangle {
                        Layout.fillWidth: true; height: 36; color: root.bgDark; radius: 4; border.color: root.borderColor; border.width: 1
                        TextInput {
                            id: exportPathInput
                            text: "/data/export/merged_aug_data/"
                            color: root.textColor; font.pixelSize: 13; anchors.fill: parent; leftPadding: 10; verticalAlignment: TextInput.AlignVCenter
                        }
                    }
                    Button {
                        text: "浏览"; Layout.preferredHeight: 36
                        background: Rectangle { color: root.tableHoverBg; radius: 4; border.color: root.borderColor; border.width: 1 }
                        contentItem: Text { text: parent.text; color: root.textColor; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                        onClicked: exportFolderDialog.open()
                    }
                }
            }
            Item { Layout.fillHeight: true }
            RowLayout {
                Layout.fillWidth: true; spacing: 15
                Item { Layout.fillWidth: true }
                Button {
                    text: "取消"; Layout.preferredWidth: 80; Layout.preferredHeight: 34
                    background: Rectangle { color: "transparent"; border.color: root.borderColor; border.width: 1; radius: 4 }
                    contentItem: Text { text: parent.text; color: root.textMuted; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                    onClicked: exportPopup.close()
                }
                Button {
                    text: "开始打包导出"; Layout.preferredWidth: 120; Layout.preferredHeight: 34
                    background: Rectangle { color: root.primaryColor; radius: 4 }
                    contentItem: Text { text: parent.text; color: "black"; font.bold: true; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                    onClicked: {
                        exportPopup.close()
                        for (var i = 0; i < generationHistoryModel.count; i++) {
                            generationHistoryModel.setProperty(i, "isSelected", false)
                        }
                        root.updateExportCount()
                        root.showToast("🚀 选中的数据集已开始合并打包导出")
                    }
                }
            }
        }
    }

    // ================= 新建生成任务弹窗 =================
    Popup {
        id: newGenerationTaskPopup
        width: Math.max(600, Math.min(1250, root.width * 0.95))
        height: Math.max(500, Math.min(850, root.height * 0.95))
        modal: true
        focus: true
        x: Math.round((root.width - width) / 2)
        y: Math.round((root.height - height) / 2)
        closePolicy: root.isGenerating ? Popup.NoAutoClose : (Popup.CloseOnEscape | Popup.CloseOnPressOutside)
        onOpened: root.loadGenerationParameterPresets()
        background: Rectangle { color: root.bgDark; radius: 8; border.color: root.borderColor; border.width: 1 }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 20
            spacing: 15

            RowLayout {
                Layout.fillWidth: true
                Text { text: "✨ 新建多策略数据扩增/生成任务"; color: root.textColor; font.pixelSize: 18; font.bold: true }
                Item { Layout.fillWidth: true }
                Rectangle {
                    width: 30; height: 30; color: "transparent"; radius: 4
                    Text { text: "✕"; color: root.textMuted; font.pixelSize: 18; anchors.centerIn: parent }
                    MouseArea {
                        anchors.fill: parent; cursorShape: Qt.PointingHandCursor; hoverEnabled: true
                        onEntered: parent.color = root.dangerColor
                        onExited: parent.color = "transparent"
                        onClicked: {
                            if (root.isGenerating) {
                                root.showToast("⚠️ 请先停止正在进行的生成任务")
                            } else {
                                newGenerationTaskPopup.close()
                            }
                        }
                    }
                }
            }

            Rectangle { Layout.fillWidth: true; height: 1; color: root.borderColor }

            // 顶部控制面板
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 90
                color: root.panelBg
                radius: 8
                border.color: root.borderColor
                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 15
                    spacing: 12
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 20

                        RowLayout {
                            spacing: 8
                            Text { text: "📁 基准源数据:"; color: root.textMuted; font.pixelSize: 13 }
                            RowLayout {
                                spacing: 4
                                Repeater {
                                    model: [
                                        { stage: "raw", label: "原始" },
                                        { stage: "cleaned", label: "清洗" },
                                        { stage: "generated", label: "生成" },
                                        { stage: "all", label: "全部" }
                                    ]
                                    delegate: Rectangle {
                                        height: 26; width: filterLabel.contentWidth + 16; radius: 13
                                        color: root.datasetTypeFilter === modelData.stage ? root.stageColor(modelData.stage) : root.bgDark
                                        border.color: root.datasetTypeFilter === modelData.stage ? root.stageColor(modelData.stage) : root.borderColor
                                        border.width: 1
                                        Text {
                                            id: filterLabel
                                            text: modelData.label; color: root.datasetTypeFilter === modelData.stage ? "#0D1117" : root.stageColor(modelData.stage)
                                            font.pixelSize: 11; font.bold: root.datasetTypeFilter === modelData.stage
                                            anchors.centerIn: parent
                                        }
                                        MouseArea {
                                            anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                                            onClicked: {
                                                root.datasetTypeFilter = modelData.stage
                                                root.applyDatasetFilter()
                                                sourceDataCombo.currentIndex = 0
                                                root.selectedStrategies = []
                                                root.loadGenerationAlgorithms()
                                            }
                                        }
                                    }
                                }
                            }
                            StableComboBox {
                                id: sourceDataCombo
                                model: root.sourceDatasets
                                textRole: "name"
                                Layout.preferredWidth: 200
                                Layout.preferredHeight: 32
                                background: Rectangle { color: root.bgDark; border.color: root.borderColor; radius: 4 }
                                contentItem: RowLayout {
                                    spacing: 6
                                    Rectangle {
                                        width: 8; height: 8; radius: 4
                                        color: {
                                            var ds = root.sourceDatasets[sourceDataCombo.currentIndex]
                                            return ds ? root.stageColor(ds.stage || "raw") : root.textMuted
                                        }
                                    }
                                    Text {
                                        text: sourceDataCombo.currentText
                                        color: root.textColor
                                        verticalAlignment: Text.AlignVCenter
                                        elide: Text.ElideRight
                                        Layout.fillWidth: true
                                    }
                                }
                                onCurrentIndexChanged: {
                                    root.selectedStrategies = []
                                    root.loadGenerationAlgorithms()
                                }
                            }
                        }

                        RowLayout {
                            spacing: 8
                            Text { text: "🔢 扩增目标数:"; color: root.textMuted; font.pixelSize: 13 }
                            Rectangle {
                                width: 80; height: 32; color: root.bgDark; radius: 4; border.color: root.primaryColor
                                TextInput {
                                    text: root.totalCount.toString()
                                    color: root.primaryColor; font.bold: true; font.family: "Courier"; font.pixelSize: 13
                                    anchors.centerIn: parent; verticalAlignment: TextInput.AlignVCenter
                                    onTextChanged: { var val = parseInt(text); root.totalCount = isNaN(val) ? 1000 : val; }
                                }
                            }
                            Text { text: "条"; color: root.textMuted; font.pixelSize: 12 }
                        }

                        Item { Layout.fillWidth: true }

                        Rectangle {
                            width: 150; height: 36; radius: 4
                            color: root.selectedStrategies.length === 0 ? Theme.border : (root.isGenerating ? Theme.muted : root.primaryColor)
                            opacity: root.selectedStrategies.length === 0 ? 0.5 : 1.0
                            Text { text: root.isGenerating ? "⏹ 停止生成" : "▶ 开始生成任务"; color: "#FFFFFF"; font.bold: true; font.pixelSize: 13; anchors.centerIn: parent }
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: root.selectedStrategies.length === 0 ? Qt.ArrowCursor : Qt.PointingHandCursor
                                onClicked: {
                                    if (root.selectedStrategies.length === 0) return
                                    if (!root.isGenerating) {
                                        var source = root.currentSourceDataset()
                                        if (!source || !source.id) {
                                            root.showToast("⚠️ 请先选择可用源数据集")
                                            return
                                        }
                                        var algoIds = root.selectedStrategies.slice()
                                        var algoStr = algoIds.join(",")
                                        var params = {}
                                        for (var pi = 0; pi < algoIds.length; pi++) {
                                            var pid = algoIds[pi]
                                            var plist = root.paramsDataMap[String(pid)] || []
                                            for (var pj = 0; pj < plist.length; pj++) {
                                                if (plist[pj].v !== undefined && plist[pj].v !== "") {
                                                    params[plist[pj].n] = plist[pj].v
                                                }
                                            }
                                        }
                                        var taskResult = backendService.createEnhancementTask(source.id, algoStr, params, root.totalCount)
                                        if (!taskResult || taskResult.status !== "success") {
                                            root.showToast("⚠️ " + (taskResult && taskResult.message ? taskResult.message : "生成任务创建失败"))
                                            return
                                        }
                                        root.currentTaskId = taskResult.id || 0
                                        root.currentTargetDatasetId = taskResult.target_dataset_id || 0
                                        root.lastFailureTaskId = 0
                                        root.currentTargetDatasetName = taskResult.target_dataset_name || ""
                                        root.currentCount = 0
                                        root.progress = 0
                                        root.isCompleted = false
                                        previewModel.clear()
                                        backendService.startEnhancementTask(root.currentTaskId)
                                        root.showToast("✅ 生成任务已启动 (" + root.currentTaskId + ")")
                                    } else {
                                        backendService.stopEnhancementTask(root.currentTaskId)
                                        root.showToast("⏹ 已请求停止任务")
                                    }
                                    root.isGenerating = !root.isGenerating
                                }
                            }
                        }
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 4
                        RowLayout {
                            Layout.fillWidth: true
                            Text {
                                text: root.isGenerating ? "生成引擎运行中" : (root.isCompleted ? "✅ 数据扩增已完成" : "请在下方勾选所需生成策略并启动")
                                color: root.isCompleted ? root.successColor : root.primaryColor
                                font.pixelSize: 12; font.bold: true
                            }
                            Item { Layout.fillWidth: true }
                            Text { text: root.currentCount + " / " + root.totalCount + " (" + Math.floor(root.progress * 100) + "%)"; color: root.textMuted; font.pixelSize: 12; font.bold: true }
                        }
                        Rectangle {
                            Layout.fillWidth: true; height: 4; color: root.bgDark; radius: 2
                            Rectangle {
                                width: parent.width * root.progress; height: parent.height
                                color: root.isCompleted ? root.successColor : root.primaryColor
                                radius: 2
                                Behavior on width { NumberAnimation { duration: 100 } }
                            }
                        }
                    }
                }
            }

            // 三栏布局
            RowLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 15

                // 左栏：算法选择
                Rectangle {
                    Layout.preferredWidth: 260
                    Layout.fillHeight: true
                    color: root.panelBg
                    radius: 8
                    border.color: root.borderColor
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 15
                        spacing: 15
                        Text { text: "📂 生成算法选择 (可多选)"; color: root.textColor; font.bold: true; font.pixelSize: 15 }
                        ScrollView {
                            Layout.fillWidth: true; Layout.fillHeight: true; clip: true; contentWidth: availableWidth
                            Column {
                                width: parent.width; spacing: 5
                                Repeater {
                                    model: root.generationAlgorithmGroups
                                    delegate: Column {
                                        width: parent.width; spacing: 2
                                        property bool isExpanded: true
                                        Rectangle {
                                            width: parent.width; height: 38; radius: 4; color: isExpanded ? Theme.hover : "transparent"
                                            Text { text: (isExpanded ? "▼ " : "▶ ") + modelData.t; color: root.textColor; font.pixelSize: 13; anchors.verticalCenter: parent.verticalCenter; anchors.left: parent.left; anchors.leftMargin: 12 }
                                            MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: isExpanded = !isExpanded }
                                        }
                                        Column {
                                            visible: isExpanded; width: parent.width; spacing: 2
                                            Repeater {
                                                model: modelData.m
                                                delegate: Rectangle {
                                                    property int algoId: Number(modelData.id)
                                                    width: parent.width; height: 34; radius: 4
                                                    color: root.selectedStrategies.indexOf(algoId) !== -1 ? root.tableHoverBg : "transparent"
                                                    RowLayout {
                                                        anchors.fill: parent; anchors.leftMargin: 25; spacing: 10
                                                        Rectangle {
                                                            width: 14; height: 14; radius: 2
                                                            border.color: root.selectedStrategies.indexOf(algoId) !== -1 ? root.primaryColor : root.textMuted
                                                            color: root.selectedStrategies.indexOf(algoId) !== -1 ? root.primaryColor : "transparent"
                                                            Text { text: "✓"; font.pixelSize: 10; color: "white"; anchors.centerIn: parent; visible: root.selectedStrategies.indexOf(algoId) !== -1 }
                                                        }
                                                        Text { text: modelData.name || modelData.key || "未命名算法"; color: root.selectedStrategies.indexOf(algoId) !== -1 ? root.textColor : root.textMuted; font.pixelSize: 12; Layout.fillWidth: true; elide: Text.ElideRight }
                                                    }
                                                    MouseArea {
                                                        anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                                                        onClicked: {
                                                            var arr = root.selectedStrategies.slice()
                                                            var idx = arr.indexOf(algoId)
                                                            if (idx !== -1) arr.splice(idx, 1)
                                                            else arr.push(algoId)
                                                            root.selectedStrategies = arr
                                                            root.isCompleted = false
                                                            previewModel.clear()
                                                            root.currentCount = 0
                                                        }
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                                Text {
                                    visible: root.generationAlgorithmGroups.length === 0
                                    text: "当前源数据集没有可用生成算法\n请先在算法与参数配置中启用或注册生成算法"
                                    color: root.textMuted; font.pixelSize: 12; wrapMode: Text.WordWrap
                                    width: parent.width; horizontalAlignment: Text.AlignHCenter
                                }
                            }
                        }
                    }
                }

                // 中栏：参数配置
                Rectangle {
                    Layout.preferredWidth: 260
                    Layout.fillHeight: true
                    color: root.panelBg
                    radius: 8
                    border.color: root.borderColor
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 15
                        spacing: 15
                        Text { text: "⚙️ 综合参数配置"; color: root.textColor; font.bold: true; font.pixelSize: 14; Layout.fillWidth: true }
                        Text { visible: root.selectedStrategies.length === 0; text: "👈 请在左侧勾选生成算法\n可以同时选择多个"; color: root.textMuted; font.pixelSize: 12; horizontalAlignment: Text.AlignHCenter; Layout.alignment: Qt.AlignCenter; Layout.fillHeight: true }
                        ScrollView {
                            Layout.fillWidth: true; Layout.fillHeight: true; clip: true; contentWidth: availableWidth; visible: root.selectedStrategies.length > 0
                            Column {
                                width: parent.width; spacing: 20
                                Repeater {
                                    model: root.selectedStrategies
                                    delegate: Column {
                                        id: selectedAlgoDelegate
                                        property int selectedAlgoId: Number(modelData)
                                        width: parent.width; spacing: 10
                                        Text { text: "🔹 " + root.algorithmName(selectedAlgoId); color: root.primaryColor; font.bold: true; font.pixelSize: 13 }
                                        Column {
                                            width: parent.width; spacing: 10
                                            Repeater {
                                                model: root.paramsDataMap[String(selectedAlgoId)] || []
                                                delegate: Column {
                                                    width: parent.width; spacing: 6
                                                    Text { text: modelData.label || modelData.n; color: root.textMuted; font.pixelSize: 12 }
                                                    // 有options → 下拉框
                                                    StableComboBox {
                                                        visible: modelData.options && modelData.options.length > 0
                                                        width: parent.width; height: 36
                                                        model: modelData.options || []
                                                        currentIndex: {
                                                            var cv = modelData.v !== undefined ? String(modelData.v) : ""
                                                            var opts = modelData.options || []
                                                            for (var oi = 0; oi < opts.length; oi++) {
                                                                if (String(opts[oi]) === cv) return oi
                                                            }
                                                            return 0
                                                        }
                                                        onCurrentIndexChanged: {
                                                            var opts = modelData.options || []
                                                            if (currentIndex >= 0 && currentIndex < opts.length) {
                                                                var paramList = root.paramsDataMap[String(selectedAlgoDelegate.selectedAlgoId)]
                                                                for (var pi = 0; pi < paramList.length; pi++) {
                                                                    if (paramList[pi].n === modelData.n) {
                                                                        paramList[pi].v = opts[currentIndex]
                                                                        break
                                                                    }
                                                                }
                                                            }
                                                        }
                                                    }
                                                    // 无options → 文本输入
                                                    Rectangle {
                                                        visible: !modelData.options || modelData.options.length === 0
                                                        width: parent.width; height: 36; color: root.bgDark; radius: 4; border.color: root.borderColor; border.width: 1
                                                        TextInput {
                                                            text: modelData.v
                                                            color: root.textColor; font.pixelSize: 13; anchors.fill: parent; leftPadding: 10; verticalAlignment: TextInput.AlignVCenter
                                                            onTextChanged: {
                                                                var paramList = root.paramsDataMap[String(selectedAlgoDelegate.selectedAlgoId)]
                                                                for (var pi = 0; pi < paramList.length; pi++) {
                                                                    if (paramList[pi].n === modelData.n) {
                                                                        paramList[pi].v = text
                                                                        break
                                                                    }
                                                                }
                                                            }
                                                        }
                                                    }
                                                }
                                            }
                                        }
                                        Rectangle { width: parent.width; height: 1; color: root.borderColor; visible: index !== root.selectedStrategies.length - 1 }
                                    }
                                }
                            }
                        }
                        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: root.borderColor }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 6
                            Text { text: "参数记录"; color: root.textMuted; font.pixelSize: 12 }
                            Item {
                                id: parameterPresetSelector
                                Layout.fillWidth: true
                                Layout.preferredHeight: 36

                                StableComboBox {
                                    id: parameterPresetCombo
                                    anchors.fill: parent
                                    enabled: root.generationParameterPresets.length > 0
                                    model: root.parameterPresetOptions()
                                    textRole: "name"
                                    currentIndex: 0
                                    background: Rectangle {
                                        color: root.bgDark
                                        border.color: root.borderColor
                                        radius: 4
                                    }
                                    onActivated: function(index) {
                                        if (index <= 0) return
                                        root.applyParameterPreset(root.generationParameterPresets[index - 1])
                                    }
                                }

                                Timer {
                                    id: parameterPresetHoverTimer
                                    interval: 1000
                                    repeat: false
                                    onTriggered: {
                                        if (parameterPresetCombo.currentIndex > 0) {
                                            root.hoveredParameterPreset = root.generationParameterPresets[parameterPresetCombo.currentIndex - 1]
                                            root.parameterPresetPreviewVisible = root.hoveredParameterPreset !== null
                                        }
                                    }
                                }

                                MouseArea {
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    acceptedButtons: Qt.NoButton
                                    onEntered: {
                                        root.parameterPresetPreviewVisible = false
                                        parameterPresetHoverTimer.restart()
                                    }
                                    onExited: {
                                        parameterPresetHoverTimer.stop()
                                        root.parameterPresetPreviewVisible = false
                                    }
                                }
                            }
                        }
                    }
                }

                // 右栏：实时监控流
                Rectangle {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    color: root.panelBg
                    radius: 8
                    border.color: root.borderColor
                    ColumnLayout {
                        anchors.fill: parent; anchors.margins: 20; spacing: 15
                        Text { text: "👁 生成任务实时监控流"; color: root.textColor; font.bold: true; font.pixelSize: 16 }
                        Rectangle {
                            Layout.fillWidth: true; Layout.fillHeight: true; color: root.bgDark; radius: 6; border.color: root.borderColor; border.width: 1; clip: true
                            ColumnLayout {
                                anchors.centerIn: parent; spacing: 10; visible: previewModel.count === 0 && !root.isGenerating
                                Text { text: root.isCompleted ? "正在加载结果" : "等待任务执行"; color: root.textMuted; font.pixelSize: 14; font.family: "Courier"; font.bold: true; Layout.alignment: Qt.AlignHCenter }
                            }
                            ListView {
                                id: taskMonitorList
                                anchors.fill: parent; anchors.margins: 10; spacing: 8; model: previewModel; clip: true
                                delegate: Rectangle {
                                    width: taskMonitorList.width
                                    height: 68
                                    radius: 4
                                    color: genMa.containsMouse ? root.tableHoverBg : "transparent"
                                    border.color: genMa.containsMouse ? root.primaryColor : "transparent"
                                    border.width: 1
                                    MouseArea {
                                        id: genMa
                                        anchors.fill: parent
                                        hoverEnabled: true
                                        cursorShape: sourceSampleId > 0 ? Qt.PointingHandCursor : Qt.ArrowCursor
                                        onClicked: {
                                            if (sourceSampleId > 0) {
                                                root.openGenerationPreview(sourceSampleId, hasGenerated ? outputSampleId : 0, sourceName, generatedName, sourcePath, generatedPath)
                                            }
                                        }
                                    }
                                    RowLayout {
                                        anchors.fill: parent
                                        anchors.margins: 10
                                        spacing: 12

                                        Rectangle {
                                            Layout.preferredWidth: 50
                                            Layout.preferredHeight: 44
                                            Layout.alignment: Qt.AlignVCenter
                                            radius: 4
                                            color: root.panelBg
                                            border.color: root.borderColor
                                            clip: true
                                            Image {
                                                anchors.fill: parent
                                                anchors.margins: 2
                                                source: root.isImagePath(sourcePath) ? root.localFileUrl(sourcePath) : ""
                                                fillMode: Image.PreserveAspectCrop
                                                asynchronous: true
                                                visible: source !== ""
                                            }
                                            Text { anchors.centerIn: parent; text: "\u6e90"; color: root.textMuted; font.pixelSize: 12; visible: !root.isImagePath(sourcePath) }
                                        }

                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            Layout.alignment: Qt.AlignVCenter
                                            spacing: 2
                                            Text { text: "\u6e90\u6837\u672c"; color: root.textMuted; font.pixelSize: 10 }
                                            Text { text: sourceName || "-"; color: root.textColor; font.pixelSize: 12; font.family: "Courier"; elide: Text.ElideRight; Layout.fillWidth: true }
                                        }

                                        Text {
                                            text: hasGenerated ? "\u2192" : ""
                                            color: root.primaryColor
                                            font.pixelSize: 20
                                            font.bold: true
                                            Layout.alignment: Qt.AlignVCenter
                                        }

                                        Rectangle {
                                            Layout.preferredWidth: 50
                                            Layout.preferredHeight: 44
                                            Layout.alignment: Qt.AlignVCenter
                                            visible: hasGenerated
                                            radius: 4
                                            color: root.panelBg
                                            border.color: root.borderColor
                                            clip: true
                                            Image {
                                                anchors.fill: parent
                                                anchors.margins: 2
                                                source: root.isImagePath(generatedPath) ? root.localFileUrl(generatedPath) : ""
                                                fillMode: Image.PreserveAspectCrop
                                                asynchronous: true
                                                visible: source !== ""
                                            }
                                            Text { anchors.centerIn: parent; text: "\u751f\u6210"; color: root.textMuted; font.pixelSize: 11; visible: !root.isImagePath(generatedPath) }
                                        }

                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            Layout.alignment: Qt.AlignVCenter
                                            visible: hasGenerated
                                            spacing: 2
                                            Text { text: "\u751f\u6210\u6837\u672c"; color: root.successColor; font.pixelSize: 10; font.bold: true }
                                            Text { text: generatedName || "-"; color: root.textColor; font.pixelSize: 12; font.family: "Courier"; elide: Text.ElideRight; Layout.fillWidth: true }
                                        }
                                    }
                                }
                            }
                            Rectangle {
                                width: parent.width; height: 2; color: root.primaryColor; opacity: 0.8; visible: root.isGenerating
                                SequentialAnimation on y {
                                    running: root.isGenerating
                                    loops: Animation.Infinite
                                    NumberAnimation { from: 0; to: parent.height; duration: 1500 }
                                    NumberAnimation { from: parent.height; to: 0; duration: 0 }
                                }
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 46
                            Layout.maximumHeight: 46
                            spacing: 15
                            Rectangle {
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                radius: 6
                                color: root.isCompleted ? root.primaryColor : root.bgDark
                                border.color: root.isCompleted ? "transparent" : root.borderColor
                                border.width: 1
                                opacity: root.isCompleted ? 1.0 : 0.4
                                RowLayout {
                                    anchors.centerIn: parent; spacing: 10
                                    Text { text: "💾"; color: root.isCompleted ? "white" : root.textMuted; font.pixelSize: 16 }
                                    Text { text: "完成扩增并打包入库"; color: root.isCompleted ? "white" : root.textMuted; font.bold: true; font.pixelSize: 14 }
                                }
                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: root.isCompleted ? Qt.PointingHandCursor : Qt.ForbiddenCursor
                                    enabled: root.isCompleted
                                    onClicked: {
                                        saveDatasetNameInput.text = root.currentTargetDatasetName || (sourceDataCombo.currentText + "_扩增版")
                                        savePopup.open()
                                    }
                                }
                            }

                            Rectangle {
                                Layout.preferredWidth: 150
                                Layout.fillHeight: true
                                radius: 6
                                color: root.isCompleted ? Qt.rgba(245, 63, 63, 0.1) : root.bgDark
                                border.color: root.isCompleted ? root.dangerColor : root.borderColor
                                border.width: 1
                                opacity: root.isCompleted ? 1.0 : 0.4
                                RowLayout {
                                    anchors.centerIn: parent; spacing: 8
                                    Text { text: "✗"; color: root.isCompleted ? root.dangerColor : root.textMuted; font.bold: true; font.pixelSize: 14 }
                                    Text { text: "放弃生成"; color: root.isCompleted ? root.dangerColor : root.textMuted; font.bold: true; font.pixelSize: 14 }
                                }
                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: root.isCompleted ? Qt.PointingHandCursor : Qt.ForbiddenCursor
                                    enabled: root.isCompleted
                                    onClicked: {
                                        previewModel.clear()
                                        root.currentCount = 0
                                        root.isCompleted = false
                                        root.currentTaskId = 0
                                        root.currentTargetDatasetId = 0
                                        root.currentTargetDatasetName = ""
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        Rectangle {
            visible: root.parameterPresetPreviewVisible && root.hoveredParameterPreset !== null
            width: 300
            height: Math.min(260, 70 + parameterPresetPreviewColumn.implicitHeight)
            x: {
                if (!parameterPresetSelector) return newGenerationTaskPopup.width - width - 24
                var mapped = parameterPresetSelector.mapToItem(newGenerationTaskPopup.contentItem, parameterPresetSelector.width + 12, -8)
                return Math.min(mapped.x, newGenerationTaskPopup.width - width - 24)
            }
            y: {
                if (!parameterPresetSelector) return 120
                var mapped = parameterPresetSelector.mapToItem(newGenerationTaskPopup.contentItem, 0, -8)
                return Math.max(24, Math.min(mapped.y, newGenerationTaskPopup.height - height - 24))
            }
            z: 20
            radius: 6
            color: root.panelBg
            border.color: root.primaryColor
            border.width: 1
            clip: true

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 12
                spacing: 8

                Text {
                    text: root.hoveredParameterPreset ? (root.hoveredParameterPreset.name || "参数记录") : "参数记录"
                    color: root.primaryColor
                    font.bold: true
                    font.pixelSize: 13
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }
                Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: root.borderColor }
                Column {
                    id: parameterPresetPreviewColumn
                    Layout.fillWidth: true
                    spacing: 6
                    Repeater {
                        model: root.parameterPresetPreviewItems(root.hoveredParameterPreset)
                        delegate: RowLayout {
                            width: parameterPresetPreviewColumn.width
                            spacing: 10
                            Text {
                                text: modelData.label
                                color: root.textMuted
                                font.pixelSize: 11
                                elide: Text.ElideRight
                                Layout.preferredWidth: 120
                            }
                            Text {
                                text: modelData.value
                                color: root.textColor
                                font.pixelSize: 11
                                font.bold: true
                                elide: Text.ElideRight
                                Layout.fillWidth: true
                            }
                        }
                    }
                }
            }
        }
    }

    // ================= 视图A：生成历史列表 =================
    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 20
        spacing: 15
        visible: root.viewMode === "history"

        RowLayout {
            Layout.fillWidth: true
            spacing: 15
            Label { text: "增量样本生成历史"; font.pixelSize: 18; font.bold: true; color: root.textColor }
            Rectangle {
                Layout.preferredWidth: 360
                Layout.preferredHeight: 34
                color: root.panelBg
                radius: 4
                border.color: historySearchInput.activeFocus ? root.primaryColor : root.borderColor
                border.width: 1
                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 10
                    anchors.rightMargin: 8
                    spacing: 6
                    Text { text: "🔍"; color: root.textMuted; font.pixelSize: 13 }
                    TextInput {
                        id: historySearchInput
                        Layout.fillWidth: true
                        color: root.textColor
                        font.pixelSize: 13
                        selectByMouse: true
                        verticalAlignment: TextInput.AlignVCenter
                        clip: true
                        text: root.historySearchText
                        onTextChanged: {
                            root.historySearchText = text
                            root.applyGenerationHistoryFilter()
                        }
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            text: "按任务名或算法搜索"
                            color: root.textMuted
                            font.pixelSize: 12
                            visible: historySearchInput.text.length === 0 && !historySearchInput.activeFocus
                        }
                    }
                    Rectangle {
                        width: 18
                        height: 18
                        radius: 9
                        color: historySearchClearMa.containsMouse ? root.tableHoverBg : "transparent"
                        visible: root.historySearchText.length > 0
                        Text {
                            text: "×"
                            color: root.textMuted
                            font.pixelSize: 14
                            anchors.centerIn: parent
                        }
                        MouseArea {
                            id: historySearchClearMa
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: historySearchInput.text = ""
                        }
                    }
                }
            }
            Item { Layout.fillWidth: true }

            Button {
                text: root.selectedExportCount > 0 ? "📥 导出选中项 (" + root.selectedExportCount + ")" : "📥 导出选中项"
                font.bold: true; font.pixelSize: 14
                enabled: root.selectedExportCount > 0
                background: Rectangle {
                    color: root.selectedExportCount > 0 ? root.successColor : root.bgDark
                    border.color: root.selectedExportCount > 0 ? "transparent" : root.borderColor
                    border.width: 1; radius: 4
                }
                contentItem: Text { text: parent.text; color: root.selectedExportCount > 0 ? "white" : root.textMuted; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                onClicked: exportPopup.open()
            }

            Button {
                text: "+ 新建生成任务"
                font.bold: true; font.pixelSize: 14
                background: Rectangle { color: parent.pressed ? "#0277BD" : parent.hovered ? "#0288D1" : "#039BE5"; radius: 4 }
                contentItem: Text { text: parent.text; color: "black"; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                onClicked: {
                    root.selectedStrategies = []
                    previewModel.clear()
                    root.currentCount = 0
                    root.isCompleted = false
                    root.currentTaskId = 0
                    root.currentTargetDatasetId = 0
                    root.currentTargetDatasetName = ""
                    backendService.getDatasets(1, 100, "")
                    newGenerationTaskPopup.open()
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: "transparent"
            clip: true

            ListView {
                id: historyListView
                anchors.fill: parent
                clip: true
                spacing: 12
                model: generationHistoryModel

                delegate: Rectangle {
                    id: cardItem
                    width: historyListView.width
                    height: 185
                    radius: 8
                    color: Theme.panel
                    border.color: model.isSelected ? root.primaryColor : (cardMa.containsMouse ? Theme.primary : root.borderColor)
                    border.width: 1

                    MouseArea {
                        id: cardMa
                        anchors.fill: parent
                        hoverEnabled: true
                        onClicked: {
                            model.isSelected = !model.isSelected
                            root.updateExportCount()
                        }
                    }

                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 15
                        spacing: 20

                        Rectangle {
                            width: 22; height: 22; radius: 4
                            color: model.isSelected ? root.primaryColor : root.bgDark
                            border.color: model.isSelected ? root.primaryColor : root.textMuted
                            Text { text: "✓"; color: "white"; font.pixelSize: 14; font.bold: true; anchors.centerIn: parent; visible: model.isSelected }
                        }

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 6

                            RowLayout {
                                Layout.fillWidth: true; spacing: 8
                                Label {
                                    text: "🚀 " + (model.projectName || "生成任务#" + (model.taskId || "?"))
                                    color: root.primaryColor; font.pixelSize: 16; font.bold: true; elide: Text.ElideRight
                                    Layout.maximumWidth: 350
                                }
                                Item { Layout.fillWidth: true }
                                Label { text: "🕒 " + (model.time || ""); color: root.textMuted; font.pixelSize: 12 }
                            }

                            RowLayout {
                                Layout.fillWidth: true; spacing: 10
                                Label { text: "源数据集: "; color: root.textMuted; font.pixelSize: 13 }
                                Label { text: model.sourceDataset || "-"; color: root.textColor; font.pixelSize: 13; Layout.maximumWidth: 200; elide: Text.ElideRight }
                                Rectangle { width: 1; height: 12; color: root.borderColor }
                                Label { text: "状态: "; color: root.textMuted; font.pixelSize: 13 }
                                Label {
                                    text: {
                                        var s = model.status || ""
                                        if (s === "completed") return "✅ 已完成"
                                        if (s === "running") return "⏳ 运行中 (" + (model.progress || 0) + "%)"
                                        if (s === "failed") return "❌ 失败"
                                        if (s === "pending") return "📋 等待中"
                                        if (s === "cancelled") return "⏹ 已取消"
                                        return s
                                    }
                                    color: model.status === "completed" ? root.successColor : (model.status === "failed" ? root.dangerColor : root.textColor)
                                    font.pixelSize: 13
                                }
                            }

                            Rectangle {
                                id: runningGenerationProgress
                                Layout.fillWidth: true
                                Layout.preferredHeight: 6
                                visible: model.status === "running"
                                color: root.bgDark
                                radius: 3
                                Rectangle {
                                    height: parent.height
                                    width: parent.width * Math.max(0, Math.min(1, (model.progress || 0) / 100.0))
                                    color: root.primaryColor
                                    radius: 3
                                    Behavior on width { NumberAnimation { duration: 120 } }
                                }
                            }

                            RowLayout {
                                Layout.fillWidth: true
                                Label { text: "使用算法: "; color: root.textMuted; font.pixelSize: 13 }
                                Flickable {
                                    id: historyAlgoFlick
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 18
                                    contentWidth: historyAlgoText.implicitWidth
                                    contentHeight: height
                                    clip: true
                                    boundsBehavior: Flickable.StopAtBounds
                                    flickableDirection: Flickable.HorizontalFlick

                                    Text {
                                        id: historyAlgoText
                                        text: model.algos || "未知"
                                        color: root.textColor
                                        font.pixelSize: 13
                                        font.bold: true
                                        anchors.verticalCenter: parent.verticalCenter
                                    }

                                    MouseArea {
                                        anchors.fill: parent
                                        acceptedButtons: Qt.NoButton
                                        onWheel: function(wheel) {
                                            var delta = wheel.pixelDelta.y !== 0 ? wheel.pixelDelta.y : wheel.angleDelta.y
                                            if (delta === 0) delta = wheel.pixelDelta.x !== 0 ? -wheel.pixelDelta.x : -wheel.angleDelta.x
                                            var maxX = Math.max(0, historyAlgoFlick.contentWidth - historyAlgoFlick.width)
                                            historyAlgoFlick.contentX = Math.max(0, Math.min(maxX, historyAlgoFlick.contentX - delta))
                                            wheel.accepted = maxX > 0
                                        }
                                    }

                                    onContentWidthChanged: {
                                        var maxX = Math.max(0, contentWidth - width)
                                        contentX = Math.min(contentX, maxX)
                                    }
                                    onWidthChanged: {
                                        var maxX = Math.max(0, contentWidth - width)
                                        contentX = Math.min(contentX, maxX)
                                    }
                                }
                            }

                            RowLayout {
                                Layout.fillWidth: true
                                Label { text: "目标数量: "; color: root.textMuted; font.pixelSize: 13 }
                                Label { text: model.targetCount || "-"; color: root.successColor; font.bold: true; font.family: "Courier"; font.pixelSize: 13 }
                            }

                            RowLayout {
                                Layout.fillWidth: true
                                Label { text: "生成数据集: "; color: root.textMuted; font.pixelSize: 13 }
                                Label { text: model.generatedDataset || "(系统自动创建)"; color: root.textColor; font.pixelSize: 13; Layout.fillWidth: true; elide: Text.ElideRight }
                            }

                            RowLayout {
                                Layout.fillWidth: true
                                Label { text: "存储路径: " + (model.path || "(系统自动管理)"); color: root.textMuted; font.pixelSize: 12; font.family: "Courier"; elide: Text.ElideRight; Layout.fillWidth: true }
                            }
                        }

                        ColumnLayout {
                            Layout.alignment: Qt.AlignVCenter | Qt.AlignRight
                            spacing: 10

                            Button {
                                text: "查看详情"
                                Layout.preferredWidth: 90; Layout.preferredHeight: 30
                                background: Rectangle { color: parent.hovered ? Theme.hover : Theme.control; radius: 4; border.color: Theme.border }
                                contentItem: Text { text: parent.text; color: "#D1D5DB"; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                                onClicked: {
                                    var detailIds = root.parseAlgorithmIds(model.algorithmIdsText || model.algorithmIds || "")
                                    var detailParams = root.parseJsonObject(model.parametersJsonText || model.parameters || {})
                                    root.currentHistoryItem = {
                                        taskId: model.taskId || 0,
                                        projectName: model.projectName,
                                        sourceDataset: model.sourceDataset,
                                        generatedDataset: model.generatedDataset,
                                        algos: model.algos,
                                        algorithmIds: detailIds,
                                        parameters: detailParams,
                                        targetCount: model.targetCount || 0,
                                        time: model.time
                                    }
                                    root.detailAlgorithmIds = detailIds
                                    var algoItems = []
                                    for (var ai = 0; ai < root.detailAlgorithmIds.length; ai++) {
                                        var aid = root.detailAlgorithmIds[ai]
                                        algoItems.push({
                                            aid: aid,
                                            aname: root.algorithmNameMap[String(aid)] || ("算法#" + aid)
                                        })
                                    }
                                    root.detailAlgorithmItems = algoItems
                                    root.detailParameters = detailParams
                                    root.hasDetailCustomParams = root.computeHasDetailParams(root.detailParameters)
                                    if (model.taskId && model.taskId > 0) {
                                        backendService.getGenerationOutputs(model.taskId, "", 1, 200)
                                    }
                                    root.viewMode = "fileDetail"
                                }
                            }

                            Button {
                                text: "修改名称"
                                Layout.preferredWidth: 90; Layout.preferredHeight: 30
                                background: Rectangle { color: parent.hovered ? Theme.hover : Theme.control; radius: 4; border.color: Theme.border }
                                contentItem: Text { text: parent.text; color: "#D1D5DB"; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                                onClicked: {
                                    root.pendingEditIndex = index
                                    editProjectNameInput.text = model.projectName
                                    editProjectPopup.open()
                                }
                            }

                            Button {
                                text: "删除"
                                Layout.preferredWidth: 90; Layout.preferredHeight: 30
                                background: Rectangle { color: parent.hovered ? "#BE123C" : "transparent"; border.color: root.dangerColor; border.width: 1; radius: 4 }
                                contentItem: Text { text: parent.text; color: parent.hovered ? "white" : root.dangerColor; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                                onClicked: {
                                    root.pendingDeleteIndex = index
                                    deleteConfirmPopup.open()
                                }
                            }
                        }
                    }
                }

                Text {
                    anchors.centerIn: parent
                    text: root.historySearchText.trim().length > 0 ? "没有匹配的生成任务" : "暂无样本生成记录"
                    color: Theme.muted
                    font.pixelSize: 16
                    visible: generationHistoryModel.count === 0
                }
            }
        }
    }

    // ================= 视图B：任务详情 =================
    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 20
        spacing: 15
        visible: root.viewMode === "fileDetail"

        RowLayout {
            Layout.fillWidth: true
            spacing: 15

            Button {
                text: "⬅ 返回历史"
                font.bold: true; font.pixelSize: 14
                background: Rectangle { color: "transparent"; border.color: Theme.border; border.width: 1; radius: 4 }
                contentItem: Text { text: parent.text; color: "#4DD0E1"; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                onClicked: {
                    root.viewMode = "history"
                    backendService.getEnhancementTasks(0, "")
                }
            }

            Label {
                text: root.currentHistoryItem ? "📂 " + (root.currentHistoryItem.projectName || ("#" + root.currentHistoryItem.taskId)) : ""
                font.pixelSize: 16; font.bold: true; color: root.primaryColor
            }

            Item { Layout.fillWidth: true }

            Label {
                text: "共 " + previewModel.count + " 条生成记录"
                color: Theme.muted; font.pixelSize: 13
            }

            Button {
                text: "▶ 刷新数据"
                font.bold: true; font.pixelSize: 14
                background: Rectangle { color: root.primaryColor; radius: 4 }
                contentItem: Text { text: parent.text; color: "black"; font.bold: true; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                onClicked: {
                    if (root.currentHistoryItem && root.currentHistoryItem.taskId > 0) {
                        backendService.getGenerationOutputs(root.currentHistoryItem.taskId, "", 1, 200)
                    }
                }
            }
        }

        // 详情布局：左侧为生成算法与参数，右侧为生成结果。
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 15

            // 左栏：已使用的算法
            Rectangle {
                Layout.preferredWidth: 260
                Layout.fillHeight: true
                color: root.panelBg
                radius: 8
                border.color: root.borderColor
                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 15
                    spacing: 12
                    Text { text: "📂 已使用算法"; color: root.textColor; font.bold: true; font.pixelSize: 15 }
                    Text {
                        visible: root.detailAlgorithmItems.length === 0
                        text: "未记录算法信息"
                        color: root.textMuted; font.pixelSize: 12
                    }
                    ScrollView {
                        Layout.fillWidth: true; Layout.preferredHeight: 180; clip: true
                        visible: root.detailAlgorithmItems.length > 0
                        Column {
                            id: algoColumn
                            width: parent.width; spacing: 6
                            Repeater {
                                model: root.detailAlgorithmItems
                                delegate: Rectangle {
                                    width: algoColumn.width; height: 42; radius: 4; color: root.tableHoverBg
                                    Text {
                                        text: "🔹 " + (modelData.aname || ("算法#" + modelData.aid))
                                        color: root.primaryColor; font.bold: true; font.pixelSize: 13
                                        anchors.verticalCenter: parent.verticalCenter; anchors.left: parent.left; anchors.leftMargin: 12
                                    }
                                }
                            }
                        }
                    }

                    Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: root.borderColor }
                    Text { text: "配置参数"; color: root.textColor; font.bold: true; font.pixelSize: 14 }
                    Text {
                        visible: !root.hasDetailCustomParams
                        text: "无额外配置参数"
                        color: root.textMuted; font.pixelSize: 12
                    }
                    ScrollView {
                        Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                        visible: root.hasDetailCustomParams
                        Column {
                            id: detailParamColumn
                            width: parent.width; spacing: 8
                            Repeater {
                                model: root.detailParameterItems(root.detailParameters)
                                delegate: Column {
                                    width: detailParamColumn.width; spacing: 4
                                    Text { text: modelData.k; color: root.textMuted; font.pixelSize: 11; elide: Text.ElideRight; width: parent.width }
                                    Rectangle {
                                        width: parent.width; height: 28; color: root.bgDark; radius: 4; border.color: root.borderColor; border.width: 1
                                        Text {
                                            text: String(modelData.v)
                                            color: root.textColor; font.pixelSize: 12
                                            anchors.verticalCenter: parent.verticalCenter; anchors.left: parent.left; anchors.right: parent.right
                                            anchors.leftMargin: 8; anchors.rightMargin: 8
                                            elide: Text.ElideRight
                                        }
                                    }
                                }
                            }
                        }
                    }
                    Button {
                        id: recordParameterButton
                        text: "记录参数"
                        enabled: root.hasDetailCustomParams
                        Layout.preferredWidth: 92
                        Layout.preferredHeight: 32
                        Layout.alignment: Qt.AlignLeft
                        background: Rectangle {
                            color: recordParameterButton.enabled ? (recordParameterButton.hovered ? "#0288D1" : root.primaryColor) : Theme.border
                            radius: 4
                        }
                        contentItem: Text {
                            text: recordParameterButton.text
                            color: recordParameterButton.enabled ? "black" : root.textMuted
                            font.bold: recordParameterButton.enabled
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                        }
                        onClicked: {
                            if (!root.hasDetailCustomParams) return
                            var title = root.currentHistoryItem && root.currentHistoryItem.projectName ? root.currentHistoryItem.projectName : "生成参数"
                            parameterPresetNameInput.text = title + " 参数"
                            parameterPresetNameInput.forceActiveFocus()
                            parameterPresetNamePopup.open()
                        }
                    }
                }
            }

            // 右栏：生成结果
            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                color: root.panelBg
                radius: 8
                border.color: root.borderColor
                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 20
                    spacing: 15
                    Text { text: "生成结果详情"; color: root.textColor; font.bold: true; font.pixelSize: 16 }
                    Rectangle {
                        Layout.fillWidth: true; Layout.fillHeight: true
                        color: root.bgDark; radius: 6; border.color: root.borderColor; border.width: 1; clip: true
                        ColumnLayout {
                            anchors.centerIn: parent; spacing: 10
                            visible: previewModel.count === 0
                            Text { text: "正在加载结果"; color: root.textMuted; font.pixelSize: 14; font.family: "Courier"; font.bold: true; Layout.alignment: Qt.AlignHCenter }
                        }
                        ListView {
                            id: detailFileListView
                            anchors.fill: parent
                            anchors.leftMargin: 10
                            anchors.topMargin: 10
                            anchors.rightMargin: 18
                            anchors.bottomMargin: 10
                            spacing: 8
                            model: previewModel
                            clip: true
                            ScrollBar.vertical: ScrollBar {
                                parent: detailFileListView.parent
                                anchors.top: detailFileListView.top
                                anchors.bottom: detailFileListView.bottom
                                anchors.right: parent.right
                                anchors.rightMargin: 4
                                policy: ScrollBar.AlwaysOn
                                active: true
                            }
                            delegate: Rectangle {
                                width: detailFileListView.width
                                height: 76
                                radius: 4
                                color: detailMa.containsMouse ? root.tableHoverBg : "transparent"
                                border.color: detailMa.containsMouse ? root.primaryColor : "transparent"
                                border.width: 1
                                MouseArea {
                                    id: detailMa
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: sourceSampleId > 0 ? Qt.PointingHandCursor : Qt.ArrowCursor
                                    onClicked: {
                                        if (sourceSampleId > 0) {
                                            root.openGenerationPreview(sourceSampleId, hasGenerated ? outputSampleId : 0, sourceName, generatedName, sourcePath, generatedPath)
                                        }
                                    }
                                }
                                RowLayout {
                                    anchors.fill: parent
                                    anchors.margins: 10
                                    spacing: 14

                                    Rectangle {
                                        Layout.preferredWidth: 58
                                        Layout.preferredHeight: 48
                                        Layout.alignment: Qt.AlignVCenter
                                        radius: 4
                                        color: root.panelBg
                                        border.color: root.borderColor
                                        clip: true
                                        Image {
                                            anchors.fill: parent
                                            anchors.margins: 2
                                            source: root.isImagePath(sourcePath) ? root.localFileUrl(sourcePath) : ""
                                            fillMode: Image.PreserveAspectCrop
                                            asynchronous: true
                                            visible: source !== ""
                                        }
                                        Text { anchors.centerIn: parent; text: "\u6e90"; color: root.textMuted; font.pixelSize: 12; visible: !root.isImagePath(sourcePath) }
                                    }

                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        Layout.alignment: Qt.AlignVCenter
                                        spacing: 2
                                        Text { text: "\u6e90\u6837\u672c"; color: root.textMuted; font.pixelSize: 10 }
                                        Text { text: sourceName || "-"; color: root.textColor; font.pixelSize: 12; font.family: "Courier"; elide: Text.ElideRight; Layout.fillWidth: true }
                                    }

                                    Text {
                                        text: hasGenerated ? "\u2192" : ""
                                        color: root.primaryColor
                                        font.pixelSize: 20
                                        font.bold: true
                                        Layout.alignment: Qt.AlignVCenter
                                    }

                                    Rectangle {
                                        Layout.preferredWidth: 58
                                        Layout.preferredHeight: 48
                                        Layout.alignment: Qt.AlignVCenter
                                        visible: hasGenerated
                                        radius: 4
                                        color: root.panelBg
                                        border.color: root.borderColor
                                        clip: true
                                        Image {
                                            anchors.fill: parent
                                            anchors.margins: 2
                                            source: root.isImagePath(generatedPath) ? root.localFileUrl(generatedPath) : ""
                                            fillMode: Image.PreserveAspectCrop
                                            asynchronous: true
                                            visible: source !== ""
                                        }
                                        Text { anchors.centerIn: parent; text: "\u751f\u6210"; color: root.textMuted; font.pixelSize: 11; visible: !root.isImagePath(generatedPath) }
                                    }

                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        Layout.alignment: Qt.AlignVCenter
                                        visible: hasGenerated
                                        spacing: 2
                                        Text { text: "\u751f\u6210\u6837\u672c"; color: root.successColor; font.pixelSize: 10; font.bold: true }
                                        Text { text: generatedName || "-"; color: root.textColor; font.pixelSize: 12; font.family: "Courier"; elide: Text.ElideRight; Layout.fillWidth: true }
                                    }

                                    ColumnLayout {
                                        Layout.preferredWidth: 118
                                        Layout.alignment: Qt.AlignVCenter
                                        spacing: 2
                                        Text { text: "\u751f\u6210\u7b97\u6cd5"; color: root.textMuted; font.pixelSize: 10 }
                                        Text { text: hasGenerated && algoId > 0 ? (root.algorithmNameMap[String(algoId)] || ("\u7b97\u6cd5#" + algoId)) : "\u6e90\u6837\u672c\u4fdd\u7559"; color: hasGenerated ? root.primaryColor : root.textMuted; font.pixelSize: 12; font.bold: hasGenerated; elide: Text.ElideRight; Layout.fillWidth: true }
                                    }

                                    Rectangle {
                                        Layout.preferredWidth: 72
                                        Layout.preferredHeight: 26
                                        Layout.alignment: Qt.AlignVCenter
                                        radius: 4
                                        color: hasGenerated ? "#1E3A5F" : root.bgDark
                                        Text {
                                            text: hasGenerated ? "\u5df2\u751f\u6210" : "\u4ec5\u6e90\u6837\u672c"
                                            color: hasGenerated ? "#60A5FA" : root.textMuted
                                            font.pixelSize: 11
                                            font.bold: true
                                            anchors.centerIn: parent
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
