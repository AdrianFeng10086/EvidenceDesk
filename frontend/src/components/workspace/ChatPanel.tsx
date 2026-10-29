'use client';

import { useMemo } from 'react';
import {
  AssistantRuntimeProvider,
  ComposerPrimitive,
  ContentPartPrimitive,
  MessagePrimitive,
  ThreadPrimitive,
  useLocalRuntime,
  useMessage,
  useMessageRuntime,
  useThread,
  useThreadRuntime,
} from '@assistant-ui/react';
import {
  AlertCircle,
  Loader2,
  MessagesSquare,
  RefreshCw,
  Send,
  Sparkles,
  Square,
} from 'lucide-react';

import { createEvidenceDeskAdapter } from '@/lib/chat-adapter';
import { cn } from '@/lib/utils';
import { EvidenceCard } from './EvidenceCard';

interface ChatPanelProps {
  workspaceId: string;
}

const SUGGESTIONS = [
  '这个项目的申报条件有哪些？',
  '我们公司符合申报资格吗？',
  '需要准备哪些证明材料？',
];

/**
 * 中间面板：对话与清单。
 *
 * 通过 assistant-ui 的 LocalRuntime 承载 FastAPI SSE 文本流：
 * - 适配器见 lib/chat-adapter.ts
 * - 证据卡通过 makeAssistantToolUI 注册（见 EvidenceCard.tsx）
 * - 运行状态、停止生成、失败重试均由运行时状态驱动
 */
export function ChatPanel({ workspaceId }: ChatPanelProps) {
  // 适配器随 workspaceId 变化，保持引用稳定以免重建运行时
  const adapter = useMemo(
    () => createEvidenceDeskAdapter(workspaceId),
    [workspaceId]
  );
  const runtime = useLocalRuntime(adapter);

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      {/* 注册 search_evidence 的折叠证据卡（Day 2 为明确标注的样例数据） */}
      <EvidenceCard />
      <ThreadView workspaceId={workspaceId} />
    </AssistantRuntimeProvider>
  );
}

function ThreadView({ workspaceId }: ChatPanelProps) {
  const isEmpty = useThread((s) => s.messages.length === 0);
  const isRunning = useThread((s) => s.isRunning);
  const threadRuntime = useThreadRuntime();

  const handleSuggestion = (question: string) => {
    void threadRuntime.append({
      role: 'user',
      content: [{ type: 'text', text: question }],
    });
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* Header */}
      <header className="flex flex-shrink-0 items-center justify-between gap-4 border-b border-slate-200 bg-white px-6 py-4">
        <div>
          <h1 className="text-lg font-medium text-slate-900">有据工作台</h1>
          <p className="mt-1 text-sm text-slate-500">
            提出问题，获取有据可查的结论
          </p>
        </div>
        <RunStatus isRunning={isRunning} />
      </header>

      {isEmpty ? (
        <EmptyState workspaceId={workspaceId} onPick={handleSuggestion} />
      ) : (
        <ThreadPrimitive.Root className="min-h-0 flex-1">
          <ThreadPrimitive.Viewport className="h-full overflow-y-auto px-6 py-6">
            <div className="mx-auto flex max-w-3xl flex-col gap-6">
              <ThreadPrimitive.Messages
                components={{
                  UserMessage,
                  AssistantMessage,
                }}
              />
            </div>
          </ThreadPrimitive.Viewport>
        </ThreadPrimitive.Root>
      )}

      <ComposerBar isRunning={isRunning} />
    </div>
  );
}

function RunStatus({ isRunning }: { isRunning: boolean }) {
  if (!isRunning) return null;

  return (
    <div className="flex items-center gap-2 rounded-full border border-sky-200 bg-sky-50 px-3 py-1 text-xs text-sky-700">
      <Loader2 className="h-3.5 w-3.5 animate-spin" />
      正在生成
    </div>
  );
}

