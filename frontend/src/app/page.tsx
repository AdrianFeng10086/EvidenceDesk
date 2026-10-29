import { redirect } from 'next/navigation';

export default function HomePage() {
  // Redirect to demo workspace
  redirect('/workspace/demo');
}
