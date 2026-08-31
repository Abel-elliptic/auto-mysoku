/**
 * 実際に本番運用中のGASコードを移植したファイル。
 *
 * processNewRentals() / updateSlideWithData() / getBuildingInfo() /
 * formatCurrency() は、建物ごとの固定値・料金計算等のビジネスロジックを
 * 一切変更せずそのまま移植している（間違って「直した」つもりで数値や
 * 判定条件を変えないこと）。
 *
 * このファイルで新たに追加したのは updateSlideWithData() の末尾のみ:
 * 文字埋め込みが終わったスライドを画像としてエクスポートしてDriveへ保存し、
 * 「ジョブ管理」シートへ1行追記する処理（社内PC側Pythonが後で拾って写真を
 * 合成するためのジョブ）。
 *
 * 移植前の元コードは、`new Date().getTime()`ベースのファイル名でスライドを
 * 複製する代わりに、既存の共有Slidesファイル（自社/一般の2種類）の1枚目を
 * duplicate()して末尾に追加していく方式だった点に注意
 * （SlidesBackgroundGenerator.tsの旧実装＝ファイルごとコピーする方式とは異なる）。
 */

function requireSheetIn(
  ss: GoogleAppsScript.Spreadsheet.Spreadsheet,
  name: string
): GoogleAppsScript.Spreadsheet.Sheet {
  const sheet = ss.getSheetByName(name);
  if (!sheet) {
    throw new Error(`シートが見つかりません: ${name}`);
  }
  return sheet;
}