function EmptyState({
  workspaceId,
  onPick,
}: {
  workspaceId: string;
  onPick: (question: string) => void;
}) {
  return (
    <div className="flex flex-1 items-center justify-center overflow-y-auto px-6 py-10">
      <div className="max-w-md text-center">
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-2xl border border-sky-200 bg-sky-50">
          <MessagesSquare className="h-6 w-6 text-sky-600" />
        </div>
        <h2 className="mb-3 text-xl font-medium text-slate-900">开始提问</h2>
        <p className="text-sm leading-relaxed text-slate-500">
          您可以询问关于资料空间
          <span className="mx-1 font-mono text-slate-700">{workspaceId}</span>
          中已上传文档的问题。回答会附上具体证据引用，并标注数据来源。
        </p>
        <div className="mt-6 space-y-2">
          {SUGGESTIONS.map((question) => (
            <button
              key={question}
              type="button"
              onClick={() => onPick(question)}
              className="w-full rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-left text-sm text-slate-700 transition-colors hover:border-sky-300 hover:bg-sky-50"
            >
              {question}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function UserMessage() {
  return (
    <MessagePrimitive.Root className="flex justify-end">
      <div className="max-w-[85%] rounded-2xl border border-sky-200 bg-sky-50 px-4 py-3 text-sm leading-relaxed text-slate-900">
        <MessagePrimitive.Content components={{ Text: UserText }} />
      </div>
    </MessagePrimitive.Root>
  );
}

function UserText() {
  return (
    <p className="whitespace-pre-wrap">
      <ContentPartPrimitive.Text />
    </p>
  );
}

function AssistantMessage() {
  const status = useMessage((m) => m.status);
  const messageRuntime = useMessageRuntime();

  const isRunning = status?.type === 'running';
  const isCancelled =
    status?.type === 'incomplete' && status.reason === 'cancelled';
  const isError = status?.type === 'incomplete' && status.reason === 'error';

  const errorText = isError
    ? status.error instanceof Error
      ? status.error.message
      : typeof status.error === 'string'
        ? status.error
        : '生成失败，请稍后重试'
    : null;

  return (
    <MessagePrimitive.Root className="flex gap-4">
      <div className="mt-0.5 flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg border border-sky-200 bg-sky-50">
        <Sparkles className="h-4 w-4 text-sky-600" />
      </div>

      <div className="min-w-0 flex-1">
        <div className="text-sm leading-relaxed text-slate-800">
          <MessagePrimitive.Content components={{ Text: AssistantText }} />
        </div>

        {isRunning && (
          <div className="mt-2 flex items-center gap-2 text-xs text-slate-500">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            正在生成…
          </div>
        )}

        {isCancelled && (
          <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-slate-500">
            <span className="inline-flex items-center gap-1.5">
              <Square className="h-3 w-3" />
              已停止生成
            </span>
            <RetryButton onRetry={() => messageRuntime.reload()} />
          </div>
        )}

        {isError && (
          <div className="mt-2 flex flex-wrap items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
            <span className="inline-flex min-w-0 items-center gap-1.5">
              <AlertCircle className="h-3.5 w-3.5 flex-shrink-0" />
              <span className="truncate" title={errorText ?? undefined}>
                {errorText}
              </span>
            </span>
            <RetryButton onRetry={() => messageRuntime.reload()} />
          </div>
        )}
      </div>
    </MessagePrimitive.Root>
  );
}

function RetryButton({ onRetry }: { onRetry: () => void }) {
  return (
    <button
      type="button"
      onClick={onRetry}
      className="inline-flex items-center gap-1 rounded-md border border-slate-300 px-2 py-1 text-xs text-slate-600 transition-colors hover:border-sky-400 hover:text-sky-700 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-sky-300"
    >
      <RefreshCw className="h-3 w-3" />
      重试
    </button>
  );
}

function AssistantText() {
  return (
    <p className="whitespace-pre-wrap">
      <ContentPartPrimitive.Text />
      <ContentPartPrimitive.InProgress>
        <span className="ml-0.5 inline-block h-3.5 w-1.5 translate-y-0.5 animate-pulse rounded-sm bg-sky-500" />
      </ContentPartPrimitive.InProgress>
    </p>
  );
}

function ComposerBar({ isRunning }: { isRunning: boolean }) {
  return (
    <div className="flex-shrink-0 border-t border-slate-200 bg-white p-4">
      <ComposerPrimitive.Root className="mx-auto flex max-w-3xl items-end gap-2">
        <ComposerPrimitive.Input
          rows={1}
          submitOnEnter
          cancelOnEscape
          placeholder={
            isRunning
              ? '正在生成，可点击右侧按钮停止…'
              : '输入您的问题…（Enter 发送，Shift+Enter 换行）'
          }
          className="max-h-[200px] min-h-[48px] flex-1 resize-none rounded-xl border border-slate-300 bg-white px-4 py-3 text-slate-900 placeholder:text-slate-400 focus:border-sky-400 focus:outline-none focus:ring-1 focus:ring-sky-100"
        />

        {isRunning ? (
          <ComposerPrimitive.Cancel
            title="停止生成"
            aria-label="停止生成"
            className="flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-100 px-4 py-3 text-slate-700 transition-colors hover:bg-slate-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-300 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Square className="h-4 w-4 fill-current" />
          </ComposerPrimitive.Cancel>
        ) : (
          <ComposerPrimitive.Send
            title="发送"
            aria-label="发送"
            className={cn(
              'flex items-center gap-2 rounded-xl bg-sky-600 px-4 py-3 text-white transition-colors',
              'hover:bg-sky-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-300',
              'disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-400'
            )}
          >
            <Send className="h-4 w-4" />
          </ComposerPrimitive.Send>
        )}
      </ComposerPrimitive.Root>
    </div>
  );
}
