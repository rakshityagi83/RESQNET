import { useState } from 'react'
import {
  ShieldCheck,
  Lock,
  User,
  LogOut,
  LogIn,
  LoaderCircle,
  X
} from 'lucide-react'

import { useAuth } from './AuthContext.jsx'

const inputClass =
  'w-full rounded-xl border border-slate-700 bg-slate-900 px-4 py-3 text-sm text-white outline-none focus:border-cyan-500'

const buttonClass =
  'flex items-center justify-center gap-2 rounded-xl border border-slate-700 px-4 py-2 text-sm transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50'

export default function AuthControls() {
  const {
    status,
    busy,
    error,
    user,
    login,
    logout,
    recoverSession
  } = useAuth()

  const [open, setOpen] = useState(false)

  async function handleLogin(event) {
    event.preventDefault()

    if (busy) return

    const form = event.currentTarget
    const data = new FormData(form)

    const username = String(data.get('username') || '')
    const password = String(data.get('password') || '')

    // Remove the password from the visible form immediately.
    form.elements.namedItem('password').value = ''

    const success = await login(username, password)

    if (success) {
      setOpen(false)
    }
  }

  if (status === 'disabled') {
    return null
  }

  if (status === 'checking' || busy === 'recover') {
    return (
      <div
        role="status"
        className="flex items-center gap-2 text-sm text-slate-400"
      >
        <LoaderCircle size={16} className="animate-spin" />
        Checking session...
      </div>
    )
  }

  if (status === 'unavailable') {
    return (
      <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-3">
        <p role="alert" className="text-sm text-amber-300">
          {error || 'Authentication service unavailable.'}
        </p>

        <button
          type="button"
          disabled={Boolean(busy)}
          onClick={() => recoverSession()}
          className="mt-2 text-sm text-cyan-400 hover:underline"
        >
          Retry connection
        </button>
      </div>
    )
  }

  if (status === 'authenticated' && user) {
    return (
      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-3 rounded-xl border border-slate-700 bg-slate-900/70 px-4 py-2">
            <ShieldCheck size={23} className="text-cyan-400" />

            <div>
              <p className="text-sm font-semibold text-white">
                {user.username}
              </p>

              <p className="text-xs capitalize text-cyan-400">
                {user.role === 'admin'
                  ? 'Administrator'
                  : 'Relief Operator'}
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={() => logout()}
            disabled={Boolean(busy)}
            className={buttonClass + ' text-slate-300'}
          >
            {busy === 'logout'
              ? <LoaderCircle size={16} className="animate-spin" />
              : <LogOut size={16} />}

            {busy === 'logout' ? 'Signing out...' : 'Sign out'}
          </button>
        </div>

        {error && (
          <p role="alert" className="text-sm text-rose-400">
            {error}
          </p>
        )}
      </div>
    )
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="flex items-center gap-2 rounded-xl bg-cyan-600 px-4 py-2 text-sm font-semibold text-white hover:bg-cyan-500"
      >
        <LogIn size={16} />
        Personnel Sign In
      </button>
    )
  }

  return (
    <section
      aria-labelledby="personnel-login-title"
      className="w-full max-w-sm rounded-2xl border border-slate-700 bg-[#101a2b] p-5 shadow-xl"
    >
      <div className="mb-5 flex items-start justify-between gap-3">
        <div>
          <ShieldCheck size={30} className="mb-3 text-cyan-400" />

          <h3
            id="personnel-login-title"
            className="text-xl font-bold text-white"
          >
            Personnel Sign In
          </h3>

          <p className="mt-1 text-xs text-slate-400">
            Authorized emergency response personnel
          </p>
        </div>

        <button
          type="button"
          aria-label="Close sign-in form"
          disabled={Boolean(busy)}
          onClick={() => setOpen(false)}
          className="rounded-lg p-2 text-slate-400 hover:bg-slate-800 disabled:opacity-50"
        >
          <X size={18} />
        </button>
      </div>

      <form onSubmit={handleLogin} className="space-y-4">
        <label className="block">
          <span className="mb-2 flex items-center gap-2 text-xs text-slate-400">
            <User size={14} />
            Username
          </span>

          <input
            name="username"
            type="text"
            autoComplete="username"
            autoCapitalize="none"
            spellCheck={false}
            placeholder="Enter your username"
            minLength={3}
            maxLength={80}
            required
            disabled={Boolean(busy)}
            className={inputClass}
          />
        </label>

        <label className="block">
          <span className="mb-2 flex items-center gap-2 text-xs text-slate-400">
            <Lock size={14} />
            Password
          </span>

          <input
            name="password"
            type="password"
            autoComplete="current-password"
            placeholder="Enter your password"
            maxLength={128}
            required
            disabled={Boolean(busy)}
            className={inputClass}
          />
        </label>

        {error && (
          <div
            role="alert"
            className="rounded-xl border border-rose-500/20 bg-rose-500/5 p-3 text-sm text-rose-400"
          >
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={Boolean(busy)}
          className="flex w-full items-center justify-center gap-2 rounded-xl bg-cyan-600 px-4 py-3 text-sm font-semibold text-white hover:bg-cyan-500 disabled:opacity-50"
        >
          {busy === 'login'
            ? <LoaderCircle size={17} className="animate-spin" />
            : <LogIn size={17} />}

          {busy === 'login'
            ? 'Authenticating...'
            : 'Sign in to RESQNET'}
        </button>

        <p className="flex items-center justify-center gap-2 text-xs text-slate-500">
          <Lock size={12} />
          Secure account access
        </p>
      </form>
    </section>
  )
}
