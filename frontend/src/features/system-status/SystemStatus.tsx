import { useCallback, useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

type Status = 'checking' | 'ready' | 'unavailable'

// Never wait on the API forever: after this the page reports it as unavailable.
const REQUEST_TIMEOUT_MS = 5000

const STATUS_MESSAGES: Record<Status, string> = {
  checking: 'Checking…',
  ready: 'API and database ready',
  unavailable: 'API unavailable',
}

async function checkReadiness(): Promise<Status> {
  try {
    const response = await fetch('/health/ready', {
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    })
    // 503 means the API is up but its database isn't; both read as "unavailable" to a user.
    return response.ok ? 'ready' : 'unavailable'
  } catch {
    // Network error or timeout: the API itself can't be reached.
    return 'unavailable'
  }
}

export function SystemStatus() {
  const [status, setStatus] = useState<Status>('checking')

  const runCheck = useCallback(async () => {
    setStatus('checking')
    setStatus(await checkReadiness())
  }, [])

  useEffect(() => {
    // The request is cancelled by its own timeout; if the component unmounts first, the late
    // result is simply ignored.
    let isCurrent = true
    checkReadiness().then((result) => {
      if (isCurrent) setStatus(result)
    })
    return () => {
      isCurrent = false
    }
  }, [])

  return (
    <Card className="w-full max-w-sm">
      <CardHeader>
        <CardTitle>System status</CardTitle>
        <CardDescription>Is the TalentFlow API running?</CardDescription>
      </CardHeader>
      <CardContent className="flex items-center justify-between gap-4">
        {/* role="status" makes screen readers announce the result when it changes. */}
        <p role="status">{STATUS_MESSAGES[status]}</p>
        <Button variant="outline" onClick={runCheck} disabled={status === 'checking'}>
          Retry
        </Button>
      </CardContent>
    </Card>
  )
}