function processNewRentals(is_own = false, batchId?: string): void {
  const ss = SpreadsheetApp.openById("1BPLLSSIM37C7aA-zuQydf_RkyFxA9wEfz_Yix2mixk0");

  // 元コードどおり、アクティブなスプレッドシートではなく明示的にIDで開いた
  // ssから取得する（SheetsRepository.tsのgetSheetByName()はgetActiveSpreadsheet()
  // を見に行くため、別スプレッドシートを参照してしまう可能性がありここでは使わない）。
  const sheetNew = requireSheetIn(ss, SHEET_NAMES.RENTAL_MANAGEMENT);
  const sheetItandi = requireSheetIn(ss, SHEET_NAMES.ITANDI);
  const sheetNyutaikyo = requireSheetIn(ss, SHEET_NAMES.MOVE_IN_OUT);
  const sheetParking = requireSheetIn(ss, SHEET_NAMES.PARKING);

  const dataNew = sheetNew.getDataRange().getValues();
  const dataItandi = sheetItandi.getDataRange().getValues();
  const dataNyutaikyo = sheetNyutaikyo.getDataRange().getValues();
  const dataParking = sheetParking.getDataRange().getValues();

  // ヘッダーを除いて2行目から処理
  for (let i = 1; i < dataNew.length; i++) {
    let parking = "「駐車場価格設定」を見直して";
    let additional = "";
    const row = dataNew[i];
    const isChecked = row[9]; // J列チェックボックス
    if (isChecked !== true) continue;

    const buildingName = row[1]; // B列 建物名
    const roomNumber = row[2]; // C列 部屋番号
    const rent = row[3]; // D列 家賃
    const managementFee = row[4]; // E列 管理費
    const shikikin = row[7]; // H列 敷金
    const reikin = row[8]; // I列 礼金

    const searchName = buildingName.startsWith("ニューノース") ? "ニューノース" : buildingName;
    if (!["ファーストシティ", "バンブーヴィレッジ"].includes(buildingName)) {
      for (let j = 1; j < dataParking.length; j++) {
        const parkingBuildingName = String(dataParking[j][8] || "").trim(); // I列
        const parkingValue = dataParking[j][10]; // K列
        if (parkingBuildingName === searchName) {
          parking = parkingValue;
          break;
        }
      }
    }
    if (buildingName == "ファーストシティ") {
      parking = "２台可能０円";
    }
    if (buildingName == "ニューノース参番館") {
      additional = "※道路拡幅工事により退去交渉がはいります。時期未定";
    }

    // ITANDIシートから対応する行を検索
    const itandiRow = dataItandi.find((r) => r[0] === buildingName && r[2] == roomNumber);
    let address = "",
      area: number | string = "",
      madori = "",
      remarks = "";
    let bike: number | string = "",
      bicycle: number | string = "";
    if (itandiRow) {
      address = itandiRow[7]; // H列 所在地
      area = itandiRow[4]; // E列 専有面積
      madori = itandiRow[23]; // X列 間取り
      remarks = itandiRow[38]; // AM列 備考
      bike = itandiRow[26]; // AA列 バイク置場
      bicycle = itandiRow[27]; // AB列 駐輪場
    } else if (buildingName == "バンブーヴィレッジ") {
      address = "東京都立川市上砂町1-3-6";
      area = 108.9;
      madori = "5LDK";
      parking = "２台可能０円";
      bike = "０円";
      bicycle = "０円";
    }
    remarks += "/外国籍のみの場合敷金1ヶ月追加";

    // 入退去管理シートから最新の解約申請データを検索
    const targetRows = dataNyutaikyo.filter(
      (r) => r[3] === buildingName && r[4] == roomNumber && r[2] === "解約申請"
    );
    let moveInDate = "";
    let isReady = false;
    if (targetRows.length > 0) {
      targetRows.sort((a, b) => new Date(b[1]).getTime() - new Date(a[1]).getTime()); // B列の日付が新しい順
      const latest = targetRows[0];
      const leaveDate = new Date(latest[11]); // L列 退去予定日

      // 退去予定日の1週間後以降の最初の土曜日を探す
      const candidate = new Date(leaveDate);
      candidate.setDate(candidate.getDate() + 7);
      while (candidate.getDay() !== 6) {
        // 土曜日は6
        candidate.setDate(candidate.getDate() + 1);
      }
      // フォーマットして代入
      moveInDate = Utilities.formatDate(candidate, "Asia/Tokyo", "yyyy年M月d日");
      const today = new Date();
      isReady = candidate <= today;
    }
    // 入居可能日が空なら「即入居可」にする
    if (!moveInDate || isReady) {
      moveInDate = "即入居可";
    }

    // 建物別情報を取得
    const { structureAndFloors, keyExchange, oldKey, train, builtYear, facilities } = getBuildingInfo(
      buildingName,
      madori,
      roomNumber
    );

    // rowData を作る
    const rowData: RentalRowData = {
      buildingName,
      roomNumber,
      madori,
      address,
      area,
      structureAndFloors,
      moveInDate,
      rent,
      managementFee,
      shikikin,
      reikin,
      keyExchange,
      oldKey,
      parking,
      bike,
      bicycle,
      facilities,
      remarks,
      train,
      builtYear,
      additional,
    };

    // スライドに反映
    updateSlideWithData(rowData, is_own, batchId);
  }
}

/**
 * 旧来の呼び出し名の後方互換用（既存のトリガー等がこの関数名を参照している
 * 可能性があるため残す）。batchIdを渡さないため、ジョブ管理シートへの連携は
 * 行わずスライド作成のみを行う（updateSlideWithData()のbatchId省略時の挙動）。
 * ジョブ管理と連携した一括生成には Menu.ts の「マイソク作成」(createFlyerBatch)
 * を使うこと。
 */
function processNewRentalsForOwn(): void {
  processNewRentals(true);
}

interface RentalRowData {
  buildingName: string;
  roomNumber: string;
  madori: string;
  address: string;
  area: number | string;
  structureAndFloors: string;
  moveInDate: string;
  rent: number | string;
  managementFee: number | string;
  shikikin: number | string;
  reikin: number | string;
  keyExchange: number | string;
  oldKey: number | string | null;
  parking: number | string;
  bike: number | string;
  bicycle: number | string;
  facilities: string;
  remarks: string;
  train: string;
  builtYear: string;
  additional: string;
}

