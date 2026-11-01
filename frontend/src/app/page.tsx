import { redirect } from 'next/navigation';

export default function HomePage() {
  // 演示账户默认进入后端启动时自动创建的资料空间
  const demoWorkspaceId =
    process.env.NEXT_PUBLIC_DEMO_WORKSPACE_ID ??
    process.env.DEMO_WORKSPACE_ID ??
    'demo_workspace';
  redirect(`/workspace/${encodeURIComponent(demoWorkspaceId)}`);
}
