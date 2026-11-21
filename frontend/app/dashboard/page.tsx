'use client';
import {useEffect} from 'react';
import {useRouter} from 'next/navigation';

export default function DashboardPage() {
  const router = useRouter();
  useEffect(() => { router.replace('/queue'); }, [router]);
  return <main className="route-gate">Opening workspace…</main>;
}