function updateSlideWithData(rowData: RentalRowData, is_own: boolean, batchId?: string): void {
  let slideId: string;
  if (is_own) {
    slideId = "1QB2132Hz0XMREBKmxddQTp-9S34dijgy2oUeBODyVtM";
  } else {
    slideId = "1rr3v0UMjSqMDJPjAvBveoqnj7r210nllVgyTxO22jOc";
  }
  const presentation = SlidesApp.openById(slideId);

  // 1枚目をコピーして末尾に追加
  const firstSlide = presentation.getSlides()[0];
  const newSlide = firstSlide.duplicate();
  const range = rowData.buildingName == "コートデルトゥール昭島" ? " ～" : "";
  const today = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), "yyyy/MM/dd");
  if (is_own) {
    rowData.remarks = rowData.remarks.replace("指定保証会社利用必須 重説は仲介会社で行ってください ", "");
    rowData.structureAndFloors = rowData.structureAndFloors.split("\n")[0];
  }

  // 置換マップ
  const replacements: Record<string, string> = {
    築年月日: rowData.builtYear || "",
    専有面積: Number(rowData.area).toFixed(2) + "㎡" || "",
    電車: rowData.train || "",
    建物と部屋: rowData.buildingName + " " + rowData.roomNumber,
    間取り: rowData.madori || "",
    所在地: rowData.address || "",
    構造: rowData.structureAndFloors || "",
    入居可能時期: rowData.moveInDate || "",
    賃料: formatCurrency(rowData.rent) + "円" || "",
    管理費: formatCurrency(rowData.managementFee) + "円" || "",
    敷金: rowData.shikikin + "ヶ月" || "",
    礼金: rowData.reikin + "ヶ月" || "",
    鍵交換費: formatCurrency(rowData.keyExchange) + "円" || "",
    駐車場: !isNaN(Number(rowData.parking))
      ? formatCurrency(rowData.parking) + "円" + (range || "")
      : String(rowData.parking),
    バイク置き場: formatCurrency(rowData.bike) + "円" || "",
    駐輪場: formatCurrency(rowData.bicycle) + "円" || "",
    "設備・詳細":
      rowData.facilities + (rowData.oldKey && !is_own ? " ローテーション鍵：" + formatCurrency(rowData.oldKey) + "円(税込)" : "") ||
      "",
    備考: rowData.remarks || "",
    公開日: today,
    Additional: rowData.additional,
  };

  // 置換処理
  for (const [placeholder, value] of Object.entries(replacements)) {
    newSlide.replaceAllText(placeholder, value);
  }

  // ここから新規追加: 画像化してDriveへ保存し、ジョブ管理シートへ1行追記する。
  // batchIdが渡されない（＝ジョブ管理と連携しない旧来の呼び出し方）場合は、
  // 従来どおりスライド作成のみで終了する。
  if (!batchId) return;

  const driveFileId = exportSlidePageAsImage(presentation.getId(), newSlide.getObjectId());
  const templateType: TemplateType = is_own ? "in_house" : "general";
  appendSingleJobRow({
    batchId,
    rowId: `${batchId}-${templateType}-${rowData.buildingName}-${rowData.roomNumber}`,
    buildingName: rowData.buildingName,
    roomName: String(rowData.roomNumber),
    templateType,
    backgroundRef: driveFileId,
  });
}

function formatCurrency(amount: number | string | null): string {
  if (amount == null || amount === "") return "";
  return Number(amount).toLocaleString(); // 例: 1234567 → "1,234,567"
}

