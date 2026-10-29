import type { ChatModelAdapter, ChatModelRunResult, ThreadMessage } from '@assistant-ui/react';

import { parseSseStream } from './sse';
import type {
  EvidenceSpanSample,
  SearchEvidenceResult,
  StreamEvent,
} from './types/stream-events';

export type EvidenceToolArgs = { query: string };
export type EvidenceToolResult = {
  is_sample: boolean;
  note?: string;
  evidence_spans: EvidenceSpanSample[];
  claim_text?: string;
};

function extractText(message: ThreadMessage): string {
  return message.content
    .filter((part): part is { type: 'text'; text: string } => part.type === 'text')
    .map((part) => part.text)
    .join('\n');
}

function toBackendRole(role: ThreadMessage['role']): 'user' | 'assistant' | 'system' {
  return role;
}

/**
 * fetch / stream 取消时抛出的是 DOMException，assistant-ui 的运行时只把
 * `Error && name === "AbortError"` 识别为“已取消”。这里统一转换为真正的
 * Error，确保点击“停止生成”后消息状态是 cancelled 而不是 error。
 */
function createAbortError(): Error {
  const error = new Error('已停止生成');
  error.name = 'AbortError';
  return error;
}

/**
 * 将 FastAPI 的 SSE 事件流转换为 assistant-ui 的 ChatModelAdapter。
 * Day 2 范围：仅转发文本内容；search_evidence 工具调用返回明确标注的样例证据。
 */
export function createEvidenceDeskAdapter(workspaceId: string): ChatModelAdapter {
  return {
    async *run({ messages, abortSignal }) {
      const backendMessages = messages.map((m) => ({
        role: toBackendRole(m.role),
        content: extractText(m),
      }));

      let text = '';
      let toolArgs: EvidenceToolArgs | null = null;
      let toolResult: EvidenceToolResult | null = null;
      const toolCallId = 'evidence-search';

      function buildResult(): ChatModelRunResult {
        const content: ChatModelRunResult['content'] = [{ type: 'text', text }];
        if (toolArgs) {
          content.push({
            type: 'tool-call',
            toolCallId,
            toolName: 'search_evidence',
            args: toolArgs,
            argsText: JSON.stringify(toolArgs),
            result: toolResult ?? undefined,
          });
        }
        return { content };
      }

      try {
        const response = await fetch('/api/chat/stream', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            workspace_id: workspaceId,
            messages: backendMessages,
          }),
          signal: abortSignal,
        });

        if (!response.ok || !response.body) {
          throw new Error(`对话请求失败: HTTP ${response.status}`);
        }

        for await (const event of parseSseStream(
          response.body,
          abortSignal
        ) as AsyncGenerator<StreamEvent, void>) {
          switch (event.type) {
            case 'run_started':
              break;
            case 'text_delta':
              text += event.delta;
              yield buildResult();
              break;
            case 'tool_started':
              toolArgs = event.arguments as EvidenceToolArgs;
              yield buildResult();
              break;
            case 'tool_finished': {
              const result = event.result as SearchEvidenceResult;
              toolResult = {
                is_sample: result.is_sample,
                note: result.note,
                evidence_spans: result.evidence_spans,
              };
              yield buildResult();
              break;
            }
            case 'claim_ready':
              if (toolResult) {
                toolResult = {
                  is_sample: toolResult.is_sample,
                  note: toolResult.note,
                  evidence_spans: toolResult.evidence_spans,
                  claim_text: event.claim.text,
                };
                yield buildResult();
              }
              break;
            case 'run_finished':
              yield buildResult();
              return;
            case 'error':
              yield {
                ...buildResult(),
                status: {
                  type: 'incomplete',
                  reason: 'error',
                  error: event.message,
                },
              };
              return;
            default:
              break;
          }
        }

        // 流被提前取消时（reader.cancel 可能让循环正常结束），同样视为已取消。
        if (abortSignal.aborted) {
          throw createAbortError();
        }
      } catch (error) {
        if (abortSignal.aborted) {
          throw createAbortError();
        }
        throw error;
      }
    },
  };
}
