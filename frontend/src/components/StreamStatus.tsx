import type { StreamState } from '@/api/ops-stream';
import { Badge } from './ui-kit';
export function StreamStatus({ stream }: { stream: { state: StreamState; lastEventAt: number | null; error: string | null } }) {
  return <div role="status" className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
    <Badge tone={stream.state === 'live' ? 'healthy' : stream.state === 'error' || stream.state === 'stale' ? 'attention' : 'neutral'}>Stream: {stream.state}</Badge>
    {stream.lastEventAt != null && <span>Last good event: {new Date(stream.lastEventAt).toISOString()}</span>}
    {stream.error && <span>{stream.error}</span>}
  </div>;
}