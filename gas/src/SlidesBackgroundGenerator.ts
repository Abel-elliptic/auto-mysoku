/**
 * Slidesの1ページを画像としてエクスポートし、Driveへ保存する共通関数。
 *
 * 実際にスライドを複製し、部屋の文字情報（建物名・賃料等）を埋め込む処理は
 * RentalDataLookup.ts の updateSlideWithData() が担当する（既存の本番運用中
 * ロジックをそのまま再利用しているため、このファイルでは新たにスライドを
 * 複製・生成する処理は持たない）。updateSlideWithData() は文字埋め込みが
 * 終わったスライドをこの exportSlidePageAsImage() に渡し、画像化してもらう。
 *
 * 重要な技術的制約（docs/architecture.md参照）:
 * Slides API `Presentations.Pages.getThumbnail` はページを画像化する公式手段だが、
 * `thumbnailProperties.thumbnailSize` で指定できる解像度には上限があり、
 * A3印刷相当（長辺 約4961px @300dpi）に対して不足する可能性がある。
 * 正確な上限値は断定せず、このメソッドが取得のたびに実際のサムネイル寸法を
 * ログ出力する運用とする。
 *
 * なお、既存のupdateSlideWithData()は建物名・賃料等の実際に読める必要がある
 * 文字情報をこのスライド自体に焼き込んでからエクスポートするため、この解像度
 * 上限は「印刷物として読める文字の鮮明さ」に直接影響する（背景デザインだけの
 * 問題ではない）。初回のエンドツーエンド確認では、この点を重点的に目視確認すること。
 */

function exportSlidePageAsImage(presentationId: string, pageObjectId: string): string {
  const thumbnail = Slides.Presentations!.Pages!.getThumbnail(presentationId, pageObjectId, {
    "thumbnailProperties.thumbnailSize": "LARGE",
    "thumbnailProperties.mimeType": "PNG",
  });

  if (!thumbnail.contentUrl) {
    throw new Error("Slidesサムネイルの取得に失敗しました（contentUrlが空）。");
  }

  // Slides `ThumbnailSize=LARGE` の実際の上限ピクセル数は断定せず、取得のたびに
  // 実測値をログ出力する（docs/architecture.md「Google Slides背景生成の技術的制約」参照）。
  console.log(
    `Slidesサムネイル実測サイズ: width=${thumbnail.width ?? "unknown"}px, height=${thumbnail.height ?? "unknown"}px (pageObjectId=${pageObjectId})`
  );

  const response = UrlFetchApp.fetch(thumbnail.contentUrl, {
    headers: { Authorization: `Bearer ${ScriptApp.getOAuthToken()}` },
  });
  const blob = response.getBlob().setName(`background_${pageObjectId}.png`);

  const folderId = getScriptProperty(SCRIPT_PROPERTY_KEYS.BACKGROUND_DRIVE_FOLDER_ID);
  const folder = DriveApp.getFolderById(folderId);
  const file = folder.createFile(blob);
  return file.getId();
}
