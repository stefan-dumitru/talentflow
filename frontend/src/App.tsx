import { SystemStatus } from '@/features/system-status/SystemStatus'

export default function App() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 p-4">
      <h1 className="text-3xl font-semibold tracking-tight">TalentFlow</h1>
      <SystemStatus />
    </main>
  )
}
