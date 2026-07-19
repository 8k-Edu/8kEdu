// Community identity for the remix network.
//
// Primary path: Supabase anonymous auth — one tap, no email, gives a real auth.uid()
// so votes are RLS-enforced (one per artifact+voter). Requires "Allow anonymous sign-ins"
// enabled in Supabase → Authentication → Sign In / Providers.
//
// Fallback: if anonymous sign-in is disabled (or config missing), mint a persisted local
// guest id so login + voting still work in the demo; votes go through the open /pub/vote
// endpoint keyed on that stable id. Flipping the toggle upgrades identity to cloud with no
// code change.
import { createClient } from '@supabase/supabase-js'

const LS_GUEST = '8kedu-guest-id'
let _client
let _clientPromise

async function client() {
  if (_client !== undefined) return _client
  if (!_clientPromise) {
    _clientPromise = (async () => {
      try {
        const cfg = await fetch('/pub/config').then((r) => r.json())
        _client = cfg?.url && cfg?.anon_key
          ? createClient(cfg.url, cfg.anon_key, { auth: { persistSession: true, autoRefreshToken: true } })
          : null
      } catch {
        _client = null
      }
      return _client
    })()
  }
  return _clientPromise
}

const cloud = (session, c) => ({
  uid: session.user.id,
  handle: 'guest-' + session.user.id.slice(0, 4),
  mode: 'cloud',
  client: c,
  token: session.access_token,
})

function localGuest() {
  let id = localStorage.getItem(LS_GUEST)
  if (!id) {
    id = 'guest-' + Math.random().toString(36).slice(2, 8)
    localStorage.setItem(LS_GUEST, id)
  }
  return { uid: id, handle: id, mode: 'local', client: null }
}

// Restore an existing identity WITHOUT logging in — so a fresh visitor sees a "Sign in" button.
export async function restore() {
  const c = await client()
  if (c) {
    const { data: { session } } = await c.auth.getSession()
    if (session?.user) return cloud(session, c)
  }
  const existing = localStorage.getItem(LS_GUEST)
  return existing ? { uid: existing, handle: existing, mode: 'local', client: null } : null
}

export async function signInGuest() {
  const c = await client()
  if (c) {
    const { error } = await c.auth.signInAnonymously()
    if (!error) {
      const { data: { session } } = await c.auth.getSession()
      if (session?.user) return cloud(session, c)
    }
  }
  return localGuest()
}

export async function signOut() {
  const c = await client()
  if (c) { try { await c.auth.signOut() } catch { /* ignore */ } }
  localStorage.removeItem(LS_GUEST)
}
