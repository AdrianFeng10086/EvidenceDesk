/**
 * 纯文本 / Markdown 没有 PDF 页码。证据定位展示段落序号与行范围，
 * 不把 page = 1 伪装成 PDF 页码。
 */
export interface LineRange {
  startLine: number;
  endLine: number;
}

export function lineRangeAt(text: string, charStart: number, charEnd: number): LineRange {
  const length = text.length;
  const start = Math.min(Math.max(charStart, 0), length);
  const end = Math.min(Math.max(charEnd, start), length);
  const endProbe = end > start ? end - 1 : start;

  return {
    startLine: countNewlines(text.slice(0, start)) + 1,
    endLine: countNewlines(text.slice(0, endProbe)) + 1,
  };
}

export function formatLineRange(range: LineRange): string {
  return range.startLine === range.endLine
    ? `第 ${range.startLine} 行`
    : `第 ${range.startLine}–${range.endLine} 行`;
}

function countNewlines(value: string): number {
  let count = 0;
  for (let index = 0; index < value.length; index += 1) {
    if (value[index] === '\n') count += 1;
  }
  return count;
}
