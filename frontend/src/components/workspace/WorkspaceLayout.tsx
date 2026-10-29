'use client';

import { ReactNode } from 'react';
import { FileList } from './FileList';
import { ChatPanel } from './ChatPanel';
import { DocumentViewer } from './DocumentViewer';

interface WorkspaceLayoutProps {
  workspaceId: string;
}

export function WorkspaceLayout({ workspaceId }: WorkspaceLayoutProps) {
  return (
    <div className="flex h-screen w-full bg-[#0B0E14]">
      {/* Left Panel: File List */}
      <aside className="w-64 border-r border-slate-800/50 flex flex-col">
        <FileList workspaceId={workspaceId} />
      </aside>

      {/* Middle Panel: Chat & Checklist */}
      <main className="flex-1 flex flex-col min-w-0">
        <ChatPanel workspaceId={workspaceId} />
      </main>

      {/* Right Panel: Document Viewer */}
      <aside className="w-[480px] border-l border-slate-800/50 flex flex-col">
        <DocumentViewer workspaceId={workspaceId} />
      </aside>
    </div>
  );
}