// 建物ごとの固定情報を取得する関数
function getBuildingInfo(
  buildingName: string,
  madori: string,
  roomNumber: string
): {
  structureAndFloors: string;
  keyExchange: number;
  oldKey: number | null;
  train: string;
  builtYear: string;
  facilities: string;
} {
  let structureAndFloors = "";
  let keyExchange = 0;
  let oldKey: number | null = null;
  let train = "";
  let builtYear = "";
  let facilities = "";

  if (buildingName === "コートデルトゥール昭島") {
    structureAndFloors = "鉄筋コンクリート造\n地上6階建て";
    keyExchange = madori === "2SLDK" || madori === "2LDK" ? 29700 : 19800;
    oldKey = 11000;
    train = "JR青梅線東中神駅徒歩19分\n西武線武蔵砂川駅徒歩20分";
    builtYear = "2024年12月";
    facilities =
      "都市ガス 専用バス 専用トイレ バストイレ別 温水洗浄便座 おいだき機能 独立洗面台 洗面所 室内洗濯機置き場 システムキッチン カウンターキッチン コンロ3口以上 エアコン インターネット無料 オートロック モニター付きインターホン 宅配ボックス 24時間ゴミ出し可 画像の家具はイメージです";
  } else if (buildingName === "ヴェラビスタ" || buildingName === "ディアルベルジェ・エスパシオ") {
    structureAndFloors = "鉄骨造\n地上3階建て";
    keyExchange = 33000;
    train = "JR青梅線中神駅徒歩11分\nJR青梅線東中神駅徒歩13分";
    if (buildingName === "ヴェラビスタ") {
      oldKey = null;
      builtYear = "2014年2月";
    } else {
      oldKey = 16500;
      builtYear = "2009年1月";
    }
    train = "JR青梅線中神駅徒歩11分\nJR青梅線東中神駅徒歩13分";
    builtYear = buildingName === "ヴェラビスタ" ? "2014年2月" : "2009年1月";
    facilities =
      "プロパンガス 専用バス 専用トイレ バストイレ別 追い炊き機能 独立洗面台 洗面所 室内洗濯機置き場 システムキッチン カウンターキッチン コンロ3口以上 エアコン インターネット無料 モニター付きインターホン 宅配ボックス";
  } else if (buildingName === "ニューノース壱番館") {
    structureAndFloors = "鉄骨造\n地上3階建て";
    keyExchange = 33000;
    oldKey = 16500;
    train = "西武線武蔵砂川駅徒歩20分\nJR青梅線東中神駅徒歩20分";
    builtYear = "2007年3月";
    facilities =
      "プロパンガス 専用バス 専用トイレ バストイレ別 追い炊き機能 独立洗面台 洗面所 室内洗濯機置き場 システムキッチン カウンターキッチン コンロ3口以上 エアコン インターネット無料 モニター付きインターホン 宅配ボックス";
  } else if (buildingName === "ニューノース弐番館" || buildingName === "ニューノース参番館") {
    structureAndFloors = "鉄骨造\n地上3階建て";
    keyExchange = buildingName === "ニューノース弐番館" ? 33000 : 16500;
    oldKey = buildingName === "ニューノース弐番館" ? 16500 : null;
    train = "西武線武蔵砂川駅徒歩20分\nJR青梅線東中神駅徒歩20分";
    builtYear = buildingName === "ニューノース弐番館" ? "2007年7月" : "2008年2月";
    facilities =
      "プロパンガス 専用バス 専用トイレ バストイレ別 追い炊き機能 独立洗面台 洗面所 室内洗濯機置き場 システムキッチン カウンターキッチン コンロ2口以上 エアコン インターネット無料 モニター付きインターホン 宅配ボックス";
    if (buildingName == "ニューノース参番館") {
      facilities += " ミストサウナ";
    }
  } else if (buildingName === "ファーストシティ") {
    structureAndFloors = "鉄骨造\n地上2階建て";
    keyExchange = 33000;
    oldKey = 16500;
    train = "JR青梅線東中神駅徒歩25分\n西武線武蔵砂川駅徒歩22分";
    builtYear = "2011年7月";
    facilities =
      "プロパンガス 専用バス 専用トイレ バストイレ別 追い炊き機能 独立洗面台 洗面所 室内洗濯機置き場 システムキッチン カウンターキッチン コンロ2口以上 エアコン";
    if (["E-1", "C", "D"].includes(roomNumber)) {
      facilities += " 専用庭";
    }
  } else if (buildingName === "バンブーヴィレッジ") {
    structureAndFloors = "木造\n戸建て";
    keyExchange = 45000;
    oldKey = null;
    train = "JR青梅線東中神駅徒歩25分\n西武線武蔵砂川駅徒歩22分";
    builtYear = "1961年8月";
    facilities = "";
  } else {
    // その他の建物
    structureAndFloors = "鉄骨造";
    keyExchange = 33000;
    oldKey = null;
    train = "";
    builtYear = "";
    facilities = "";
  }

  return {
    structureAndFloors,
    keyExchange,
    oldKey,
    train,
    builtYear,
    facilities,
  };
}
