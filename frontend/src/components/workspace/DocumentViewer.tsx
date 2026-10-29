'use client';

import { useState } from 'react';
import { ZoomIn, ZoomOut, Download, FileText } from 'lucide-react';

interface DocumentViewerProps {
  workspaceId: string;
}

export function DocumentViewer({ workspaceId }: DocumentViewerProps) {
  const [zoom, setZoom] = useState(100);
  const [currentPage, setCurrentPage] = useState(1);
  const totalPages = 15;

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <header className="border-b border-slate-200 bg-slate-50 px-4 py-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-slate-900">
            <FileText className="h-4 w-4 text-sky-700" />
            <h2 className="text-sm font-medium">文档阅读</h2>
          </div>
          <div className="flex items-center gap-1">
            <button
              className="rounded p-1.5 text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900"
              title="下载"
            >
              <Download className="h-4 w-4" />
            </button>
          </div>
        </div>
      </header>

      {/* Toolbar */}
      <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50 px-4 py-2">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setZoom(Math.max(50, zoom - 10))}
            className="rounded p-1.5 text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900"
            title="缩小"
          >
            <ZoomOut className="h-4 w-4" />
          </button>
          <span className="w-12 text-center text-xs text-slate-600">
            {zoom}%
          </span>
          <button
            onClick={() => setZoom(Math.min(200, zoom + 10))}
            className="rounded p-1.5 text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900"
            title="放大"
          >
            <ZoomIn className="h-4 w-4" />
          </button>
        </div>
        <div className="flex items-center gap-2 text-xs text-slate-500">
          <input
            type="number"
            min={1}
            max={totalPages}
            value={currentPage}
            onChange={(e) => setCurrentPage(Number(e.target.value))}
            className="w-12 rounded border border-slate-300 bg-white px-2 py-1 text-center text-slate-700 focus:border-sky-400 focus:outline-none focus:ring-1 focus:ring-sky-100"
          />
          <span>/ {totalPages}</span>
        </div>
      </div>

      {/* Viewer */}
      <div className="flex-1 overflow-auto bg-slate-100 p-4">
        <div className="flex min-h-full items-center justify-center">
          <div
            className="bg-white shadow-lg ring-1 ring-slate-200"
            style={{
              width: `${(595 * zoom) / 100}px`,
              height: `${(842 * zoom) / 100}px`,
            }}
          >
            <div className="flex h-full w-full items-center justify-center text-slate-400">
              <div className="text-center">
                <FileText className="mx-auto mb-4 h-16 w-16 opacity-30" />
                <p className="text-sm">PDF 渲染区域</p>
                <p className="mt-2 text-xs">第 {currentPage} 页</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
