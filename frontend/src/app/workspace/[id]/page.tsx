import { WorkspaceLayout } from '@/components/workspace/WorkspaceLayout';

export default function WorkspacePage({
  params,
}: {
  params: { id: string };
}) {
  return <WorkspaceLayout key={params.id} workspaceId={params.id} />;
}
