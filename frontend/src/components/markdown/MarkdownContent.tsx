'use client';

import ReactMarkdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';

import { cn } from '@/lib/utils';

interface MarkdownContentProps {
  content: string;
  className?: string;
}

/**
 * 对话与 Markdown 文档共用的渲染器。
 *
 * 只渲染 GFM 语法，不启用原始 HTML，避免模型输出注入任意标签。
 * 流式输出时内容可能暂时不完整（例如未闭合的代码块），
 * react-markdown 会自动按普通文本降级渲染。
 */
const components: Components = {
  h1: ({ children }) => (
    <h1 className="mb-3 mt-5 text-xl font-semibold text-slate-900 first:mt-0">{children}</h1>
  ),
  h2: ({ children }) => (
    <h2 className="mb-2 mt-5 text-lg font-semibold text-slate-900 first:mt-0">{children}</h2>
  ),
  h3: ({ children }) => (
    <h3 className="mb-2 mt-4 text-base font-semibold text-slate-900 first:mt-0">{children}</h3>
  ),
  h4: ({ children }) => (
    <h4 className="mb-1.5 mt-3 text-sm font-semibold text-slate-900 first:mt-0">{children}</h4>
  ),
  p: ({ children }) => <p className="my-2 leading-relaxed first:mt-0 last:mb-0">{children}</p>,
  ul: ({ children }) => <ul className="my-2 list-disc space-y-1 pl-5">{children}</ul>,
  ol: ({ children }) => <ol className="my-2 list-decimal space-y-1 pl-5">{children}</ol>,
  li: ({ children }) => <li className="leading-relaxed marker:text-slate-400">{children}</li>,
  blockquote: ({ children }) => (
    <blockquote className="my-3 border-l-2 border-sky-300 bg-sky-50/60 py-1 pl-3 text-slate-600">
      {children}
    </blockquote>
  ),
  hr: () => <hr className="my-4 border-slate-200" />,
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noreferrer noopener"
      className="font-medium text-sky-700 underline decoration-sky-300 underline-offset-2 hover:text-sky-800"
    >
      {children}
    </a>
  ),
  strong: ({ children }) => <strong className="font-semibold text-slate-900">{children}</strong>,
  pre: ({ children }) => (
    <pre className="my-3 overflow-x-auto rounded-lg border border-slate-200 bg-slate-950 p-3 text-xs leading-relaxed text-slate-100">
      {children}
    </pre>
  ),
  code: ({ className, children, ...props }) => {
    const isBlock = Boolean(className?.includes('language-'));
    return (
      <code
        className={cn(
          isBlock
            ? 'font-mono text-[12px] text-slate-100'
            : 'rounded bg-slate-100 px-1 py-0.5 font-mono text-[0.9em] text-slate-800',
          className
        )}
        {...props}
      >
        {children}
      </code>
    );
  },
  table: ({ children }) => (
    <div className="my-3 overflow-x-auto rounded-lg border border-slate-200">
      <table className="w-full border-collapse text-sm">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-slate-50 text-slate-700">{children}</thead>,
  th: ({ children }) => (
    <th className="border-b border-slate-200 px-3 py-2 text-left font-medium">{children}</th>
  ),
  td: ({ children }) => (
    <td className="border-b border-slate-100 px-3 py-2 align-top">{children}</td>
  ),
  img: ({ src, alt }) => (
    // eslint-disable-next-line @next/next/no-img-element — 模型输出图片尺寸不可预知
    <img src={src} alt={alt ?? ''} className="my-2 max-w-full rounded-lg border border-slate-200" />
  ),
};

export function MarkdownContent({ content, className }: MarkdownContentProps) {
  return (
    <div className={cn('min-w-0 break-words text-sm text-slate-800', className)}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
