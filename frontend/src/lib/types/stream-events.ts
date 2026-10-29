/**
 * 后端 SSE 流式事件类型。
 * 与 docs/architecture.md 「三、流式事件协议」保持一致。
 */

export interface RunStartedEvent {
  type: 'run_started';
  run_id: string;
  model: string;
  timestamp: string;
}

export interface TextDeltaEvent {
  type: 'text_delta';
  delta: string;
  timestamp: string;
}

export interface ToolStartedEvent {
  type: 'tool_started';
  tool_name: string;
  arguments: Record<string, unknown>;
  timestamp: string;
}

export interface EvidenceSpanSample {
  id: string;
  document_name: string;
  page: number;
  text: string;
  is_sample: true;
}

export interface SearchEvidenceResult {
  is_sample: boolean;
  note?: string;
  evidence_spans: EvidenceSpanSample[];
}

export interface ToolFinishedEvent {
  type: 'tool_finished';
  tool_name: string;
  result: SearchEvidenceResult | Record<string, unknown>;
  duration_ms: number;
  timestamp: string;
}

export interface ClaimReady {
  id: string;
  text: string;
  evidence_span_ids: string[];
  validation_status: 'pending' | 'validated' | 'invalid';
  is_sample?: boolean;
}

export interface ClaimReadyEvent {
  type: 'claim_ready';
  claim: ClaimReady;
  timestamp: string;
}

export interface VisualEvidenceBox {
  id: string;
  x: number;
  y: number;
  width: number;
  height: number;
  description: string;
  supports_claim_ids: string[];
}

export interface VisualEvidenceReadyEvent {
  type: 'visual_evidence_ready';
  visual_evidence: {
    id: string;
    image_id: string;
    page: number;
    boxes: VisualEvidenceBox[];
    validation_status: string;
  };
  timestamp: string;
}

export interface ClarificationRequiredEvent {
  type: 'clarification_required';
  question: string;
  fact_key: string;
  reason: string;
  timestamp: string;
}

export interface RunFinishedEvent {
  type: 'run_finished';
  run_id: string;
  summary: {
    claims_count: number;
    evidence_spans_count: number;
    visual_evidences_count: number;
    clarifications_count: number;
  };
  timestamp: string;
}

export interface ErrorEvent {
  type: 'error';
  error_code: string;
  message: string;
  recoverable: boolean;
  timestamp: string;
}

export type StreamEvent =
  | RunStartedEvent
  | TextDeltaEvent
  | ToolStartedEvent
  | ToolFinishedEvent
  | ClaimReadyEvent
  | VisualEvidenceReadyEvent
  | ClarificationRequiredEvent
  | RunFinishedEvent
  | ErrorEvent;
