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
      <header className="px-4 py-3 border-b border-slate-800/50">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-[#F8FAFC]">
            <FileText className="w-4 h-4" />
            <h2 className="text-sm font-medium">文档阅读</h2>
          </div>
          <div className="flex items-center gap-1">
            <button
              className="p-1.5 rounded hover:bg-slate-800/50 text-slate-400 hover:text-[#F8FAFC] transition-colors"
              title="下载"
            >
              <Download className="w-4 h-4" />
            </button>
          </div>
        </div>
      </header>

      {/* Toolbar */}
      <div className="px-4 py-2 border-b border-slate-800/50 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setZoom(Math.max(50, zoom - 10))}
            className="p-1.5 rounded hover:bg-slate-800/50 text-slate-400 hover:text-[#F8FAFC] transition-colors"
            title="缩小"
          >
            <ZoomOut className="w-4 h-4" />
          </button>
          <span className="text-xs text-slate-400 w-12 text-center">
            {zoom}%
          </span>
          <button
            onClick={() => setZoom(Math.min(200, zoom + 10))}
            className="p-1.5 rounded hover:bg-slate-800/50 text-slate-400 hover:text-[#F8FAFC] transition-colors"
            title="放大"
          >
            <ZoomIn className="w-4 h-4" />
          </button>
        </div>
        <div className="flex items-center gap-2 text-xs text-slate-400">
          <input
            type="number"
            min={1}
            max={totalPages}
            value={currentPage}
            onChange={(e) => setCurrentPage(Number(e.target.value))}
            className="w-12 px-2 py-1 bg-slate-900/50 border border-slate-700/50 rounded text-center focus:outline-none focus:border-[#38BDF8]/50"
          />
          <span>/ {totalPages}</span>
        </div>
      </div>

      {/* Viewer */}
      <div className="flex-1 overflow-auto bg-slate-900/30 p-4">
        <div className="flex items-center justify-center min-h-full">
          <div
            className="bg-white shadow-xl"
            style={{
              width: `${(595 * zoom) / 100}px`,
              height: `${(842 * zoom) / 100}px`,
            }}
          >
            <div className="w-full h-full flex items-center justify-center text-slate-400">
              <div className="text-center">
                <FileText className="w-16 h-16 mx-auto mb-4 opacity-20" />
                <p className="text-sm">PDF 渲染区域</p>
                <p className="text-xs mt-2">第 {currentPage} 页</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
