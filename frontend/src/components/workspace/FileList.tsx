'use client';

import { useState, useEffect } from 'react';
import { FileText, Plus, FolderOpen } from 'lucide-react';

interface Document {
  id: string;
  name: string;
  type: string;
  uploadedAt: string;
  pageCount?: number;
  status: 'processing' | 'ready' | 'error';
}

interface FileListProps {
  workspaceId: string;
}

export function FileList({ workspaceId }: FileListProps) {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  // Mock data for development
  useEffect(() => {
    setDocuments([
      {
        id: '1',
        name: '项目申报指南.pdf',
        type: 'pdf',
        uploadedAt: '2024-10-27',
        pageCount: 15,
        status: 'ready'
      }
    ]);
  }, [workspaceId]);

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <header className="border-b border-slate-200 p-4">
        <div className="mb-3 flex items-center justify-between">
          <div className="flex items-center gap-2 text-slate-900">
            <FolderOpen className="h-5 w-5 text-sky-700" />
            <h2 className="font-medium">资料空间</h2>
          </div>
          <button
            className="rounded p-1.5 text-slate-500 transition-colors hover:bg-slate-200/70 hover:text-sky-700"
            title="上传文件"
          >
            <Plus className="h-4 w-4" />
          </button>
        </div>
        <div className="flex items-center gap-2 text-xs text-slate-500">
          <span>{documents.length} / 10 个文件</span>
          <span className="rounded-full border border-amber-300 bg-amber-50 px-2 py-0.5 text-[11px] text-amber-700">
            示例数据
          </span>
        </div>
      </header>

      {/* File List */}
      <div className="flex-1 overflow-y-auto">
        {documents.length === 0 ? (
          <div className="p-6 text-center text-slate-500">
            <FileText className="w-12 h-12 mx-auto mb-3 opacity-30" />
            <p className="text-sm">暂无文件</p>
            <p className="text-xs mt-1">点击 + 上传文档</p>
          </div>
        ) : (
          <ul className="p-2 space-y-1">
            {documents.map((doc) => (
              <li key={doc.id}>
                <button
                  className={`
                    w-full rounded-lg px-3 py-2.5 text-left transition-colors
                    ${selectedId === doc.id
                      ? 'bg-white text-slate-900 shadow-sm ring-1 ring-slate-200'
                      : 'text-slate-700 hover:bg-slate-100'
                    }
                  `}
                  onClick={() => setSelectedId(doc.id)}
                >
                  <div className="flex items-start gap-2">
                    <FileText className="w-4 h-4 mt-0.5 flex-shrink-0" />
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium truncate">
                        {doc.name}
                      </div>
                      <div className="flex items-center gap-2 mt-1 text-xs text-slate-500">
                        {doc.pageCount && <span>{doc.pageCount}页</span>}
                        <span>·</span>
                        <span>{doc.uploadedAt}</span>
                      </div>
                    </div>
                    {doc.status === 'processing' && (
                      <div className="h-2 w-2 animate-pulse rounded-full bg-amber-500" />
                    )}
                    {doc.status === 'ready' && (
                      <div className="h-2 w-2 rounded-full bg-teal-500" />
                    )}
                  </div>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
