import assert from 'node:assert/strict';
import test from 'node:test';

import type { BBox } from '../types/documents.ts';
import { fitScale, hasDrawableBboxes, toOverlayRect } from './coordinates.ts';

const PAGE_WIDTH = 595.92;
const PAGE_HEIGHT = 841.92;

const bbox: BBox = {
  x0: 72,
  y0: 110.25,
  x1: 320.5,
  y1: 135.75,
  page_width: PAGE_WIDTH,
  page_height: PAGE_HEIGHT,
  char_start: 0,
  char_end: 20,
};

test('75%、100%、150% 缩放保持同一相对位置', () => {
  const containerWidth = 460;
  const zooms = [0.75, 1, 1.5];

  const rects = zooms.map((zoom) => {
    const scale = fitScale(containerWidth, PAGE_WIDTH, zoom);
    const rect = toOverlayRect(bbox, scale, 0);
    assert.ok(rect);
    return { scale, rect };
  });

  for (const { scale, rect } of rects) {
    assert.ok(Math.abs(rect.left / (PAGE_WIDTH * scale) - bbox.x0 / PAGE_WIDTH) < 1e-9);
    assert.ok(Math.abs(rect.top / (PAGE_HEIGHT * scale) - bbox.y0 / PAGE_HEIGHT) < 1e-9);
    assert.ok(Math.abs(rect.width / (PAGE_WIDTH * scale) - (bbox.x1 - bbox.x0) / PAGE_WIDTH) < 1e-9);
  }

  const base = rects[1].rect;
  const small = rects[0].rect;
  const large = rects[2].rect;

  assert.ok(Math.abs(small.left - base.left * 0.75) < 1e-9);
  assert.ok(Math.abs(large.left - base.left * 1.5) < 1e-9);
  assert.ok(Math.abs(small.width - base.width * 0.75) < 1e-9);
  assert.ok(Math.abs(large.height - base.height * 1.5) < 1e-9);
});

test('面板宽度变化时按新的容器宽度重新换算', () => {
  const narrow = fitScale(320, PAGE_WIDTH, 1);
  const wide = fitScale(960, PAGE_WIDTH, 1);
  const narrowRect = toOverlayRect(bbox, narrow, 0);
  const wideRect = toOverlayRect(bbox, wide, 0);

  assert.ok(narrowRect && wideRect);
  assert.ok(wideRect.width > narrowRect.width);
  assert.ok(Math.abs(narrowRect.left / narrow - bbox.x0) < 1e-9);
  assert.ok(Math.abs(wideRect.left / wide - bbox.x0) < 1e-9);
});

test('修复前案例：左下角原点会把文字框上下镜像', () => {
  const scale = 1;
  const fixed = toOverlayRect(bbox, scale, 0);
  assert.ok(fixed);

  // 旧实现误用 PDF.js 原生左下角坐标：
  const legacyTop = (PAGE_HEIGHT - bbox.y1) * scale;

  assert.notEqual(fixed.top, legacyTop);
  assert.equal(fixed.top, bbox.y0 * scale);
  assert.ok(
    Math.abs(fixed.top + fixed.height - (PAGE_HEIGHT - legacyTop)) < 1e-9,
    '旧实现把文字框画到了页面底部，应被回归测试拦住'
  );
});

test('无有效文字框时不应声称精确定位', () => {
  assert.equal(hasDrawableBboxes([]), false);
  assert.equal(hasDrawableBboxes([{ ...bbox, x1: bbox.x0 }]), false);
  assert.equal(
    hasDrawableBboxes([{ ...bbox, page_width: 0, page_height: 0 }]),
    false
  );
  assert.equal(hasDrawableBboxes([bbox]), true);
});

test('旋转页面不返回可绘制矩形，交由页级定位兜底', () => {
  assert.equal(toOverlayRect(bbox, 1, 90), null);
  assert.equal(toOverlayRect(bbox, 1, 180), null);
  assert.equal(toOverlayRect(bbox, 1, 270), null);
});

test('解析记录与当前页面裁剪框尺寸不一致时按比例归一化', () => {
  const rect = toOverlayRect(bbox, 1, 0, PAGE_WIDTH * 2, PAGE_HEIGHT * 2);
  assert.ok(rect);
  assert.equal(rect.left, bbox.x0 * 2);
  assert.equal(rect.top, bbox.y0 * 2);
  assert.equal(rect.width, (bbox.x1 - bbox.x0) * 2);
  assert.equal(rect.height, (bbox.y1 - bbox.y0) * 2);
});

test('越界文字框会被裁剪到页面内', () => {
  const rect = toOverlayRect(
    { ...bbox, x0: -10, y0: -5, x1: PAGE_WIDTH + 10, y1: PAGE_HEIGHT + 10 },
    1,
    0
  );
  assert.ok(rect);
  assert.equal(rect.left, 0);
  assert.equal(rect.top, 0);
  assert.equal(rect.width, PAGE_WIDTH);
  assert.equal(rect.height, PAGE_HEIGHT);
});
