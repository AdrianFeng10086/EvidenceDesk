import assert from 'node:assert/strict';
import test from 'node:test';

import { formatLineRange, lineRangeAt } from './text-range.ts';

test('跨行段落返回起止行号', () => {
  const text = '第一段：申请人须为副教授。\n第一段续：并提交研究成果。\n\n第二段：截止时间为2024年11月15日。\n';
  const range = lineRangeAt(text, 0, 28);

  assert.deepEqual(range, { startLine: 1, endLine: 2 });
  assert.equal(formatLineRange(range), '第 1–2 行');
});

test('段落定位不依赖 pdf 页码', () => {
  const text = '甲\n乙\n丙\n';
  assert.deepEqual(lineRangeAt(text, 2, 3), { startLine: 2, endLine: 2 });
  assert.deepEqual(lineRangeAt(text, 4, 5), { startLine: 3, endLine: 3 });
});

test('空片段和越界偏移也不会返回非法行号', () => {
  assert.deepEqual(lineRangeAt('abc', 1, 1), { startLine: 1, endLine: 1 });
  assert.deepEqual(lineRangeAt('abc', 99, 200), { startLine: 1, endLine: 1 });
});
