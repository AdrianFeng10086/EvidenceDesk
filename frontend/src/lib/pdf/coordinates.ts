import type { BBox } from '../types/documents';

/**
 * pdfplumber 的文字框以页面左上角为原点（单位 pt）。
 * PDF.js 在 rotation = 0 时的 viewport 同样以左上角为原点，因此
 * 只需乘以当前 CSS 缩放比例；不能使用 convertToViewportPoint，
 * 它期待 PDF 原生的左下角原点。
 */
export interface OverlayRect {
  left: number;
  top: number;
  width: number;
  height: number;
}

export function fitScale(
  containerWidth: number,
  pageWidthPoints: number,
  zoom: number,
  padding = 32
): number {
  if (!(containerWidth > 0) || !(pageWidthPoints > 0) || !(zoom > 0)) {
    return zoom;
  }
  const available = Math.max(containerWidth - padding, 120);
  return (available / pageWidthPoints) * zoom;
}

export function toOverlayRect(
  bbox: BBox,
  scale: number,
  rotation: number,
  actualPageWidth?: number,
  actualPageHeight?: number
): OverlayRect | null {
  if (rotation % 360 !== 0) {
    return null;
  }
  if (!(scale > 0)) {
    return null;
  }

  const pageWidth = bbox.page_width > 0 ? bbox.page_width : 0;
  const pageHeight = bbox.page_height > 0 ? bbox.page_height : 0;
  if (!pageWidth || !pageHeight) {
    return null;
  }

  // 解析记录与当前 PDF 页裁剪框不一致时，按实际页面尺寸归一化
  const widthRatio =
    actualPageWidth && actualPageWidth > 0 ? actualPageWidth / pageWidth : 1;
  const heightRatio =
    actualPageHeight && actualPageHeight > 0 ? actualPageHeight / pageHeight : 1;

  const x0 = clamp(bbox.x0, 0, pageWidth);
  const x1 = clamp(bbox.x1, 0, pageWidth);
  const y0 = clamp(bbox.y0, 0, pageHeight);
  const y1 = clamp(bbox.y1, 0, pageHeight);
  const width = (x1 - x0) * widthRatio;
  const height = (y1 - y0) * heightRatio;

  if (!(width > 0) || !(height > 0)) {
    return null;
  }

  return {
    left: x0 * widthRatio * scale,
    top: y0 * heightRatio * scale,
    width: width * scale,
    height: height * scale,
  };
}

export function hasDrawableBboxes(bboxes: readonly BBox[]): boolean {
  return bboxes.some((bbox) => {
    if (!(bbox.page_width > 0) || !(bbox.page_height > 0)) return false;
    const x0 = clamp(bbox.x0, 0, bbox.page_width);
    const x1 = clamp(bbox.x1, 0, bbox.page_width);
    const y0 = clamp(bbox.y0, 0, bbox.page_height);
    const y1 = clamp(bbox.y1, 0, bbox.page_height);
    return x1 > x0 && y1 > y0;
  });
}

export function toOverlayRects(
  bboxes: readonly BBox[],
  scale: number,
  rotation: number,
  actualPageWidth?: number,
  actualPageHeight?: number
): OverlayRect[] {
  return bboxes
    .map((bbox) =>
      toOverlayRect(bbox, scale, rotation, actualPageWidth, actualPageHeight)
    )
    .filter((rect): rect is OverlayRect => rect !== null);
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}
