'use client';

import { useEffect, useState } from 'react';
import { FileText, FolderOpen, MessagesSquare, type LucideIcon } from 'lucide-react';

import { useEvidenceLocator } from '@/lib/stores/evidence-locator';
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
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(null);
  const evidenceTarget = useEvidenceLocator((state) => state.target);
  const clearEvidenceTarget = useEvidenceLocator((state) => state.clear);
  const setEvidenceWorkspace = useEvidenceLocator((state) => state.setWorkspace);

  // 切换资料空间时清掉旧空间的目标，避免把阅读器拉向无权访问的文档版本
  useEffect(() => {
    setEvidenceWorkspace(workspaceId);
    clearEvidenceTarget();
    setSelectedVersionId(null);
  }, [workspaceId, setEvidenceWorkspace, clearEvidenceTarget]);

  // 证据卡/页级引用把目标版本推给右侧阅读器；连续点击时以最后一次为准
  useEffect(() => {
    if (!evidenceTarget || evidenceTarget.workspaceId !== workspaceId) return;
    setSelectedVersionId(evidenceTarget.documentVersionId);
    setActivePanel('docs');
  }, [evidenceTarget, workspaceId]);

  const handleSelectVersion = (versionId: string) => {
    // 用户主动切换文档时丢弃旧证据目标，避免阅读器被拉回上一份文件
    clearEvidenceTarget();
    setSelectedVersionId(versionId);
    // 移动端选择文档后直接切到阅读面板；桌面端三栏同时可见，不影响其他面板
    setActivePanel('docs');
  };

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
          'min-h-0 w-full flex-col border-slate-200 bg-slate-50 md:flex md:w-60 md:flex-none md:border-r lg:w-64 xl:w-72',
          activePanel === 'files' ? 'flex flex-1' : 'hidden'
        )}
      >
        <FileList
          workspaceId={workspaceId}
          selectedVersionId={selectedVersionId}
          onSelectVersion={handleSelectVersion}
        />
      </aside>

      {/* Middle Panel: Chat & Checklist */}
      <main
        className={cn(
          'min-h-0 min-w-0 w-full flex-col bg-white md:flex md:flex-1',
          activePanel === 'chat' ? 'flex flex-1' : 'hidden'
        )}
      >
        {/* key 保证切换资料空间时重置对话运行时 */}
        <ChatPanel key={workspaceId} workspaceId={workspaceId} />
      </main>

      {/* Right Panel: Document Viewer */}
      <aside
        className={cn(
          'min-h-0 w-full flex-col border-slate-200 bg-slate-50 md:flex md:w-[380px] md:flex-none md:border-l lg:w-[460px] xl:w-[560px] 2xl:w-[640px]',
          activePanel === 'docs' ? 'flex flex-1' : 'hidden'
        )}
      >
        <DocumentViewer
          workspaceId={workspaceId}
          versionId={selectedVersionId}
          onSelectVersion={handleSelectVersion}
        />
      </aside>
    </div>
  );
}
