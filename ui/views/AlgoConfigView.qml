import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import QtQuick.Pdf
import ".."

Item {
    id: root
    anchors.fill: parent

    // ==========================================
    // 鍏ㄥ眬绠€娲佷富棰樿鑼?
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
        title: "绠楁硶閰嶇疆甯姪"
        body: "鏈〉鐢ㄤ簬鏌ョ湅銆佹敞鍐屻€佷慨鏀瑰拰鍗歌浇绠楁硶鎻掍欢锛屾槸鐢熸垚銆佹竻娲椼€佽缁冨拰璇勪及绠楁硶鐨勭粺涓€閰嶇疆鍏ュ彛銆俓n\n1. 宸︿晶鎸夌畻娉曞ぇ绫诲拰鏁版嵁妯℃€佸垎缁勫睍绀烘彃浠讹紝鍙€氳繃椤堕儴涓嬫媺妗嗙瓫閫夊叏閮ㄣ€佹竻娲椼€佺敓鎴愩€佽瘎浼版垨璁粌绠楁硶锛涚偣鍑诲垎缁勫彲灞曞紑鎴栨姌鍙犮€俓n2. 鐐瑰嚮鏌愪釜绠楁硶鍚庯紝鍙充晶浼氭樉绀虹畻娉曞悕绉般€佹墍灞炵被鍒€佽剼鏈垨妯″潡鎸傝浇璺緞銆佹帴鍙ｇ畝杩般€佷娇鐢ㄨ鏄庡拰鍙傛暟蹇収銆俓n3. 鈥滄彃浠惰鑼冣€濇寜閽細寮瑰嚭鏈」鐩殑绠楁硶鎻掍欢寮€鍙戣鑼冪獥鍙ｏ紝鍙笅鎷夋煡鐪?run(payload, context) 鍏ュ彛銆丳ARAMETERS 鍙傛暟澹版槑鍜岃緭鍑烘牸寮忋€俓n4. 鈥滄敞鍐屾柊鎻掍欢鐜鈥濈敤浜庢帴鍏ユ柊鐨?Python 鎻掍欢銆傞€夋嫨鑴氭湰鍚庣郴缁熶細鑷姩鍙嶅皠 PARAMETERS锛岀敓鎴愬弬鏁伴厤缃〃锛涘～鍐欏悕绉般€佺被鍒€佹ā鎬佸拰璇存槑鍚庣‘璁ゆ敞鍐屻€俓n5. 鈥滆皟鍙備慨鏀光€濈敤浜庝慨鏀瑰凡鏈夌畻娉曠殑鍙傛暟瀹氫箟銆佸悕绉般€佺被鍒€佹ā鎬併€佽剼鏈矾寰勬垨妯″潡璺緞銆傚唴缃ā鍧楃畻娉曚細淇濈暀 module_path锛岃剼鏈彃浠朵細澶嶅埗骞朵繚瀛?script_path銆俓n6. 鍙傛暟琛ㄦ敮鎸佹柊澧炪€佸垹闄ゅ拰缂栬緫鍙傛暟鍚嶃€佹樉绀烘爣绛俱€佺被鍨嬨€侀粯璁ゅ€笺€佹暟鍊艰寖鍥村拰涓嬫媺閫夐」銆備繚瀛樺悗锛屾暟鎹敓鎴?娓呮礂/璇勪及椤甸潰浼氭寜杩欎簺鍙傛暟娓叉煋鍔ㄦ€侀厤缃帶浠躲€俓n7. 鈥滃嵏杞界幆澧冣€濅細鍒犻櫎绠楁硶娉ㄥ唽璁板綍銆傚垹闄ゅ墠璇风‘璁ゆ病鏈夋鍦ㄨ繍琛岀殑浠诲姟渚濊禆璇ョ畻娉曘€俓n8. 璋冩暣瀹屾垚鍚庡缓璁洖鍒板搴斾笟鍔￠〉闈㈠埛鏂扮畻娉曞垪琛紝纭鏂板弬鏁板拰鏂版彃浠跺凡缁忕敓鏁堛€?
    }

    // 鐘舵€佹帶鍒?
    property int pendingEditIndex: -1
    property int pendingDeleteIndex: -1

    // 鍒嗙被鎶樺彔闈㈡澘鐘舵€?
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
    property string algoCategoryFilter: "鍏ㄩ儴绠楁硶"
    property string pluginSpecText: "<html><body style='font-family:Segoe UI,Microsoft YaHei,sans-serif;font-size:14px;color:" + root.textColor + ";background:transparent;padding:24px 30px;line-height:1.7'>" +
        "<h1 style='font-size:22px;color:" + root.primaryColor + ";margin:0 0 4px 0;font-weight:700'>ISG 绠楁硶鎻掍欢寮€鍙戣鑼?/h1>" +
        "<p style='color:" + root.textMuted + ";margin:0 0 28px 0;font-size:13px'>Version 1.0 路 Python 鎻掍欢鏍囧噯鎺ュ彛</p>" +

        "<h2 style='font-size:15px;color:" + root.primaryColor + ";margin:24px 0 8px 0'>姒傝堪</h2>" +
        "<p style='margin:0 0 12px 0'>ISG 绠楁硶鎻掍欢鏄爣鍑?Python <code style='background:" + root.tableHoverBg + ";padding:1px 6px;border-radius:3px'>.py</code> 鏂囦欢锛屽疄鐜?<code style='background:" + root.tableHoverBg + ";padding:1px 6px;border-radius:3px'>run(payload, context)</code> 鍏ュ彛鍑芥暟锛屽０鏄庢ā鍧楃骇 <code style='background:" + root.tableHoverBg + ";padding:1px 6px;border-radius:3px'>PARAMETERS</code> 鍒楄〃銆?/p>" +

        "<h2 style='font-size:15px;color:" + root.primaryColor + ";margin:24px 0 8px 0'>鏂囦欢缁撴瀯</h2>" +
        "<pre style='background:" + root.panelBg + ";color:" + root.textColor + ";border:1px solid " + root.borderColor + ";border-radius:6px;padding:14px 16px;font-family:Consolas,Courier New,monospace;font-size:12.5px;line-height:1.55;margin:0'># -*- coding: utf-8 -*-\n\"\"\"鎻掍欢绠€瑕佽鏄庛€俓"\"\"\nfrom pathlib import Path\n\nPARAMETERS: list[dict[str, Any]] = [\n    {\n        \"name\": \"threshold\",\n        \"type\": \"float\",\n        \"label\": \"闃堝€糪",\n        \"default\": 0.5,\n        \"min\": 0.0, \"max\": 1.0,\n        \"options\": [],\n        \"description\": \"鍒ゅ畾闃堝€糪",\n        \"required\": False,\n    },\n]\n\ndef run(payload: dict[str, Any], context: Any) -> dict[str, Any]:\n    \"\"\"绠楁硶鍏ュ彛銆俻ayload: parameters/input/output\n    鎴愬姛: {\"ok\": True, \"outputs\": [...]}\n    澶辫触: {\"ok\": False, \"error_code\": \"...\", \"message\": \"...\"}\"\"\"\n    ...</pre>" +

        "<h2 style='font-size:15px;color:" + root.primaryColor + ";margin:24px 0 8px 0'>PARAMETERS 瀛楁</h2>" +
        "<table style='border-collapse:collapse;width:100%;font-size:13px'>" +
        "<tr style='border-bottom:2px solid " + root.primaryColor + "'><td style='padding:7px 10px;font-weight:700'>瀛楁</td><td style='padding:7px 10px;font-weight:700'>绫诲瀷</td><td style='padding:7px 10px;font-weight:700'>蹇呭～</td><td style='padding:7px 10px;font-weight:700'>璇存槑</td></tr>" +
        "<tr style='border-bottom:1px solid " + root.borderColor + "'><td style='padding:6px 10px'><code>name</code></td><td style='padding:6px 10px'>str</td><td style='padding:6px 10px'>鏄?/td><td style='padding:6px 10px'>鑻辨枃灏忓啓+涓嬪垝绾?/td></tr>" +
        "<tr style='border-bottom:1px solid " + root.borderColor + "'><td style='padding:6px 10px'><code>type</code></td><td style='padding:6px 10px'>str</td><td style='padding:6px 10px'>鏄?/td><td style='padding:6px 10px'>string / int / float / bool / select</td></tr>" +
        "<tr style='border-bottom:1px solid " + root.borderColor + "'><td style='padding:6px 10px'><code>label</code></td><td style='padding:6px 10px'>str</td><td style='padding:6px 10px'>鏄?/td><td style='padding:6px 10px'>UI 涓枃鍚?/td></tr>" +
        "<tr style='border-bottom:1px solid " + root.borderColor + "'><td style='padding:6px 10px'><code>default</code></td><td style='padding:6px 10px'>*</td><td style='padding:6px 10px'>鏄?/td><td style='padding:6px 10px'>榛樿鍊?/td></tr>" +
        "<tr style='border-bottom:1px solid " + root.borderColor + "'><td style='padding:6px 10px'><code>min / max</code></td><td style='padding:6px 10px'>float</td><td style='padding:6px 10px'>鍚?/td><td style='padding:6px 10px'>鏁板€艰寖鍥?/td></tr>" +
        "<tr style='border-bottom:1px solid " + root.borderColor + "'><td style='padding:6px 10px'><code>options</code></td><td style='padding:6px 10px'>list</td><td style='padding:6px 10px'>鍚?/td><td style='padding:6px 10px'>select 鐨勫€欓€夐」</td></tr>" +
        "<tr style='border-bottom:1px solid " + root.borderColor + "'><td style='padding:6px 10px'><code>description</code></td><td style='padding:6px 10px'>str</td><td style='padding:6px 10px'>鍚?/td><td style='padding:6px 10px'>璇存槑鏂囨湰</td></tr>" +
        "<tr><td style='padding:6px 10px'><code>required</code></td><td style='padding:6px 10px'>bool</td><td style='padding:6px 10px'>鍚?/td><td style='padding:6px 10px'>榛樿 false</td></tr>" +
        "</table>" +

        "<h2 style='font-size:15px;color:" + root.primaryColor + ";margin:24px 0 8px 0'>绫诲瀷绾﹀畾</h2>" +
        "<table style='border-collapse:collapse;width:100%;font-size:13px'>" +
        "<tr style='border-bottom:2px solid " + root.primaryColor + "'><td style='padding:7px 10px;font-weight:700'>type</td><td style='padding:7px 10px;font-weight:700'>绀轰緥</td><td style='padding:7px 10px;font-weight:700'>璇存槑</td></tr>" +
        "<tr style='border-bottom:1px solid " + root.borderColor + "'><td style='padding:5px 10px'>string</td><td style='padding:5px 10px'><code>\"normal\"</code></td><td style='padding:5px 10px'>瀛楃涓?/td></tr>" +
        "<tr style='border-bottom:1px solid " + root.borderColor + "'><td style='padding:5px 10px'>int</td><td style='padding:5px 10px'><code>100</code></td><td style='padding:5px 10px'>鏁存暟</td></tr>" +
        "<tr style='border-bottom:1px solid " + root.borderColor + "'><td style='padding:5px 10px'>float</td><td style='padding:5px 10px'><code>0.5</code></td><td style='padding:5px 10px'>娴偣</td></tr>" +
        "<tr style='border-bottom:1px solid " + root.borderColor + "'><td style='padding:5px 10px'>bool</td><td style='padding:5px 10px'><code>True / False</code></td><td style='padding:5px 10px'>甯冨皵</td></tr>" +
        "<tr><td style='padding:5px 10px'>select</td><td style='padding:5px 10px'><code>\"A\"</code></td><td style='padding:5px 10px'>鏋氫妇锛宱ptions 蹇呭～</td></tr>" +
        "</table>" +

        "<h2 style='font-size:15px;color:" + root.primaryColor + ";margin:24px 0 8px 0'>run() 鍑芥暟</h2>" +
        "<p style='margin:0'>绛惧悕: <code style='background:" + root.tableHoverBg + ";padding:1px 6px;border-radius:3px'>def run(payload: dict, context: Any) -> dict</code></p>" +

        "<p style='font-weight:600;margin:14px 0 4px 0'>payload 缁撴瀯</p>" +
        "<pre style='background:" + root.panelBg + ";color:" + root.textColor + ";border:1px solid " + root.borderColor + ";border-radius:6px;padding:12px 16px;font-family:Consolas,Courier New,monospace;font-size:12.5px;line-height:1.55;margin:0'>{\n  \"algorithm_key\": \"generation.image.geometric_transform\",\n  \"parameters\": { \"rotation_degrees\": 10.0 },\n  \"input\": {\n    \"dataset_id\": 1,\n    \"dataset_path\": \"/data/datasets/abc\",\n    \"samples\": [{ \"id\": 1, \"path\": \"...\", \"labels\": [...] }]\n  },\n  \"output\": { \"output_dir\": \"/data/tasks/42/output\" },\n  \"target_count\": 100\n}</pre>" +

        "<p style='font-weight:600;margin:14px 0 4px 0'>context 鏂规硶</p>" +
        "<table style='border-collapse:collapse;width:100%;font-size:13px'>" +
        "<tr style='border-bottom:2px solid " + root.primaryColor + "'><td style='padding:7px 10px;font-weight:700'>鏂规硶</td><td style='padding:7px 10px;font-weight:700'>璇存槑</td></tr>" +
        "<tr style='border-bottom:1px solid " + root.borderColor + "'><td style='padding:5px 10px;font-family:Consolas,monospace'>set_progress(percent, msg)</td><td style='padding:5px 10px'>鏇存柊杩涘害 0鈥?00</td></tr>" +
        "<tr style='border-bottom:1px solid " + root.borderColor + "'><td style='padding:5px 10px;font-family:Consolas,monospace'>log(level, msg, payload)</td><td style='padding:5px 10px'>璁板綍鏃ュ織 info/warn/error</td></tr>" +
        "<tr><td style='padding:5px 10px;font-family:Consolas,monospace'>is_cancel_requested() -> bool</td><td style='padding:5px 10px'>妫€鏌ュ彇娑堬紝鍛ㄦ湡鎬ц皟鐢?/td></tr>" +
        "</table>" +

        "<p style='font-weight:600;margin:14px 0 4px 0'>杩斿洖鍊?/p>" +
        "<pre style='background:" + root.panelBg + ";color:" + root.textColor + ";border:1px solid " + root.borderColor + ";border-radius:6px;padding:12px 16px;font-family:Consolas,Courier New,monospace;font-size:12.5px;line-height:1.55;margin:0'>鎴愬姛(鐢熸垚): {\"ok\": True, \"outputs\": [{...}], \"logs\": []}\n鎴愬姛(娓呮礂): {\"ok\": True, \"suggestions\": [{...}], \"logs\": []}\n澶辫触:      {\"ok\": False, \"error_code\": \"...\", \"message\": \"...\"}\n鍙栨秷:      {\"ok\": False, \"error_code\": \"CANCELLED\", \"message\": \"...\"}</pre>" +

        "<h2 style='font-size:15px;color:" + root.primaryColor + ";margin:24px 0 8px 0'>鍛藉悕绾﹀畾</h2>" +
        "<p style='margin:0 0 2px 0'>路 鍙傛暟 name: 鑻辨枃灏忓啓+涓嬪垝绾?<code>blur_threshold</code></p>" +
        "<p style='margin:0 0 2px 0'>路 鍙傛暟 label: 绠€鐭腑鏂囥€屾ā绯婇槇鍊笺€?/p>" +
        "<p style='margin:0 0 2px 0'>路 绠楁硶 key: <code>.</code> 鍒嗛殧 <code>generation.image.geo</code></p>" +
        "<p style='margin:0'>路 绠楁硶 name: UI 涓枃鍚嶃€屽嚑浣曞彉鎹€?/p>" +

        "<h2 style='font-size:15px;color:" + root.primaryColor + ";margin:24px 0 8px 0'>娉ㄦ剰浜嬮」</h2>" +
        "<p style='margin:0 0 2px 0'>路 PARAMETERS 蹇呴』妯″潡绾э紝鏃犲弬鏁板啓 <code>PARAMETERS = []</code></p>" +
        "<p style='margin:0 0 2px 0'>路 涓嶄慨鏀?PARAMETERS锛孖O 鐢?<code>pathlib.Path</code></p>" +
        "<p style='margin:0 0 2px 0'>路 鑰楁椂鎿嶄綔鍛ㄦ湡鎬ф鏌?<code>context.is_cancel_requested()</code></p>" +
        "<p style='margin:0'>路 鎻掍欢鏀?<code>plugins/user/</code> 鎴栫敤 <code>module_path</code></p>" +

        "<p style='color:" + root.textMuted + ";font-size:12px;margin-top:30px'>馃搫 瀹屾暣绀轰緥瑙?plugins/user/_TEMPLATE.py</p>" +
        "</body></html>"

    property url pluginSpecPdfSource: ""

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

    function showCategorySection(categoryLabel) {
        return root.algoCategoryFilter === "鍏ㄩ儴绠楁硶" || root.algoCategoryFilter === categoryLabel
    }

    function firstAlgoIdForCategory(categoryLabel) {
        for (var i = 0; i < algoListModel.count; i++) {
            var item = algoListModel.get(i)
            if (!item.isHeader && item.category === categoryLabel) return item.id
        }
        return -1
    }

    function applyAlgoCategoryFilter(categoryLabel) {
        root.algoCategoryFilter = categoryLabel || "鍏ㄩ儴绠楁硶"
        if (root.algoCategoryFilter === "鍏ㄩ儴绠楁硶") return

        if (root.algoCategoryFilter === "娓呮礂绠楁硶") root.cleaningExpanded = true
        if (root.algoCategoryFilter === "鐢熸垚绠楁硶") root.generationExpanded = true
        if (root.algoCategoryFilter === "璇勪及绠楁硶") root.evaluationExpanded = true
        if (root.algoCategoryFilter === "璁粌绠楁硶") root.trainingExpanded = true

        if (root.selectedAlgoIndex !== -1 && root.selectedAlgoField("category") === root.algoCategoryFilter) return
        var firstId = root.firstAlgoIdForCategory(root.algoCategoryFilter)
        if (firstId !== -1) root.selectedAlgoId = firstId
    }

    // ================= 鑳屾櫙 =================
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

    // ================= 鏁版嵁妯″瀷 =================
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

    ListModel { id: bindingEvalModel }

    function refreshBindingEvalCombo() {
        bindingEvalModel.clear()
        bindingEvalModel.append({key: "", display: "-- 鏈粦瀹?--"})
        for (var i = 0; i < algoListModel.count; i++) {
            var a = algoListModel.get(i)
            if (a.category === "璇勪及绠楁硶") {
                bindingEvalModel.append({key: a.key, display: a.name})
            }
        }
        var boundKey = root.selectedAlgoField("boundEvalKey")
        for (var j = 0; j < bindingEvalModel.count; j++) {
            if (bindingEvalModel.get(j).key === boundKey) {
                bindingEvalCombo.currentIndex = j
                return
            }
        }
        bindingEvalCombo.currentIndex = 0
    }

    // 鍏变韩绠楁硶鍒楄〃椤瑰鎵?
    Component {
        id: algoItemDelegate
        Rectangle {
            width: parent ? parent.width : 260
            height: model.isHeader ? 30 : 64
            radius: 0
            color: {
                if (model.isHeader) return Qt.rgba(29/255, 78/255, 216/255, 0.06)
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
                enabled: !model.isHeader
                onClicked: { root.selectedAlgoId = model.id; root.refreshBindingEvalCombo() }
            }

            Text {
                anchors.left: parent.left
                anchors.leftMargin: 14
                anchors.verticalCenter: parent.verticalCenter
                text: model.subCategory || model.name || ""
                color: root.devAccentColor
                font.pixelSize: 11
                font.bold: true
                visible: model.isHeader
            }

            RowLayout {
                anchors.fill: parent
                anchors.margins: 10
                spacing: 12
                visible: !model.isHeader

                Rectangle {
                    width: 34; height: 34; radius: 5
                    color: root.bgDark
                    border.color: model.id === root.selectedAlgoId ? root.devAccentColor : root.borderColor
                    border.width: 1
                    Text {
                        text: {
                            var c = model.category
                            if (c === "娓呮礂绠楁硶") return "娓?
                            if (c === "鐢熸垚绠楁硶") return "鐢?
                            if (c === "璇勪及绠楁硶") return "璇?
                            if (c === "璁粌绠楁硶") return "璁?
                            return "?"
                        }
                        color: {
                            var c = model.category
                            if (c === "娓呮礂绠楁硶") return root.cleanTagColor
                            if (c === "鐢熸垚绠楁硶") return root.genTagColor
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

    // ================= 鍏ㄥ眬鎻愮ず Toast =================
    property string toastMessage: "鉁?鎿嶄綔鎴愬姛"

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

    Component.onDestruction: {
        toastCloseTimer.stop()
    }

    function showToast(msg) {
        root.toastMessage = msg
        toastMsg.open()
        toastAnim.restart()
        toastCloseTimer.restart()
    }

    Popup {
        id: pluginSpecPopup
        modal: true
        focus: true
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        x: Math.round((root.width - width) / 2)
        y: Math.round((root.height - height) / 2)
        width: Math.min(root.width - 40, 1180)
        height: Math.min(root.height - 40, 760)
        padding: 0
        background: Item {
            // 鏌斿拰闃村奖灞?
            Rectangle {
                anchors.fill: parent; anchors.margins: 3; radius: 14
                color: Qt.rgba(0, 0, 0, 0.15)
            }
            Rectangle {
                anchors.fill: parent; anchors.margins: 1; radius: 12
                color: root.panelBg; border.color: root.borderColor; border.width: 1
            }
        }
        contentItem: ColumnLayout {
            spacing: 0

            // 鏍囬鏍?(鍙充笂瑙?鎵╁ぇ/鍏抽棴)
            Rectangle {
                Layout.fillWidth: true; height: 44
                color: "transparent"
                RowLayout {
                    anchors.fill: parent; anchors.leftMargin: 20; anchors.rightMargin: 8
                    Text { text: "馃搵 鎻掍欢瑙勮寖"; color: root.textColor; font.pixelSize: 14; font.bold: true; Layout.fillWidth: true }
                    Rectangle { id: expandIcon; width: 28; height: 28; radius: 6
                        color: expandMa.containsMouse ? root.tableHoverBg : "transparent"
                        property bool isMax: false
                        Text { text: expandIcon.isMax ? "馃棗" : "馃棖"; color: root.textMuted; font.pixelSize: 14; anchors.centerIn: parent }
                        MouseArea { id: expandMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                expandIcon.isMax = !expandIcon.isMax
                                if (expandIcon.isMax) { pluginSpecPopup.width = root.width - 20; pluginSpecPopup.height = root.height - 20 }
                                else { pluginSpecPopup.width = Math.min(root.width - 40, 1180); pluginSpecPopup.height = Math.min(root.height - 40, 760) }
                            }
                        }
                    }
                    Rectangle { id: closeIcon; width: 28; height: 28; radius: 6
                        color: closeMa.containsMouse ? Qt.rgba(245,63,63,0.1) : "transparent"
                        Text { text: "鉁?; color: closeMa.containsMouse ? root.dangerColor : root.textMuted; font.pixelSize: 14; anchors.centerIn: parent }
                        MouseArea { id: closeMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                            onClicked: pluginSpecPopup.close()
                        }
                    }
                }
            }
            // 鍐呭鍖?
            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                color: Theme.mode === "dark" ? "#202124" : "#f5f7fb"
                clip: true

                PdfDocument {
                    id: pluginSpecPdfDocument
                    source: root.pluginSpecPdfSource
                }

                PdfMultiPageView {
                    id: pluginSpecPdfView
                    anchors.fill: parent
                    anchors.margins: 8
                    document: pluginSpecPdfDocument
                    visible: root.pluginSpecPdfSource !== ""
                }

                Text {
                    anchors.centerIn: parent
                    text: root.pluginSpecPdfSource === "" ? "\u6b63\u5728\u52a0\u8f7d\u63d2\u4ef6\u89c4\u8303..." : ""
                    color: root.textMuted
                    font.pixelSize: 13
                    visible: root.pluginSpecPdfSource === ""
                }
            }

            // 搴曢儴鏍?(鍙充笅瑙?涓嬭浇PDF)
            Rectangle {
                Layout.fillWidth: true; height: 40
                color: "transparent"
                RowLayout { anchors.fill: parent; anchors.rightMargin: 12
                    Item { Layout.fillWidth: true }
                    Rectangle { id: downloadBtn; width: 90; height: 26; radius: 13
                        color: downloadMa.containsMouse ? root.primaryColor : root.tableHoverBg
                        Text { text: "猬?涓嬭浇PDF"; color: downloadMa.containsMouse ? "white" : root.textColor; font.pixelSize: 11; anchors.centerIn: parent }
                        MouseArea { id: downloadMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                            onClicked: { pluginSpecSaveDialog.selectedFile = "ISG_plugin_spec_professional.pdf"; pluginSpecSaveDialog.open() }
                        }
                    }
                }
            }
        }
    }

    function categoryLabel(category) {
        if (category === "cleaning") return "娓呮礂绠楁硶"
        if (category === "generation") return "鐢熸垚绠楁硶"
        if (category === "evaluation") return "璇勪及绠楁硶"
        if (category === "training") return "璁粌绠楁硶"
        return category || "鏈垎绫?
    }

    function categoryValue(label) {
        if (label === "娓呮礂绠楁硶") return "cleaning"
        if (label === "鐢熸垚绠楁硶") return "generation"
        if (label === "璇勪及绠楁硶") return "evaluation"
        if (label === "璁粌绠楁硶") return "training"
        return label || "generation"
    }

    function scenarioKeyFromName(name) {
        if (name === "姘翠笅鐩爣妫€娴嬩笌璇嗗埆") return "underwater_target_detection_recognition"
        if (name === "鑸拌埞鐩爣璇嗗埆涓庤窡韪?) return "ship_target_recognition_tracking"
        if (name === "绯荤粺鍋ュ悍鐘舵€侀浼颁笌鏁呴殰璇婃柇") return "system_health_fault_diagnosis"
        if (name === "鏅鸿兘鍐崇瓥涓庢寚鎸ユ帶鍒?) return "intelligent_decision_command_control"
        if (name === "澶氭ā鎬佹暟鎹瀺鍚?) return "multimodal_data_fusion"
        return ""
    }

    function scenarioNameFromKey(key) {
        if (key === "underwater_target_detection_recognition") return "姘翠笅鐩爣妫€娴嬩笌璇嗗埆"
        if (key === "ship_target_recognition_tracking") return "鑸拌埞鐩爣璇嗗埆涓庤窡韪?
        if (key === "system_health_fault_diagnosis") return "绯荤粺鍋ュ悍鐘舵€侀浼颁笌鏁呴殰璇婃柇"
        if (key === "intelligent_decision_command_control") return "鏅鸿兘鍐崇瓥涓庢寚鎸ユ帶鍒?
        if (key === "multimodal_data_fusion") return "澶氭ā鎬佹暟鎹瀺鍚?
        return key || "鏈寚瀹氬満鏅?
    }

    function modalityFromSubCategory(text) {
        if (text.indexOf("鏂囨湰") !== -1) return "text"
        if (text.indexOf("闊抽") !== -1) return "audio"
        if (text.indexOf("琛ㄦ牸") !== -1 || text.indexOf("鏃跺簭") !== -1) return "tabular"
        if (text.indexOf("瑙嗛") !== -1) return "video"
        if (text.indexOf("澶氭ā鎬?) !== -1) return "multimodal"
        return "image"
    }

    function subtypeLabel(category, modality) {
        if (category === "cleaning") {
            if (modality === "text") return "鏂囨湰娓呮礂绛栫暐"
            if (modality === "audio") return "闊抽娓呮礂绛栫暐"
            if (modality === "tabular") return "琛ㄦ牸鏁版嵁娓呮礂"
            return "鍥惧儚娓呮礂绛栫暐"
        }
        if (category === "generation") {
            if (modality === "text") return "鏂囨湰澧炲己鏂规硶"
            if (modality === "audio") return "闊抽澧炲己鏂规硶"
            if (modality === "multimodal") return "澶氭ā鎬佸寮烘柟娉?
            return "鍥惧儚澧炲己鏂规硶"
        }
        if (category === "training") {
            if (modality === "text") return "鏂囨湰璁粌妯″瀷"
            if (modality === "audio") return "闊抽璁粌妯″瀷"
            if (modality === "tabular") return "鏃跺簭璁粌妯″瀷"
            if (modality === "multimodal") return "澶氭ā鎬佽缁冩ā鍨?
            return "鍥惧儚璁粌妯″瀷"
        }
        if (category === "evaluation") {
            if (modality === "text") return "鏂囨湰璇勪及鏂规硶"
            if (modality === "audio") return "闊抽璇勪及鏂规硶"
            if (modality === "tabular") return "鏃跺簭璇勪及鏂规硶"
            if (modality === "multimodal") return "澶氭ā鎬佽瘎浼版柟娉?
            return "鍥惧儚璇勪及鏂规硶"
        }
        return "鏈垎绫?
    }

    function modalityOrder(modality) {
        if (modality === "image") return 0
        if (modality === "audio") return 1
        if (modality === "text") return 2
        if (modality === "tabular") return 3
        if (modality === "video") return 4
        return 5
    }

    function categoryOrder(category) {
        if (category === "cleaning") return 0
        if (category === "generation") return 1
        if (category === "evaluation") return 2
        if (category === "training") return 3
        return 4
    }

    function isUserPlugin(item) {
        var script = String(item.script_path || "")
        return script !== ""
    }

    function normalizeParamType(typeName) {
        var t = String(typeName || "string")
        if (t === "number") return "float"
        if (t === "integer") return "int"
        if (t === "boolean") return "bool"
        return t
    }

    function normalizeParamDefault(value, typeName) {
        var t = root.normalizeParamType(typeName)
        if (t === "int") {
            var intValue = parseInt(value)
            return isNaN(intValue) ? 0 : intValue
        }
        if (t === "float") {
            var floatValue = parseFloat(value)
            return isNaN(floatValue) ? 0 : floatValue
        }
        if (t === "bool") {
            if (typeof value === "boolean") return value
            var text = String(value || "").toLowerCase()
            return text === "true" || text === "1" || text === "yes"
        }
        return value
    }

    function validateParamValue(value, typeName) {
        var t = root.normalizeParamType(typeName)
        if (t === "int") return /^-?\d+$/.test(String(value || "").trim())
        if (t === "float") return /^-?(\d+(\.\d*)?|\.\d+)$/.test(String(value || "").trim())
        if (t === "bool") {
            var text = String(value || "").toLowerCase()
            return text === "true" || text === "false" || text === "1" || text === "0" || text === "yes" || text === "no"
        }
        return true
    }

    function isScriptPath(value) {
        var path = String(value || "")
        return path.toLowerCase().indexOf(".py") !== -1 || path.indexOf("/") !== -1 || path.indexOf("\\") !== -1
    }

    function compareAlgorithms(a, b) {
        var ac = root.categoryOrder(a.category)
        var bc = root.categoryOrder(b.category)
        if (ac !== bc) return ac - bc

        if (a.category === "training" && b.category === "training") {
            var av = a.validation_rules || {}
            var bv = b.validation_rules || {}
            var as = av["scenario_key"] || ""
            var bs = bv["scenario_key"] || ""
            if (as !== bs) return String(as).localeCompare(String(bs))
        }

        var am = root.modalityOrder(a.modality)
        var bm = root.modalityOrder(b.modality)
        if (am !== bm) return am - bm

        var au = root.isUserPlugin(a) ? 0 : 1
        var bu = root.isUserPlugin(b) ? 0 : 1
        if (au !== bu) return au - bu

        return String(a.name || "").localeCompare(String(b.name || ""), "zh-Hans-CN")
    }

    function appendGroupedEntry(model, entry, lastSubCategory) {
        if (lastSubCategory !== entry.subCategory) {
            model.append({
                isHeader: true,
                id: -1,
                name: entry.subCategory,
                category: entry.category,
                subCategory: entry.subCategory,
                modality: entry.modality,
                script: "",
                desc: "",
                paramsJson: "[]",
                enabled: false
            })
        }
        model.append(entry)
        return entry.subCategory
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
            var ptype = root.normalizeParamType(p.type)
            var paramDef = {
                name: p.n,
                label: p.label || p.n,
                type: ptype,
                required: false,
                default_value: root.normalizeParamDefault(p.v, ptype),
                description: p.desc || ""
            }
            if (ptype === "int" || ptype === "float") {
                paramDef.min_value = p.min !== undefined && p.min !== "" ? parseFloat(p.min) : null
                paramDef.max_value = p.max !== undefined && p.max !== "" ? parseFloat(p.max) : null
            }
            if (ptype === "select" && p.options) {
                if (Array.isArray(p.options)) {
                    paramDef.options = p.options
                } else {
                    paramDef.options = String(p.options).split(",").map(function(s) { return s.trim() }).filter(function(s) { return s !== "" })
                }
            }
            params.push(paramDef)
        }
        return {
            key: inputAlgoName.text.trim().replace(/\s+/g, "_").toLowerCase(),
            name: inputAlgoName.text.trim(),
            category: category,
            modality: modality,
            entry_type: "python_function",
            callable_name: "run",
            description: inputDesc.text,
            input_contract: {"dataset_required": true, "sample_required": true},
            output_contract: category === "cleaning" ? {"produces": ["suggestions"], "artifact_types": []}
                          : category === "training" ? {"produces": ["model_checkpoint"], "artifact_types": ["checkpoint"]}
                          : category === "evaluation" ? {"produces": ["metrics", "artifacts"], "artifact_types": ["report"]}
                          : {"produces": ["outputs"], "artifact_types": []},
            validation_rules: category === "training" ? {scenario_key: root.scenarioKeyFromName(subCatStr)} : {},
            parameters: params,
            modality: category === "training" ? "multimodal" : modality
        }
    }

    Component.onCompleted: root.loadAlgorithms()
    onVisibleChanged: { if (visible) root.loadAlgorithms() }
    onSelectedAlgoIdChanged: root.refreshBindingEvalCombo()

    Connections {
        target: backendService
        function onAlgorithmsUpdated(items) {
            if (!root.visible) return  // 鍙湪褰撳墠椤甸潰鍙鏃跺鐞?
            algoListModel.clear()
            cleaningAlgoModel.clear()
            generationAlgoModel.clear()
            evaluationAlgoModel.clear()
            trainingAlgoModel.clear()
            var cCount = 0, gCount = 0, eCount = 0, tCount = 0
            var sortedItems = (items || []).slice().sort(root.compareAlgorithms)
            var lastCleaningSub = ""
            var lastGenerationSub = ""
            var lastEvaluationSub = ""
            var lastTrainingSub = ""
            for (var i = 0; i < sortedItems.length; i++) {
                var item = sortedItems[i]
                var params = []
                var sourceParams = item.parameters || []
                for (var p = 0; p < sourceParams.length; p++) {
                    var sp = sourceParams[p]
                    params.push({
                        "n": sp.name || "",
                        "label": sp.label || sp.name || "",
                        "v": String(sp.default_value !== undefined ? sp.default_value : ""),
                        "type": root.normalizeParamType(sp.type),
                        "min": String(sp.min_value !== undefined && sp.min_value !== null ? sp.min_value : ""),
                        "max": String(sp.max_value !== undefined && sp.max_value !== null ? sp.max_value : ""),
                        "options": sp.options || [],
                        "desc": sp.description || ""
                    })
                }
                var subCat = root.subtypeLabel(item.category, item.modality)
                if (item.category === "training") {
                    var vr = item.validation_rules || {}
                    var scKey = vr["scenario_key"] || ""
                    if (scKey) subCat = "鍦烘櫙: " + root.scenarioNameFromKey(scKey)
                }
                var entry = {
                    id: item.id,
                    key: item.key,
                    name: item.name,
                    category: root.categoryLabel(item.category),
                    subCategory: subCat,
                    modality: item.modality,
                    script: item.script_path || item.module_path || "",
                    scriptPath: item.script_path || "",
                    modulePath: item.module_path || "",
                    desc: item.description || "",
                    paramsJson: JSON.stringify(params),
                    enabled: item.status === "enabled",
                    isHeader: false,
                    scenarioKey: (item.category === "training" ? ((item.validation_rules || {}).scenario_key || "") : ""),
                    boundEvalKey: item.bound_evaluation_key || "",
                    boundEvalName: item.bound_evaluation_name || ""
                }
                algoListModel.append(entry)
                if (item.category === "cleaning") {
                    lastCleaningSub = root.appendGroupedEntry(cleaningAlgoModel, entry, lastCleaningSub)
                    cCount++
                } else if (item.category === "generation") {
                    lastGenerationSub = root.appendGroupedEntry(generationAlgoModel, entry, lastGenerationSub)
                    gCount++
                } else if (item.category === "evaluation") {
                    lastEvaluationSub = root.appendGroupedEntry(evaluationAlgoModel, entry, lastEvaluationSub)
                    eCount++
                } else {
                    lastTrainingSub = root.appendGroupedEntry(trainingAlgoModel, entry, lastTrainingSub)
                    tCount++
                }
            }
            root.cleaningCount = cCount
            root.generationCount = gCount
            root.evaluationCount = eCount
            root.trainingCount = tCount
            root.totalAlgoCount = items.length
            if (sortedItems.length > 0 && root.selectedAlgoId === -1) {
                root.selectedAlgoId = sortedItems[0].id
            }
        }
    }

    function algorithmUsageText(category) {
        if (root.selectedAlgoIndex === -1) {
            return "閫夋嫨绠楁硶鍚庡彲鏌ョ湅浣跨敤璇存槑銆傚畬鏁存枃妗? docs/ALGORITHM_USAGE_GUIDE.md"
        }
        if (category === "娓呮礂绠楁硶") {
            return "娓呮礂绠楁硶鐢ㄤ簬鍙戠幇閲嶅銆佷綆璐ㄣ€佸紓甯告垨闇€鑴辨晱鐨勬牱鏈€傝緭鍏ヤ负鏁版嵁闆嗘牱鏈矾寰勫拰鍙傛暟瀛楀吀锛岃緭鍑轰负娓呮礂寤鸿銆佺疆淇″害鍜屽彲閫夊鐞嗙粨鏋溿€備笂绾垮墠闇€纭鍙傛暟榛樿鍊笺€佽緭鍑哄缓璁被鍨嬪拰澶辫触鏃ュ織銆?
        }
        return "鐢熸垚绠楁硶鐢ㄤ簬瀵瑰浘鍍忋€侀煶棰戞垨鏂囨湰鏍锋湰鍋氭墿澧炪€傝緭鍏ヤ负婧愭牱鏈矾寰勩€佽緭鍑虹洰褰曞拰鍙傛暟瀛楀吀锛岃緭鍑轰负鏂板鏍锋湰鏂囦欢鍙婂寮哄厓鏁版嵁銆備笂绾垮墠闇€纭鐢熸垚鏁伴噺銆佽緭鍑烘牸寮忋€佽祫婧愬崰鐢ㄥ拰鍙鐜板疄楠屽弬鏁般€?
    }

    // ================= 寮圭獥锛氭枃浠堕€夋嫨鍣?=================
    FileDialog {
        id: scriptFileDialog
        title: "閫夋嫨绠楁硶鑴氭湰/绋嬪簭鏂囦欢"
        nameFilters: ["Python 鑴氭湰 (*.py)"]
        onAccepted: {
            var path = selectedFile.toString()
            var cleanPath = decodeURIComponent(path.replace(/^(file:\/{2,3})/, ""))
            inputScriptPath.text = cleanPath
            var result = backendService.reflectParameters(cleanPath)
            if (result && result.ok) {
                editingParamsModel.clear()
                var params = result.parameters || []
                for (var i = 0; i < params.length; i++) {
                    var p = params[i]
                    editingParamsModel.append({
                        "n": p.name || "",
                        "label": p.label || p.name || "",
                        "v": String(p.default !== undefined ? p.default : ""),
                        "type": root.normalizeParamType(p.type),
                        "min": String(p.min !== undefined && p.min !== null ? p.min : ""),
                        "max": String(p.max !== undefined && p.max !== null ? p.max : ""),
                        "options": p.options || [],
                        "desc": p.description || ""
                    })
                }
                root.showToast("鉁?宸茶嚜鍔ㄥ姞杞?" + params.length + " 涓弬鏁?)
            } else {
                root.showToast("鈿狅笍 鍙傛暟鍙嶅皠澶辫触: " + ((result && (result.error || result.message)) ? (result.error || result.message) : "鏈煡閿欒"))
            }
        }
    }

    // ================= 寮圭獥锛氭彃浠惰鑼?PDF 淇濆瓨 =================
    FileDialog {
        id: pluginSpecSaveDialog
        title: "淇濆瓨鎻掍欢瑙勮寖 PDF"
        fileMode: FileDialog.SaveFile
        nameFilters: ["PDF 鏂囨。 (*.pdf)"]
        onAccepted: {
            var path = selectedFile.toString()
            var cleanPath = decodeURIComponent(path.replace(/^(file:\/{2,3})/, ""))
            var result = backendService.downloadAlgorithmPluginSpec(cleanPath)
            if (result && result.status === "success") root.showToast("鉁?鎻掍欢瑙勮寖宸蹭笅杞?)
            else root.showToast("鈿狅笍 " + ((result && result.message) ? result.message : "鎻掍欢瑙勮寖涓嬭浇澶辫触"))
        }
    }

    // ================= 寮圭獥锛氫簩娆＄‘璁ゅ垹闄?=================
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
                Text { text: "鈿狅笍"; font.pixelSize: 20 }
                Text { text: "纭鍗歌浇姝ょ畻娉曞悧锛?; color: root.textColor; font.pixelSize: 15; font.bold: true }
            }

            Text {
                text: "鍗歌浇鍚庯紝娓呮礂鎴栫敓鎴愭ā鍧楀皢鏃犳硶鍐嶈皟鐢ㄦ鑷畾涔夌畻娉曘€?
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
                    text: "鍙栨秷"
                    Layout.preferredWidth: 80
                    Layout.preferredHeight: 30
                    background: Rectangle { color: "transparent"; border.color: root.borderColor; border.width: 1; radius: 4 }
                    contentItem: Text { text: parent.text; color: root.textMuted; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                    onClicked: deleteConfirmPopup.close()
                }
                Button {
                    text: "纭鍗歌浇"
                    Layout.preferredWidth: 80
                    Layout.preferredHeight: 30
                    background: Rectangle { color: root.dangerColor; radius: 4 }
                    contentItem: Text { text: parent.text; color: "black"; font.bold: true; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                    onClicked: {
                        if (root.pendingDeleteIndex !== -1) {
                            var result = backendService.deleteAlgorithm(algoListModel.get(root.pendingDeleteIndex).id)
                            if (result && result.ok) {
                                root.selectedAlgoId = -1
                                root.loadAlgorithms()
                                root.showToast("馃棏锔?绠楁硶宸叉垚鍔熷嵏杞?)
                            } else {
                                root.showToast("鈿狅笍 绠楁硶鍗歌浇澶辫触")
                            }
                        }
                        deleteConfirmPopup.close()
                    }
                }
            }
        }
    }

    // ================= 鏍稿績寮圭獥锛氶厤缃柊绠楁硶/淇敼绠楁硶 =================
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

            // 鏍囬鏍?
            RowLayout {
                Layout.fillWidth: true
                Text {
                    text: root.pendingEditIndex === -1 ? "馃З 鎺ュ叆鑷畾涔夋柊鎻掍欢" : "鈿欙笍 淇敼鎻掍欢搴曞眰閰嶇疆"
                    color: root.devAccentColor
                    font.pixelSize: 18
                    font.bold: true
                }
                Item { Layout.fillWidth: true }
                Rectangle {
                    width: 30; height: 30; color: "transparent"; radius: 4
                    Text { text: "鉁?; color: root.textMuted; font.pixelSize: 18; anchors.centerIn: parent }
                    MouseArea {
                        anchors.fill: parent; cursorShape: Qt.PointingHandCursor; hoverEnabled: true
                        onEntered: { parent.color = root.tableHoverBg }
                        onExited: { parent.color = "transparent" }
                        onClicked: algoConfigPopup.close()
                    }
                }
            }

            Rectangle { Layout.fillWidth: true; height: 1; color: root.borderColor }

            // 宸﹀彸鍒嗘爮锛氬乏渚у熀纭€淇℃伅锛屽彸渚у姩鎬佸弬鏁伴厤缃?
            RowLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 30

                // === 宸︽爮锛氬熀纭€淇℃伅 ===
                ColumnLayout {
                    Layout.preferredWidth: 320
                    Layout.fillHeight: true
                    spacing: 15

                    Text { text: "馃摑 鍩虹鏄犲皠淇℃伅"; color: root.textColor; font.pixelSize: 14; font.bold: true }

                    ColumnLayout {
                        spacing: 6; Layout.fillWidth: true
                        Text { text: "鎻掍欢鍚嶇О:"; color: root.textMuted; font.pixelSize: 12 }
                        Rectangle {
                            Layout.fillWidth: true; height: 36; color: root.bgDark; radius: 4; border.color: root.borderColor; border.width: 1
                            TextInput { id: inputAlgoName; color: root.textColor; font.pixelSize: 13; anchors.fill: parent; leftPadding: 10; verticalAlignment: TextInput.AlignVCenter }
                        }
                    }

                    ColumnLayout {
                        spacing: 6; Layout.fillWidth: true
                        Text {
                            text: inputCategory.currentIndex === 2 ? "鎵€灞炲簲鐢ㄥ満鏅?" : "缁嗗垎绛栫暐绫诲埆 (鍙洿鎺ヨ緭鍏ユ柊澧?:"
                            color: root.textMuted; font.pixelSize: 12
                        }
                        ComboBox {
                            id: inputCategory
                            model: ["娓呮礂绠楁硶", "鐢熸垚绠楁硶", "璁粌绠楁硶", "璇勪及绠楁硶"]
                            Layout.fillWidth: true; Layout.preferredHeight: 36
                            background: Rectangle { color: root.bgDark; border.color: root.borderColor; border.width: 1; radius: 4 }
                            contentItem: Text { text: inputCategory.currentText; color: root.textColor; font.pixelSize: 13; verticalAlignment: Text.AlignVCenter; leftPadding: 10 }
                            popup: Popup {
                                y: inputCategory.height + 2; width: inputCategory.width; padding: 4
                                background: Rectangle { color: root.panelBg; border.color: root.borderColor; radius: 6 }
                                contentItem: ListView {
                                    clip: true; implicitHeight: contentHeight
                                    model: inputCategory.delegateModel
                                }
                            }
                            delegate: ItemDelegate {
                                width: inputCategory.width - 8; height: 32
                                contentItem: Text { text: modelData; color: root.textColor; font.pixelSize: 13; verticalAlignment: Text.AlignVCenter; leftPadding: 10 }
                                background: Rectangle { color: hovered ? root.tableHoverBg : "transparent"; radius: 4 }
                            }
                        }
                    }

                    ColumnLayout {
                        spacing: 6; Layout.fillWidth: true
                        ComboBox {
                            id: inputSubCategory
                            editable: inputCategory.currentIndex !== 2
                            model: {
                                if (inputCategory.currentIndex === 0) return ["鍥惧儚娓呮礂绛栫暐", "鏂囨湰娓呮礂绛栫暐", "闊抽娓呮礂绛栫暐", "琛ㄦ牸鏁版嵁娓呮礂"]
                                if (inputCategory.currentIndex === 1) return ["鍥惧儚澧炲己鏂规硶", "鏂囨湰澧炲己鏂规硶", "闊抽澧炲己鏂规硶", "澶氭ā鎬佸寮烘柟娉?, "娣卞害瀛︿範鐢熸垚"]
                                if (inputCategory.currentIndex === 2) return ["姘翠笅鐩爣妫€娴嬩笌璇嗗埆", "鑸拌埞鐩爣璇嗗埆涓庤窡韪?, "绯荤粺鍋ュ悍鐘舵€侀浼颁笌鏁呴殰璇婃柇", "鏅鸿兘鍐崇瓥涓庢寚鎸ユ帶鍒?, "澶氭ā鎬佹暟鎹瀺鍚?]
                                if (inputCategory.currentIndex === 3) return ["澶氭ā鎬佽瘎浼版柟娉?]
                                return []
                            }
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
                        Text { text: "鎸傝浇鑴氭湰/绋嬪簭鐗╃悊璺緞:"; color: root.textMuted; font.pixelSize: 12 }
                        RowLayout {
                            Layout.fillWidth: true; spacing: 8
                            Rectangle {
                                Layout.fillWidth: true; height: 36; color: root.bgDark; radius: 4; border.color: root.borderColor; border.width: 1
                                TextInput { id: inputScriptPath; color: root.devAccentColor; font.pixelSize: 13; font.family: "Courier"; anchors.fill: parent; leftPadding: 10; verticalAlignment: TextInput.AlignVCenter; clip: true }
                            }
                            Button {
                                text: "娴忚..."; Layout.preferredHeight: 36; Layout.preferredWidth: 60
                                background: Rectangle { color: root.tableHoverBg; border.color: root.borderColor; border.width: 1; radius: 4 }
                                contentItem: Text { text: parent.text; color: root.textColor; font.pixelSize: 12; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                                onClicked: scriptFileDialog.open()
                            }
                        }
                    }

                    ColumnLayout {
                        spacing: 6; Layout.fillWidth: true
                        Text { text: "搴曞眰鍔熻兘绠€杩?"; color: root.textMuted; font.pixelSize: 12 }
                        Rectangle {
                            Layout.fillWidth: true; Layout.preferredHeight: 60; color: root.bgDark; radius: 4; border.color: root.borderColor; border.width: 1
                            TextEdit { id: inputDesc; color: root.textColor; font.pixelSize: 13; anchors.fill: parent; padding: 10; wrapMode: TextEdit.Wrap }
                        }
                    }

                    Item { Layout.fillHeight: true }
                }

                Rectangle { Layout.fillHeight: true; width: 1; color: root.borderColor }

                // === 鍙虫爮锛氬姩鎬佸弬鏁伴厤缃紩鎿?===
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    spacing: 15

                    RowLayout {
                        Layout.fillWidth: true
                        Text { text: "鈿欙笍 鍔ㄦ€佸弽灏勫弬鏁板垪琛?; color: root.textColor; font.pixelSize: 14; font.bold: true }
                        Item { Layout.fillWidth: true }
                        Text { text: "杩欎簺鍙傛暟灏嗗湪鍔熻兘闈㈡澘涓姩鎬佺敓鎴愯緭鍏ユ"; color: root.textMuted; font.pixelSize: 11 }
                    }

                    // 鍙傛暟鍒楄〃瑙嗗浘
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
                                    Text { text: "鍙傛暟鍚?; color: root.textMuted; font.pixelSize: 11; font.bold: true; Layout.fillWidth: true }
                                    Text { text: "鏍囩"; color: root.textMuted; font.pixelSize: 11; font.bold: true; Layout.fillWidth: true }
                                    Text { text: "绫诲瀷"; color: root.textMuted; font.pixelSize: 11; font.bold: true; Layout.preferredWidth: 70 }
                                    Text { text: "鎿嶄綔"; color: root.textMuted; font.pixelSize: 11; font.bold: true; Layout.preferredWidth: 32; horizontalAlignment: Text.AlignHCenter }
                                }
                            }

                            ListView {
                                id: paramListView
                                Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                                model: editingParamsModel

                                Text {
                                    visible: editingParamsModel.count === 0
                                    text: "姝ゆ彃浠舵棤鍔ㄦ€佸弬鏁伴厤缃?
                                    color: root.textMuted; font.pixelSize: 12; anchors.centerIn: parent
                                }

                                delegate: Rectangle {
                                    width: paramListView.width
                                    height: (root.normalizeParamType(model.type) === "int" || root.normalizeParamType(model.type) === "float" || root.normalizeParamType(model.type) === "select") ? 110 : 76
                                    color: index % 2 === 0 ? "transparent" : root.tableHoverBg

                                    ColumnLayout {
                                        anchors.fill: parent
                                        anchors.leftMargin: 10
                                        anchors.rightMargin: 10
                                        spacing: 2

                                        // 绗竴琛岋細鍙傛暟鍚?+ 鏍囩 + 绫诲瀷 + 榛樿鍊?+ 鍒犻櫎
                                        RowLayout {
                                            Layout.fillWidth: true
                                            Layout.preferredHeight: 36
                                            spacing: 6
                                            // 鍙傛暟鍚?
                                            Rectangle {
                                                Layout.fillWidth: true; Layout.minimumWidth: 82; height: 28; color: "transparent"; border.color: root.borderColor; border.width: 1; radius: 3
                                                TextInput {
                                                    text: model.n; color: root.textColor; font.pixelSize: 11; anchors.fill: parent; leftPadding: 5; rightPadding: 5; clip: true; verticalAlignment: TextInput.AlignVCenter
                                                    onTextChanged: editingParamsModel.setProperty(index, "n", text)
                                                }
                                            }
                                            // 鏄剧ず鏍囩
                                            Rectangle {
                                                Layout.fillWidth: true; Layout.minimumWidth: 82; height: 28; color: "transparent"; border.color: root.borderColor; border.width: 1; radius: 3
                                                TextInput {
                                                    text: model.label; color: root.textColor; font.pixelSize: 11; anchors.fill: parent; leftPadding: 5; rightPadding: 5; clip: true; verticalAlignment: TextInput.AlignVCenter
                                                    onTextChanged: editingParamsModel.setProperty(index, "label", text)
                                                }
                                            }
                                            // 绫诲瀷閫夋嫨
                                            ComboBox {
                                                id: paramTypeCombo
                                                Layout.preferredWidth: 70; Layout.preferredHeight: 28
                                                model: ["string", "int", "float", "bool", "select"]
                                                currentIndex: {
                                                    var t = model.type || "string"
                                                    t = root.normalizeParamType(t)
                                                    if (t === "int") return 1
                                                    if (t === "float") return 2
                                                    if (t === "bool") return 3
                                                    if (t === "select") return 4
                                                    return 0
                                                }
                                                onActivated: editingParamsModel.setProperty(index, "type", currentText)
                                                background: Rectangle { color: root.bgDark; border.color: root.borderColor; border.width: 1; radius: 3 }
                                                contentItem: Text { text: paramTypeCombo.currentText; color: root.devAccentColor; font.pixelSize: 11; verticalAlignment: Text.AlignVCenter; leftPadding: 5 }
                                                popup: Popup {
                                                    y: paramTypeCombo.height + 2; width: 90; padding: 3
                                                    background: Rectangle { color: root.panelBg; border.color: root.borderColor; radius: 5 }
                                                    contentItem: ListView { clip: true; implicitHeight: contentHeight; model: paramTypeCombo.delegateModel }
                                                }
                                                delegate: ItemDelegate {
                                                    width: 84; height: 24
                                                    contentItem: Text { text: modelData; color: root.textColor; font.pixelSize: 11; verticalAlignment: Text.AlignVCenter; leftPadding: 6 }
                                                    background: Rectangle { color: hovered ? root.tableHoverBg : "transparent"; radius: 3 }
                                                }
                                            }
                                            // 榛樿鍊?
                                            Rectangle {
                                                visible: false
                                                Layout.fillWidth: true; height: 28; color: "transparent"; border.color: root.borderColor; border.width: 1; radius: 3
                                                TextInput {
                                                    text: model.v; color: root.devAccentColor; font.pixelSize: 11; anchors.fill: parent; leftPadding: 5; verticalAlignment: TextInput.AlignVCenter
                                                    onTextChanged: editingParamsModel.setProperty(index, "v", text)
                                                }
                                            }
                                            // 鍒犻櫎鎸夐挳
                                            Rectangle {
                                                Layout.preferredWidth: 26; height: 26; radius: 3
                                                color: delMa2.containsMouse ? root.dangerColor : "transparent"
                                                border.color: delMa2.containsMouse ? "transparent" : root.borderColor; border.width: 1
                                                Text { text: "鉁?; font.pixelSize: 11; anchors.centerIn: parent; color: delMa2.containsMouse ? "white" : root.textMuted }
                                                MouseArea { id: delMa2; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: editingParamsModel.remove(index) }
                                            }
                                        }

                                        // 绗簩琛岋細min/max (int/float) 鎴?options (select)
                                        RowLayout {
                                            Layout.fillWidth: true
                                            Layout.preferredHeight: 28
                                            spacing: 6
                                            Text {
                                                text: "榛樿鍊?; color: root.textMuted; font.pixelSize: 10
                                                Layout.preferredWidth: 44
                                            }
                                            Rectangle {
                                                Layout.fillWidth: true; height: 24; color: "transparent"; border.color: root.borderColor; border.width: 1; radius: 3
                                                TextInput {
                                                    text: model.v; color: root.devAccentColor; font.pixelSize: 10; anchors.fill: parent; leftPadding: 5; rightPadding: 5; clip: true; verticalAlignment: TextInput.AlignVCenter
                                                    onTextChanged: editingParamsModel.setProperty(index, "v", text)
                                                }
                                            }
                                        }

                                        RowLayout {
                                            Layout.fillWidth: true
                                            Layout.preferredHeight: 30
                                            visible: root.normalizeParamType(model.type) === "int" || root.normalizeParamType(model.type) === "float" || root.normalizeParamType(model.type) === "select"
                                            spacing: 6

                                            // int/float: min + max
                                            Text {
                                                visible: root.normalizeParamType(model.type) === "int" || root.normalizeParamType(model.type) === "float"
                                                text: "min"; color: root.textMuted; font.pixelSize: 10
                                                Layout.preferredWidth: 24
                                            }
                                            Rectangle {
                                                visible: root.normalizeParamType(model.type) === "int" || root.normalizeParamType(model.type) === "float"
                                                Layout.preferredWidth: 65; height: 24; color: "transparent"; border.color: root.borderColor; border.width: 1; radius: 3
                                                TextInput {
                                                    text: model.min; color: root.textMuted; font.pixelSize: 10; anchors.fill: parent; leftPadding: 4; rightPadding: 4; clip: true; verticalAlignment: TextInput.AlignVCenter
                                                    onTextChanged: editingParamsModel.setProperty(index, "min", text)
                                                }
                                            }
                                            Text {
                                                visible: root.normalizeParamType(model.type) === "int" || root.normalizeParamType(model.type) === "float"
                                                text: "max"; color: root.textMuted; font.pixelSize: 10
                                                Layout.preferredWidth: 28
                                            }
                                            Rectangle {
                                                visible: root.normalizeParamType(model.type) === "int" || root.normalizeParamType(model.type) === "float"
                                                Layout.preferredWidth: 65; height: 24; color: "transparent"; border.color: root.borderColor; border.width: 1; radius: 3
                                                TextInput {
                                                    text: model.max; color: root.textMuted; font.pixelSize: 10; anchors.fill: parent; leftPadding: 4; rightPadding: 4; clip: true; verticalAlignment: TextInput.AlignVCenter
                                                    onTextChanged: editingParamsModel.setProperty(index, "max", text)
                                                }
                                            }

                                            // select: options
                                            Text {
                                                visible: root.normalizeParamType(model.type) === "select"
                                                text: "閫夐」"; color: root.textMuted; font.pixelSize: 10
                                                Layout.preferredWidth: 28
                                            }
                                            Rectangle {
                                                visible: root.normalizeParamType(model.type) === "select"
                                                Layout.fillWidth: true; height: 24; color: "transparent"; border.color: root.borderColor; border.width: 1; radius: 3
                                                TextInput {
                                                    text: typeof model.options === "object" && model.options && model.options.length !== undefined ? model.options.join(",") : String(model.options || ""); color: root.textMuted; font.pixelSize: 10; anchors.fill: parent; leftPadding: 4; rightPadding: 4; clip: true; verticalAlignment: TextInput.AlignVCenter
                                                    onTextChanged: editingParamsModel.setProperty(index, "options", text.split(",").map(function(s) { return s.trim() }).filter(function(s) { return s !== "" }))
                                                }
                                            }
                                        }
                                    }
                                }
                            }

                            // 搴曢儴鏂板鍙傛暟鍖?
                            Rectangle {
                                Layout.fillWidth: true; height: 58; color: Theme.rowAlt
                                Rectangle { width: parent.width; height: 1; color: root.borderColor; anchors.top: parent.top }
                                RowLayout {
                                    anchors.fill: parent; anchors.leftMargin: 10; anchors.rightMargin: 10; spacing: 6
                                    TextField {
                                        id: newParamName; Layout.preferredWidth: 80; Layout.preferredHeight: 28
                                        color: root.textColor; font.pixelSize: 11; leftPadding: 5; rightPadding: 5; verticalAlignment: TextInput.AlignVCenter; clip: true
                                        placeholderText: "鍙傛暟鍚?; placeholderTextColor: root.textMuted
                                        background: Rectangle { color: root.panelBg; border.color: root.borderColor; border.width: 1; radius: 3 }
                                    }
                                    TextField {
                                        id: newParamLabel; Layout.preferredWidth: 80; Layout.preferredHeight: 28
                                        color: root.textColor; font.pixelSize: 11; leftPadding: 5; rightPadding: 5; verticalAlignment: TextInput.AlignVCenter; clip: true
                                        placeholderText: "鏍囩"; placeholderTextColor: root.textMuted
                                        background: Rectangle { color: root.panelBg; border.color: root.borderColor; border.width: 1; radius: 3 }
                                    }
                                    ComboBox {
                                        id: newParamType; Layout.preferredWidth: 65; Layout.preferredHeight: 28
                                        model: ["string", "int", "float", "bool", "select"]
                                        currentIndex: 0
                                        background: Rectangle { color: root.panelBg; border.color: root.borderColor; border.width: 1; radius: 3 }
                                        contentItem: Text { text: newParamType.currentText; color: root.devAccentColor; font.pixelSize: 11; verticalAlignment: Text.AlignVCenter; leftPadding: 5 }
                                        popup: Popup {
                                            y: newParamType.height + 2; width: 90; padding: 3
                                            background: Rectangle { color: root.panelBg; border.color: root.borderColor; radius: 5 }
                                            contentItem: ListView { clip: true; implicitHeight: contentHeight; model: newParamType.delegateModel }
                                        }
                                        delegate: ItemDelegate {
                                            width: 84; height: 24
                                            contentItem: Text { text: modelData; color: root.textColor; font.pixelSize: 11; verticalAlignment: Text.AlignVCenter; leftPadding: 6 }
                                            background: Rectangle { color: hovered ? root.tableHoverBg : "transparent"; radius: 3 }
                                        }
                                    }
                                    TextField {
                                        id: newParamVal; Layout.fillWidth: true; Layout.preferredHeight: 28
                                        color: root.devAccentColor; font.pixelSize: 11; leftPadding: 5; rightPadding: 5; verticalAlignment: TextInput.AlignVCenter; clip: true
                                        placeholderText: "榛樿鍊?; placeholderTextColor: root.textMuted
                                        background: Rectangle { color: root.panelBg; border.color: root.borderColor; border.width: 1; radius: 3 }
                                    }
                                    Button {
                                        text: "娣诲姞"; Layout.preferredWidth: 45; Layout.preferredHeight: 28
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

            // 搴曢儴鎿嶄綔鎸夐挳
            RowLayout {
                Layout.fillWidth: true; spacing: 15
                Item { Layout.fillWidth: true }
                Button {
                    text: "鍙栨秷"; Layout.preferredWidth: 90; Layout.preferredHeight: 36
                    background: Rectangle { color: "transparent"; border.color: root.borderColor; border.width: 1; radius: 4 }
                    contentItem: Text { text: parent.text; color: root.textMuted; font.pixelSize: 14; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                    onClicked: algoConfigPopup.close()
                }
                Button {
                    text: root.pendingEditIndex === -1 ? "纭娉ㄥ唽" : "淇濆瓨淇敼"
                    Layout.preferredWidth: 140; Layout.preferredHeight: 36
                    background: Rectangle { color: root.devAccentColor; radius: 4 }
                    contentItem: Text { text: parent.text; color: root.bgDark; font.bold: true; font.pixelSize: 14; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                    onClicked: {
                        if (inputAlgoName.text.trim() === "" || inputScriptPath.text.trim() === "") {
                            root.showToast("鈿狅笍 鎻掍欢鍚嶇О鍜岃矾寰勪笉鑳戒负绌?)
                            return
                        }
                        // 鏀堕泦鍙傛暟锛堝惈瀹屾暣鍏冩暟鎹級
                        var pArray = []
                        for(var i=0; i<editingParamsModel.count; i++) {
                            var m = editingParamsModel.get(i)
                            var ptype = root.normalizeParamType(m.type)
                            if (!root.validateParamValue(m.v, ptype)) {
                                root.showToast("参数 " + (m.label || m.n || "") + " 的默认值不符合 " + ptype + " 类型")
                                return
                            }
                            pArray.push({
                                "n": m.n, "label": m.label, "v": m.v, "type": ptype,
                                "min": m.min || "", "max": m.max || "",
                                "options": m.options || "", "desc": m.desc || ""
                            })
                        }
                        var pJsonStr = JSON.stringify(pArray)

                        var payload = root.buildAlgorithmPayload(pJsonStr)
                        var inputPath = inputScriptPath.text.trim()
                        var currentData = root.pendingEditIndex === -1 ? null : algoListModel.get(root.pendingEditIndex)
                        var isScriptPlugin = root.pendingEditIndex === -1 || root.isScriptPath(inputPath) || (currentData && currentData.scriptPath !== "")

                        if (isScriptPlugin) {
                            var importResult = backendService.importPluginFile(inputPath)
                            if (!importResult.ok) {
                                root.showToast("鈿狅笍 鏂囦欢澶嶅埗澶辫触: " + (importResult.message || "鏈煡閿欒"))
                                return
                            }
                            payload.script_path = importResult.path
                            payload.module_path = ""
                        } else {
                            payload.module_path = inputPath
                            payload.script_path = ""
                        }

                        var result = root.pendingEditIndex === -1
                            ? backendService.createAlgorithm(payload)
                            : backendService.updateAlgorithm(algoListModel.get(root.pendingEditIndex).id, payload)
                        if (root.pendingEditIndex === -1) {
                            if (result && result.ok) root.showToast("鉁?鏂版彃浠跺紩鎿庡凡鎺ュ叆")
                            else root.showToast("鈿狅笍 鎻掍欢娉ㄥ唽澶辫触: " + ((result && result.message) ? result.message : "鏈煡閿欒"))
                        } else {
                            if (result && result.ok) root.showToast("鉁?搴曞眰閰嶇疆宸叉洿鏂?)
                            else root.showToast("鈿狅笍 閰嶇疆淇濆瓨澶辫触: " + ((result && result.message) ? result.message : "鏈煡閿欒"))
                        }
                        if (result && result.ok) {
                            root.loadAlgorithms()
                            algoConfigPopup.close()
                        }
                    }
                }
            }
        }
    }


    // ========================================================================
    // ======================== 鍏ㄦ柊鐣岄潰涓讳綋锛歁aster-Detail 鎺у埗鍙?================
    // ========================================================================
    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 20
        spacing: 20

        // 椤舵爮鏍忥細鎺у埗鍙?Header
        RowLayout {
            Layout.fillWidth: true
            spacing: 15

            Rectangle { width: 4; height: 24; color: root.devAccentColor; radius: 2 }

            Label {
                text: "绠楁硶寮曟搸涓庝簩娆℃彃浠舵帶鍒跺彴"
                font.pixelSize: 22
                font.bold: true
                color: root.textColor
            }

            Item { Layout.fillWidth: true }

            Button {
                text: "鎻掍欢瑙勮寖"
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
                    var result = backendService.getAlgorithmPluginSpecUrl()
                    if (result && result.status === "success") {
                        root.pluginSpecPdfSource = result.url
                        pluginSpecPopup.open()
                    } else {
                        root.showToast("\u26a0\ufe0f " + ((result && result.message) ? result.message : "\u63d2\u4ef6\u89c4\u8303\u52a0\u8f7d\u5931\u8d25"))
                    }
                }
            }

            Button {
                text: "+ 娉ㄥ唽鏂版彃浠剁幆澧?
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

        // ================= Master-Detail 宸﹀彸鍒嗘爮鏍稿績 =================
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 20

            // ---------------- 宸︿晶 (Master)锛氬垎绫绘姌鍙犵畻娉曞垪琛?----------------
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
                    text: "鏆傛棤鑷畾涔夌畻娉曟敞鍐?
                    color: root.textMuted
                    font.pixelSize: 14
                    visible: algoListModel.count === 0
                }

                Flickable {
                    id: algoListFlickable
                    anchors.fill: parent
                    contentHeight: Math.max(sectionColumn.implicitHeight, 96 + root.totalAlgoCount * 68 + 200)
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    visible: algoListModel.count > 0

                    ScrollBar.vertical: ScrollBar {
                        policy: ScrollBar.AlwaysOn
                        interactive: true
                    }

                    ColumnLayout {
                        id: sectionColumn
                        width: parent.width - 12
                        spacing: 0

                        // ---- 缁熻姒傝 ----
                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 96
                            color: Qt.rgba(29/255, 78/255, 216/255, 0.06)

                            ComboBox {
                                id: algoCategoryFilterCombo
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.top: parent.top
                                anchors.leftMargin: 10
                                anchors.rightMargin: 10
                                anchors.topMargin: 10
                                height: 32
                                model: ["鍏ㄩ儴绠楁硶", "娓呮礂绠楁硶", "鐢熸垚绠楁硶", "璇勪及绠楁硶", "璁粌绠楁硶"]
                                currentIndex: Math.max(0, model.indexOf(root.algoCategoryFilter))
                                background: Rectangle { color: root.bgDark; border.color: root.borderColor; border.width: 1; radius: 4 }
                                contentItem: Text { text: algoCategoryFilterCombo.currentText; color: root.textColor; font.pixelSize: 12; verticalAlignment: Text.AlignVCenter; leftPadding: 10 }
                                popup: Popup {
                                    y: algoCategoryFilterCombo.height + 2; width: algoCategoryFilterCombo.width; padding: 3
                                    background: Rectangle { color: root.panelBg; border.color: root.borderColor; radius: 6 }
                                    contentItem: ListView { clip: true; implicitHeight: contentHeight; model: algoCategoryFilterCombo.delegateModel }
                                }
                                delegate: ItemDelegate {
                                    width: algoCategoryFilterCombo.width - 6; height: 28
                                    contentItem: Text { text: modelData; color: root.textColor; font.pixelSize: 12; verticalAlignment: Text.AlignVCenter; leftPadding: 10 }
                                    background: Rectangle { color: hovered ? root.tableHoverBg : "transparent"; radius: 3 }
                                }
                                onActivated: root.applyAlgoCategoryFilter(currentText)
                            }

                            RowLayout {
                                anchors.horizontalCenter: parent.horizontalCenter
                                anchors.bottom: parent.bottom
                                anchors.bottomMargin: 11
                                spacing: 16
                                Text {
                                    text: "鎬昏 " + root.totalAlgoCount
                                    color: root.textColor; font.pixelSize: 13; font.bold: true
                                }
                                Rectangle { width: 1; height: 14; color: root.borderColor }
                                Rectangle {
                                    Layout.preferredWidth: Math.max(22, cleanStatText.implicitWidth + 10)
                                    Layout.preferredHeight: 18; radius: 9
                                    color: Qt.rgba(47/255, 133/255, 90/255, 0.15)
                                    Text { id: cleanStatText; anchors.centerIn: parent; text: "娓?" + root.cleaningCount; color: root.cleanTagColor; font.pixelSize: 10; font.bold: true }
                                }
                                Rectangle {
                                    Layout.preferredWidth: Math.max(22, genStatText.implicitWidth + 10)
                                    Layout.preferredHeight: 18; radius: 9
                                    color: Qt.rgba(194/255, 125/255, 14/255, 0.15)
                                    Text { id: genStatText; anchors.centerIn: parent; text: "鐢?" + root.generationCount; color: root.genTagColor; font.pixelSize: 10; font.bold: true }
                                }
                                Rectangle {
                                    Layout.preferredWidth: Math.max(22, evalStatText.implicitWidth + 10)
                                    Layout.preferredHeight: 18; radius: 9
                                    color: Qt.rgba(29/255, 78/255, 216/255, 0.15)
                                    Text { id: evalStatText; anchors.centerIn: parent; text: "璇?" + root.evaluationCount; color: root.devAccentColor; font.pixelSize: 10; font.bold: true }
                                }
                                Rectangle {
                                    Layout.preferredWidth: Math.max(22, trainStatText.implicitWidth + 10)
                                    Layout.preferredHeight: 18; radius: 9
                                    color: Qt.rgba(180/255, 83/255, 9/255, 0.15)
                                    Text { id: trainStatText; anchors.centerIn: parent; text: "璁?" + root.trainingCount; color: root.genTagColor; font.pixelSize: 10; font.bold: true }
                                }
                            }
                        }

                            Rectangle { Layout.fillWidth: true; height: 1; color: root.borderColor }

                        // ===== 娓呮礂绠楁硶 =====
                        Rectangle {
                            visible: root.showCategorySection("娓呮礂绠楁硶")
                            Layout.fillWidth: true; height: 38
                            color: root.cleaningExpanded ? Qt.rgba(47/255, 133/255, 90/255, 0.04) : "transparent"
                            MouseArea {
                                anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                                onClicked: root.cleaningExpanded = !root.cleaningExpanded
                            }
                            RowLayout {
                                anchors.fill: parent; anchors.leftMargin: 12; anchors.rightMargin: 12; spacing: 8
                                Text {
                                    text: root.cleaningExpanded ? "鈻? : "鈻?
                                    color: root.cleanTagColor; font.pixelSize: 10; Layout.preferredWidth: 14
                                }
                                Text {
                                    text: "娓呮礂绠楁硶"; color: root.textColor; font.pixelSize: 13; font.bold: true
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
                            visible: root.showCategorySection("娓呮礂绠楁硶") && root.cleaningExpanded
                            Layout.fillWidth: true
                            Repeater {
                                model: cleaningAlgoModel
                                delegate: algoItemDelegate
                            }
                        }
                        Rectangle { visible: root.showCategorySection("娓呮礂绠楁硶"); Layout.fillWidth: true; height: 1; color: root.borderColor }

                        // ===== 鐢熸垚绠楁硶 =====
                        Rectangle {
                            visible: root.showCategorySection("鐢熸垚绠楁硶")
                            Layout.fillWidth: true; height: 38
                            color: root.generationExpanded ? Qt.rgba(194/255, 125/255, 14/255, 0.04) : "transparent"
                            MouseArea {
                                anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                                onClicked: root.generationExpanded = !root.generationExpanded
                            }
                            RowLayout {
                                anchors.fill: parent; anchors.leftMargin: 12; anchors.rightMargin: 12; spacing: 8
                                Text {
                                    text: root.generationExpanded ? "鈻? : "鈻?
                                    color: root.genTagColor; font.pixelSize: 10; Layout.preferredWidth: 14
                                }
                                Text {
                                    text: "鐢熸垚绠楁硶"; color: root.textColor; font.pixelSize: 13; font.bold: true
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
                            visible: root.showCategorySection("鐢熸垚绠楁硶") && root.generationExpanded
                            Layout.fillWidth: true
                            Repeater {
                                model: generationAlgoModel
                                delegate: algoItemDelegate
                            }
                        }
                        Rectangle { visible: root.showCategorySection("鐢熸垚绠楁硶"); Layout.fillWidth: true; height: 1; color: root.borderColor }

                        // ===== 璇勪及绠楁硶 =====
                        Rectangle {
                            visible: root.showCategorySection("璇勪及绠楁硶")
                            Layout.fillWidth: true; height: 38
                            color: root.evaluationExpanded ? Qt.rgba(29/255, 78/255, 216/255, 0.04) : "transparent"
                            MouseArea {
                                anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                                onClicked: root.evaluationExpanded = !root.evaluationExpanded
                            }
                            RowLayout {
                                anchors.fill: parent; anchors.leftMargin: 12; anchors.rightMargin: 12; spacing: 8
                                Text {
                                    text: root.evaluationExpanded ? "鈻? : "鈻?
                                    color: root.devAccentColor; font.pixelSize: 10; Layout.preferredWidth: 14
                                }
                                Text {
                                    text: "璇勪及绠楁硶"; color: root.textColor; font.pixelSize: 13; font.bold: true
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
                            visible: root.showCategorySection("璇勪及绠楁硶") && root.evaluationExpanded
                            Layout.fillWidth: true
                            Repeater {
                                model: evaluationAlgoModel
                                delegate: algoItemDelegate
                            }
                        }
                        Rectangle { visible: root.showCategorySection("璇勪及绠楁硶"); Layout.fillWidth: true; height: 1; color: root.borderColor }

                        // ===== 璁粌绠楁硶 =====
                        Rectangle {
                            visible: root.showCategorySection("璁粌绠楁硶")
                            Layout.fillWidth: true; height: 38
                            color: root.trainingExpanded ? Qt.rgba(180/255, 83/255, 9/255, 0.04) : "transparent"
                            MouseArea {
                                anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                                onClicked: root.trainingExpanded = !root.trainingExpanded
                            }
                            RowLayout {
                                anchors.fill: parent; anchors.leftMargin: 12; anchors.rightMargin: 12; spacing: 8
                                Text {
                                    text: root.trainingExpanded ? "鈻? : "鈻?
                                    color: root.genTagColor; font.pixelSize: 10; Layout.preferredWidth: 14
                                }
                                Text {
                                    text: "璁粌绠楁硶"; color: root.textColor; font.pixelSize: 13; font.bold: true
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
                            visible: root.showCategorySection("璁粌绠楁硶") && root.trainingExpanded
                            Layout.fillWidth: true
                            Repeater {
                                model: trainingAlgoModel
                                delegate: algoItemDelegate
                            }
                        }
                    }
                }
            }

            // ---------------- 鍙充晶 (Detail)锛氭彃浠惰鎯呴厤缃彴 ----------------
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
                    text: "璇峰湪宸︿晶閫夋嫨鎴栨敞鍐屾柊绠楁硶鎻掍欢"
                    color: root.textMuted
                    font.pixelSize: 16
                    visible: root.selectedAlgoIndex === -1
                }

                // 璇︽儏闈㈡澘涓讳綋
                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 25
                    spacing: 20
                    visible: root.selectedAlgoIndex !== -1

                    // 1. 椤堕儴 Header
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
                                    if (c === "娓呮礂绠楁硶") return root.cleanTagColor
                                    if (c === "鐢熸垚绠楁硶") return root.genTagColor
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

                        // 鎿嶄綔鎸夐挳缁?(宸蹭慨澶?color 灞炴€ч噸澶嶈缃鑷寸殑鎶ラ敊闂)
                        RowLayout {
                            spacing: 10
                            Button {
                                text: "鉁忥笍 璋冨弬淇敼"
                                Layout.preferredHeight: 32
                                background: Rectangle { border.color: root.borderColor; border.width: 1; radius: 4; color: parent.hovered ? root.tableHoverBg : "transparent" }
                                contentItem: Text { text: parent.text; color: root.textColor; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                                onClicked: {
                                    if(root.selectedAlgoIndex === -1) return;
                                    var idx = root.selectedAlgoIndex;
                                    var modelData = algoListModel.get(idx);

                                    root.pendingEditIndex = idx;
                                    inputAlgoName.text = modelData.name;
                                    if (modelData.category === "娓呮礂绠楁硶") inputCategory.currentIndex = 0
                                    else if (modelData.category === "鐢熸垚绠楁硶") inputCategory.currentIndex = 1
                                    else if (modelData.category === "璁粌绠楁硶") inputCategory.currentIndex = 2
                                    else inputCategory.currentIndex = 3

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
                                text: "馃棏锔?鍗歌浇鐜"
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

                    // 2. 鑴氭湰鏄犲皠灞曠ず
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        Text { text: "鑴氭湰鐗╃悊鎸傝浇璺緞 (Target Script)"; color: root.devAccentMuted; font.pixelSize: 12; font.family: "Courier"; font.bold: true }
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

                    // 3. 鎻忚堪
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        Text { text: "鎺ュ彛绠€杩?; color: root.textMuted; font.pixelSize: 12; font.bold: true }
                        Text {
                            text: root.selectedAlgoField("desc")
                            color: root.textColor; font.pixelSize: 14; wrapMode: Text.WordWrap; Layout.fillWidth: true; lineHeight: 1.4
                        }
                    }

                    // 4. 绠楁硶浣跨敤璇存槑
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        Text { text: "绠楁硶浣跨敤璇存槑"; color: root.primaryColor; font.pixelSize: 13; font.bold: true }
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
                            text: "瀹屾暣鏂囨。: docs/ALGORITHM_USAGE_GUIDE.md"
                            color: root.textMuted
                            font.pixelSize: 12
                        }
                    }

                    // 4.5 鍏宠仈璇勪及绠楁硶锛堜粎璁粌绠楁硶鍙锛?
                    ColumnLayout {
                        Layout.fillWidth: true; spacing: 8
                        visible: root.selectedAlgoField("category") === "璁粌绠楁硶"
                        Text { text: "鍏宠仈璇勪及绠楁硶"; color: root.devAccentColor; font.pixelSize: 13; font.bold: true }
                        RowLayout {
                            Layout.fillWidth: true; spacing: 10
                            ComboBox {
                                id: bindingEvalCombo
                                Layout.fillWidth: true; Layout.preferredHeight: 32
                                model: bindingEvalModel; textRole: "display"; valueRole: "key"
                                background: Rectangle { color: root.bgDark; border.color: root.borderColor; border.width: 1; radius: 4 }
                                contentItem: Text { text: bindingEvalCombo.currentText; color: root.textColor; font.pixelSize: 12; verticalAlignment: Text.AlignVCenter; leftPadding: 10 }
                                popup: Popup {
                                    y: bindingEvalCombo.height + 2; width: bindingEvalCombo.width; padding: 3
                                    background: Rectangle { color: root.panelBg; border.color: root.borderColor; radius: 6 }
                                    contentItem: ListView { clip: true; implicitHeight: contentHeight; model: bindingEvalCombo.delegateModel }
                                }
                                delegate: ItemDelegate {
                                    width: bindingEvalCombo.width - 6; height: 28
                                    contentItem: Text { text: model.display; color: root.textColor; font.pixelSize: 12; verticalAlignment: Text.AlignVCenter; leftPadding: 10 }
                                    background: Rectangle { color: hovered ? root.tableHoverBg : "transparent"; radius: 3 }
                                }
                            }
                            Button {
                                text: "淇濆瓨缁戝畾"; Layout.preferredHeight: 32
                                background: Rectangle { color: root.devAccentColor; radius: 4 }
                                contentItem: Text { text: parent.text; color: "white"; font.pixelSize: 12; font.bold: true; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                                onClicked: {
                                    var result = backendService.saveAlgorithmBinding(root.selectedAlgoField("key"), bindingEvalCombo.currentValue || "")
                                    if (result && result.ok) {
                                        root.showToast("鉁?缁戝畾宸蹭繚瀛?)
                                        var idx = root.selectedAlgoIndex
                                        if (idx >= 0) { algoListModel.setProperty(idx, "boundEvalKey", bindingEvalCombo.currentValue || ""); algoListModel.setProperty(idx, "boundEvalName", bindingEvalCombo.currentText || "") }
                                    } else root.showToast("鈿狅笍 缁戝畾澶辫触")
                                }
                            }
                        }
                    }

                    // 5. 瑙ｆ瀽骞跺睍绀哄姩鎬?JSON 鍙傛暟
                    ColumnLayout {
                        Layout.fillWidth: true; Layout.fillHeight: true; spacing: 8
                        Text { text: "鍔ㄦ€佸弽灏勫弬鏁板揩鐓?(Read-Only)"; color: root.devAccentColor; font.pixelSize: 12; font.family: "Courier"; font.bold: true }

                        Rectangle {
                            Layout.fillWidth: true; Layout.fillHeight: true; color: root.bgDark; border.color: root.borderColor; border.width: 1; radius: 6; clip: true

                            Flickable {
                                anchors.fill: parent; anchors.margins: 15; contentHeight: paramText.contentHeight; clip: true
                                Text {
                                    id: paramText
                                    color: root.textColor; font.family: "Courier"; font.pixelSize: 14; lineHeight: 1.5
                                    text: {
                                        var rawParams = root.selectedAlgoField("paramsJson")
                                        if(!rawParams) return "[]\n// 鏃犵幆澧冨弬鏁颁紶鍏?;
                                        try {
                                            var arr = JSON.parse(rawParams);
                                            if(arr.length === 0) return "[]\n// 鏃犵幆澧冨弬鏁颁紶鍏?;
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



