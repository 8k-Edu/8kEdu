// Browser Supabase client with anonymous sign-in — gives each visitor a real auth.uid()
// so votes are per-user and RLS-enforced (one vote per artifact), no email friction.
// The anon/publishable key is public by design; we fetch it at runtime from /pub/config.
import { createClient } from '@supabase/supabase-js'

let _ready = null

export function auth() {
  if (_ready) return _ready
  _ready = (async () => {
    try {
      const cfg = await fetch('/pub/config').then((r) => r.json())
      if (!cfg?.url || !cfg?.anon_key) return { client: null, uid: null, reason: 'no config' }
      const client = createClient(cfg.url, cfg.anon_key, { auth: { persistSession: true, autoRefreshToken: true } })
      let { data: { session } } = await client.auth.getSession()
      if (!session) {
        const { error } = await client.auth.signInAnonymously()
        // anonymous sign-ins must be enabled in Supabase → Auth settings; if off we degrade gracefully
        if (error) return { client, uid: null, reason: error.message }
      }
      const { data: { user } } = await client.auth.getUser()
      return { client, uid: user?.id || null }
    } catch (e) {
      return { client: null, uid: null, reason: String(e).slice(0, 120) }
    }
  })()
  return _ready
}
