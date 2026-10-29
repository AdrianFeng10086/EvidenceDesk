'use client';

import { useState } from 'react';
import { FileText, FolderOpen, MessagesSquare, type LucideIcon } from 'lucide-react';

import { cn } from '@/lib/utils';
import { ChatPanel } from './ChatPanel';
import { DocumentViewer } from './DocumentViewer';
import { FileList } from './FileList';

interface WorkspaceLayoutProps {
  workspaceId: string;
}

type PanelKey = 'files' | 'chat' | 'docs';

const TABS: { key: PanelKey; label: string; icon: LucideIcon }[] = [
  { key: 'files', label: '资料', icon: FolderOpen },
  { key: 'chat', label: '对话', icon: MessagesSquare },
  { key: 'docs', label: '文档', icon: FileText },
];

/**
 * 工作台布局。
 *
 * 桌面端（md 及以上）：左侧文件清单、中间对话、右侧文档阅读三栏并排。
 * 移动端：不强行压缩成三栏，改为顶部分区标签页，一次只显示一个面板。
 */
export function WorkspaceLayout({ workspaceId }: WorkspaceLayoutProps) {
  const [activePanel, setActivePanel] = useState<PanelKey>('chat');

  return (
    <div className="flex h-[100dvh] w-full flex-col overflow-hidden bg-white md:h-screen md:flex-row">
      {/* 移动端分区标签页 */}
      <nav
        role="tablist"
        aria-label="面板切换"
        className="flex flex-shrink-0 border-b border-slate-200 bg-white md:hidden"
      >
        {TABS.map(({ key, label, icon: Icon }) => {
          const isActive = activePanel === key;
          return (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={isActive}
              onClick={() => setActivePanel(key)}
              className={cn(
                'flex flex-1 items-center justify-center gap-2 py-3 text-sm transition-colors',
                isActive
                  ? 'border-b-2 border-sky-600 text-sky-700'
                  : 'border-b-2 border-transparent text-slate-500 hover:text-slate-800'
              )}
            >
              <Icon className="h-4 w-4" />
              {label}
            </button>
          );
        })}
      </nav>

      {/* Left Panel: File List */}
      <aside
        className={cn(
          'min-h-0 w-full flex-col border-slate-200 bg-slate-50 md:flex md:w-64 md:flex-none md:border-r',
          activePanel === 'files' ? 'flex flex-1' : 'hidden'
        )}
      >
        <FileList workspaceId={workspaceId} />
      </aside>

      {/* Middle Panel: Chat & Checklist */}
      <main
        className={cn(
          'min-h-0 w-full flex-col bg-white md:flex md:flex-1',
          activePanel === 'chat' ? 'flex flex-1' : 'hidden'
        )}
      >
        {/* key 保证切换资料空间时重置对话运行时 */}
        <ChatPanel key={workspaceId} workspaceId={workspaceId} />
      </main>

      {/* Right Panel: Document Viewer */}
      <aside
        className={cn(
          'min-h-0 w-full flex-col border-slate-200 bg-slate-50 md:flex md:w-[480px] md:flex-none md:border-l',
          activePanel === 'docs' ? 'flex flex-1' : 'hidden'
        )}
      >
        <DocumentViewer workspaceId={workspaceId} />
      </aside>
    </div>
  );
}
