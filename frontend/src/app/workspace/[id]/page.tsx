import { WorkspaceLayout } from '@/components/workspace/WorkspaceLayout';

export default function WorkspacePage({
  params,
}: {
  params: { id: string };
}) {
  return <WorkspaceLayout workspaceId={params.id} />;
}
