/**
 * レイアウト情報取得用ツール。
 *
 * Slidesページ上に仮配置したプレースホルダー要素（画像・図形・テキストボックス）の
 * transform / size を Slides API から取得し、「レイアウト情報」シートへ出力する。
 * 手作業のCanvaレイアウトを数値化し、templates/*.yaml の座標値を決める材料にする。
 *
 * 使い方: 対象のSlidesファイルを開いた状態でこのメニューを実行するか、
 * Script Propertiesで対象ファイルIDを指定する（要確認: 運用フロー）。
 */

function captureLayoutFromActivePresentation(): void {
  const ui = SpreadsheetApp.getUi();
  const templateType = ui.prompt("テンプレート種別を入力してください (in_house / itandi / general)").getResponseText();
  const fileId = ui.prompt("対象のSlidesファイルIDを入力してください").getResponseText();

  const presentationId = fileId;
  const rows: LayoutCaptureRow[] = [];

  const presentation = Slides.Presentations!.get(presentationId);
  const pageSize = presentation.pageSize;

  (presentation.slides || []).forEach((slide) => {
    (slide.pageElements || []).forEach((element) => {
      const decomposed = decomposeTransform(element);
      rows.push({
        templateType,
        slidePageId: slide.objectId || "",
        elementName: element.title || element.objectId || "",
        elementType: classifyElementType(element),
        xEmu: decomposed.x,
        yEmu: decomposed.y,
        widthEmu: decomposed.width,
        heightEmu: decomposed.height,
        rotationDeg: decomposed.rotationDeg,
        pageWidthEmu: pageSize?.width?.magnitude || 0,
        pageHeightEmu: pageSize?.height?.magnitude || 0,
      });
    });
  });

  appendLayoutRows(rows);
  ui.alert(`${rows.length}件のレイアウト情報を取得しました。`);
}

/**
 * PageElementの種別をIMAGE/TEXT/SHAPEに分類する。
 *
 * 注意: Slides APIではテキストボックスも `element.shape`（shapeType="TEXT_BOX"）として
 * 表現され、`element.shape` の有無だけで判定すると全てのテキストボックスが
 * SHAPE扱いになってしまう（TEXTに一致するケースが実質存在しなくなる）。
 * そのため image を先に判定し、shapeはさらに shapeType で TEXT_BOX かどうかを見る。
 */
function classifyElementType(element: GoogleAppsScript.Slides.Schema.PageElement): "IMAGE" | "TEXT" | "SHAPE" {
  if (element.image) return "IMAGE";
  if (element.shape) {
    return element.shape.shapeType === "TEXT_BOX" ? "TEXT" : "SHAPE";
  }
  return "SHAPE";
}

/**
 * PageElementのtransform（アフィン変換行列）とsizeから、
 * x, y, width, height, rotation を算出する。
 *
 * Slides APIの座標系はEMU (English Metric Units, 1pt = 12700 EMU)。
 * transformは [scaleX, shearX, translateX; shearY, scaleY, translateY] の形。
 */
function decomposeTransform(element: GoogleAppsScript.Slides.Schema.PageElement): {
  x: number;
  y: number;
  width: number;
  height: number;
  rotationDeg: number;
} {
  const transform = element.transform;
  const size = element.size;

  const scaleX = transform?.scaleX ?? 1;
  const scaleY = transform?.scaleY ?? 1;
  const shearX = transform?.shearX ?? 0;
  const shearY = transform?.shearY ?? 0;
  const translateX = transform?.translateX ?? 0;
  const translateY = transform?.translateY ?? 0;

  const widthEmu = (size?.width?.magnitude ?? 0) * scaleX;
  const heightEmu = (size?.height?.magnitude ?? 0) * scaleY;

  // 回転角はscaleとshearから算出（せん断がない単純な回転の場合の近似）。
  const rotationRad = Math.atan2(shearY, scaleX);
  const rotationDeg = (rotationRad * 180) / Math.PI;

  return {
    x: translateX,
    y: translateY,
    width: widthEmu,
    height: heightEmu,
    rotationDeg,
  };
}
