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
      <header className="p-4 border-b border-slate-800/50">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2 text-[#F8FAFC]">
            <FolderOpen className="w-5 h-5" />
            <h2 className="font-medium">资料空间</h2>
          </div>
          <button
            className="p-1.5 rounded hover:bg-slate-800/50 text-slate-400 hover:text-[#38BDF8] transition-colors"
            title="上传文件"
          >
            <Plus className="w-4 h-4" />
          </button>
        </div>
        <div className="text-xs text-slate-500">
          {documents.length} / 10 个文件
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
                    w-full px-3 py-2.5 rounded-lg text-left transition-colors
                    ${selectedId === doc.id
                      ? 'bg-slate-800/70 text-[#F8FAFC]'
                      : 'text-slate-300 hover:bg-slate-800/40'
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
                      <div className="w-2 h-2 rounded-full bg-[#F59E0B] animate-pulse" />
                    )}
                    {doc.status === 'ready' && (
                      <div className="w-2 h-2 rounded-full bg-[#4FD1C5]" />
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
