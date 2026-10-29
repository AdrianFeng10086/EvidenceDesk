'use client';

import { useState, useRef, useEffect } from 'react';
import { Send, Loader2 } from 'lucide-react';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
}

interface ChatPanelProps {
  workspaceId: string;
}

export function ChatPanel({ workspaceId }: ChatPanelProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: input.trim(),
      timestamp: new Date()
    };

    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    // Mock streaming response
    setTimeout(() => {
      const assistantMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: '我已经理解您的问题。这是一个模拟回复，用于演示流式对话界面。',
        timestamp: new Date()
      };
      setMessages(prev => [...prev, assistantMessage]);
      setIsLoading(false);
    }, 1000);
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <header className="px-6 py-4 border-b border-slate-800/50">
        <h1 className="text-lg font-medium text-[#F8FAFC]">有据工作台</h1>
        <p className="text-sm text-slate-500 mt-1">
          提出问题,获取有据可查的结论
        </p>
      </header>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6 py-6">
        {messages.length === 0 ? (
          <div className="h-full flex items-center justify-center">
            <div className="text-center max-w-md">
              <h2 className="text-xl font-medium text-[#F8FAFC] mb-3">
                开始提问
              </h2>
              <p className="text-sm text-slate-400 leading-relaxed">
                您可以询问关于已上传文档的任何问题，我会基于文档内容给出准确回答，并附上具体证据引用。
              </p>
              <div className="mt-6 space-y-2">
                <button className="w-full px-4 py-2.5 text-left text-sm rounded-lg border border-slate-800/50 hover:border-[#38BDF8]/30 hover:bg-slate-800/30 text-slate-300 transition-colors">
                  这个项目的申报条件有哪些？
                </button>
                <button className="w-full px-4 py-2.5 text-left text-sm rounded-lg border border-slate-800/50 hover:border-[#38BDF8]/30 hover:bg-slate-800/30 text-slate-300 transition-colors">
                  我们公司符合申报资格吗？
                </button>
              </div>
            </div>
          </div>
        ) : (
          <div className="space-y-6 max-w-3xl">
            {messages.map((message) => (
              <div
                key={message.id}
                className={`
                  flex gap-4
                  ${message.role === 'user' ? 'justify-end' : 'justify-start'}
                `}
              >
                {message.role === 'assistant' && (
                  <div className="w-8 h-8 rounded-lg bg-[#38BDF8]/10 border border-[#38BDF8]/20 flex items-center justify-center flex-shrink-0">
                    <div className="w-4 h-4 rounded bg-[#38BDF8]/80" />
                  </div>
                )}
                <div
                  className={`
                    rounded-2xl px-4 py-3 max-w-[85%]
                    ${message.role === 'user'
                      ? 'bg-[#38BDF8]/10 border border-[#38BDF8]/20 text-[#F8FAFC]'
                      : 'bg-slate-800/40 border border-slate-700/50 text-slate-200'
                    }
                  `}
                >
                  <div className="text-sm leading-relaxed whitespace-pre-wrap">
                    {message.content}
                  </div>
                </div>
              </div>
            ))}
            {isLoading && (
              <div className="flex gap-4 justify-start">
                <div className="w-8 h-8 rounded-lg bg-[#38BDF8]/10 border border-[#38BDF8]/20 flex items-center justify-center flex-shrink-0">
                  <Loader2 className="w-4 h-4 text-[#38BDF8] animate-spin" />
                </div>
                <div className="rounded-2xl px-4 py-3 bg-slate-800/40 border border-slate-700/50">
                  <div className="flex items-center gap-2 text-slate-400">
                    <div className="w-2 h-2 rounded-full bg-slate-500 animate-pulse" />
                    <div className="w-2 h-2 rounded-full bg-slate-500 animate-pulse delay-100" />
                    <div className="w-2 h-2 rounded-full bg-slate-500 animate-pulse delay-200" />
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* Input */}
      <div className="border-t border-slate-800/50 p-4">
        <form onSubmit={handleSubmit} className="max-w-3xl mx-auto">
          <div className="relative flex items-end gap-2">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSubmit(e);
                }
              }}
              placeholder="输入您的问题... (Enter 发送, Shift+Enter 换行)"
              className="flex-1 min-h-[48px] max-h-[200px] px-4 py-3 bg-slate-900/50 border border-slate-700/50 rounded-xl text-[#F8FAFC] placeholder:text-slate-500 focus:outline-none focus:border-[#38BDF8]/50 focus:ring-1 focus:ring-[#38BDF8]/20 resize-none"
              rows={1}
            />
            <button
              type="submit"
              disabled={!input.trim() || isLoading}
              className="px-4 py-3 bg-[#38BDF8] hover:bg-[#38BDF8]/90 disabled:bg-slate-700 disabled:cursor-not-allowed text-white rounded-xl transition-colors flex items-center gap-2"
            >
              <Send className="w-4 h-4" />
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
