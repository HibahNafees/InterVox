import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import { AuthProvider } from '../lib/auth'

const ADA = { id: 1, name: 'Ada', email: 'ada@example.com' }

function respond(routes) {
  const fetch = vi.fn(async (url, opts = {}) => {
    const hit = routes[`${opts.method || 'GET'} ${url}`]
    if (!hit) throw new Error(`unexpected ${opts.method || 'GET'} ${url}`)
    const [status, body] = hit
    return { ok: status < 400, status, json: async () => body }
  })
  vi.stubGlobal('fetch', fetch)
  return fetch
}

function renderAt(path) {
  localStorage.setItem('mi_token', 'tok')
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  )
}

afterEach(() => vi.unstubAllGlobals())

describe('account', () => {
  it('deletes everything after the password and confirmation, then logs out', async () => {
    const user = userEvent.setup()
    const fetch = respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'DELETE /api/auth/me': [200, { ok: true }],
    })
    renderAt('/account')
    const button = await screen.findByRole('button', { name: 'Delete everything' })
    expect(button).toBeDisabled()
    await user.type(screen.getByLabelText('Your password'), 'correct-horse')
    expect(button).toBeDisabled()
    await user.click(screen.getByLabelText(/I understand/))
    await user.click(button)

    expect(await screen.findByText('Your account and all its data were deleted.')).toBeInTheDocument()
    const [, opts] = fetch.mock.calls.find(([, o]) => o?.method === 'DELETE')
    expect(JSON.parse(opts.body)).toEqual({ password: 'correct-horse' })
    expect(localStorage.getItem('mi_token')).toBeNull()
  })

  it('a Google-only account confirms by typing its email (T-156)', async () => {
    const user = userEvent.setup()
    const fetch = respond({
      'GET /api/auth/me': [200, { user: { ...ADA, has_password: false, google: true } }],
      'DELETE /api/auth/me': [200, { ok: true }],
      'GET /api/auth/providers': [200, { google_client_id: null }],
    })
    renderAt('/account')
    await user.type(await screen.findByLabelText('Type your email to confirm'), 'ada@example.com')
    await user.click(screen.getByRole('checkbox'))
    await user.click(screen.getByRole('button', { name: 'Delete everything' }))
    const [, opts] = fetch.mock.calls.find(([, o]) => o?.method === 'DELETE')
    expect(JSON.parse(opts.body)).toEqual({ email: 'ada@example.com' })
  })

  it('shows a wrong password', async () => {
    const user = userEvent.setup()
    respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'DELETE /api/auth/me': [403, { error: 'Incorrect password' }],
    })
    renderAt('/account')
    await user.type(await screen.findByLabelText('Your password'), 'nope')
    await user.click(screen.getByLabelText(/I understand/))
    await user.click(screen.getByRole('button', { name: 'Delete everything' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Incorrect password')
  })
})
