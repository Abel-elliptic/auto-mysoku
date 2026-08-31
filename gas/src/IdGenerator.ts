/**
 * バッチID (JOB-YYYYMMDD-NNNN) の採番。
 *
 * 同日中に「マイソク作成」が複数回・ほぼ同時に実行されるとNNNNが重複しうるため、
 * LockService.getScriptLock() で採番処理のみを排他制御する
 * （ジョブ行の書き込みそのものはロックの外で行い、ロック保持時間を短く保つ）。
 */

function nextBatchId(jobSheet: GoogleAppsScript.Spreadsheet.Sheet): string {
  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    const today = Utilities.formatDate(new Date(), "Asia/Tokyo", "yyyyMMdd");
    const prefix = `JOB-${today}-`;

    const values = jobSheet.getDataRange().getValues();
    const batchIdColIndex = JOB_COLUMNS.indexOf("batch_id");

    let maxSeq = 0;
    for (let i = 1; i < values.length; i++) {
      const batchId = String(values[i][batchIdColIndex] || "");
      if (batchId.startsWith(prefix)) {
        const seq = parseInt(batchId.substring(prefix.length), 10);
        if (!isNaN(seq) && seq > maxSeq) {
          maxSeq = seq;
        }
      }
    }

    const nextSeq = maxSeq + 1;
    return `${prefix}${String(nextSeq).padStart(4, "0")}`;
  } finally {
    lock.releaseLock();
  }
}
