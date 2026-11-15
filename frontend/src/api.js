// API client for the Flask backend (see /backend). Every call goes through request() below, which
// applies two small "interceptors":
//   * request interceptor  -> attaches `Authorization: Bearer <JWT>` when a token is stored
//   * response interceptor -> turns errors into Error objects with `.status`, and on a 401 for a signed-in
//                             user clears the token and fires `gy:unauthorized` so AuthContext can log out.
//
// Dev: vite proxies /api -> http://localhost:8000. For a separately hosted API set VITE_API_URL
// (e.g. VITE_API_URL=https://api.example.com) when building.
const API_ORIGIN = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')
const BASE = API_ORIGIN + '/api'
export const mediaUrl = (path) => !path ? '' : (/^https?:\/\//i.test(path) ? path : API_ORIGIN + path)
const TOKEN_KEY = 'gariyangu_token'
export const UNAUTHORIZED_EVENT = 'gy:unauthorized'

const getToken = () => { try { return localStorage.getItem(TOKEN_KEY) } catch { return null } }
const setToken = (t) => { try { t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY) } catch { /* storage unavailable */ } }

const NETWORK_ERROR = 'Cannot reach the server. Check your connection and that the backend is running.'

// Request interceptor: add the bearer token.
function withAuth(headers) {
  const token = getToken()
  return token ? { ...headers, Authorization: 'Bearer ' + token } : headers
}

// Response interceptor: parse the body, normalise errors, handle expired sessions.
async function handleResponse(res, hadToken, path, fallback) {
  const data = await res.json().catch(() => null) // empty / non-JSON body
  if (res.ok) return data
  if (res.status === 401 && hadToken && !path.startsWith('/auth/login')) {
    setToken(null)
    window.dispatchEvent(new Event(UNAUTHORIZED_EVENT))
  }
  const err = new Error(data?.error || `${fallback} (${res.status})`)
  err.status = res.status
  throw err
}

async function send(method, path, { body, form } = {}) {
  const headers = withAuth(body !== undefined ? { 'Content-Type': 'application/json' } : {})
  const hadToken = Boolean(headers.Authorization)
  let res
  try {
    res = await fetch(BASE + path, { method, headers, body: form || (body !== undefined ? JSON.stringify(body) : undefined) })
  } catch {
    throw new Error(NETWORK_ERROR)
  }
  return handleResponse(res, hadToken, path, form ? 'Upload failed' : 'Request failed')
}

const request = (method, path, body) => send(method, path, { body })
const get = (p) => request('GET', p)
const post = (p, b = {}) => request('POST', p, b)
const uploadRequest = (path, formData) => send('POST', path, { form: formData })

/* ---------------- auth ---------------- */
export async function login(email, password) {
  const { token, user } = await post('/auth/login', { email, password })
  setToken(token)
  return user
}
export async function register(data) {
  const { token, user } = await post('/auth/register', data)
  setToken(token)
  return user
}
export const logout = () => setToken(null)
export const getUser = () => get('/auth/me')

/* ---------------- cars ---------------- */
export const listCars = () => get('/cars')
export async function getCar(id) {
  try { return await get(`/cars/${id}`) } catch (e) { if (e.status === 404) return null; throw e }
}

/* ---------------- buyer: requests & offers ---------------- */
export const createRequest = (_buyerId, f) => post('/requests', f)
export const myRequests = () => get('/requests/mine')
export const updateRequest = (id, f) => request('PUT', `/requests/${id}`, f)
export const deleteRequest = (id) => request('DELETE', `/requests/${id}`)
export const closeRequest = (_buyerId, requestId) => post(`/requests/${requestId}/close`)
export const acceptOffer = (_buyerId, offerId) => post(`/offers/${offerId}/accept`)
export const declineOffer = (_buyerId, offerId) => post(`/offers/${offerId}/decline`)
export const addReview = (_buyerId, offerId, rating, comment) => post(`/offers/${offerId}/review`, { rating, comment })

/* ---------------- dealer ---------------- */
export const openRequests = () => get('/dealer/requests')
export const submitOffer = (_dealerId, data) => post('/dealer/offers', data)
export const withdrawOffer = (_dealerId, offerId) => post(`/dealer/offers/${offerId}/withdraw`)
export const dealerOffers = () => get('/dealer/offers')
export const dealerStats = () => get('/dealer/stats')
export const dealerListings = () => get('/dealer/listings')
export const saveListing = (_ownerId, data) =>
  data.id ? request('PUT', `/dealer/listings/${data.id}`, data) : post('/dealer/listings', data)
export const setListingStatus = (_ownerId, id, status) => post(`/dealer/listings/${id}/status`, { status })
export const deleteListing = (_ownerId, id) => request('DELETE', `/dealer/listings/${id}`)
export const uploadListingImages = (listingId, files) => {
  const form = new FormData()
  files.forEach((file) => form.append('images', file))
  return uploadRequest(`/dealer/listings/${listingId}/images`, form)
}
export const setPrimaryListingImage = (listingId, imageId) => post(`/dealer/listings/${listingId}/images/${imageId}/primary`)
export const deleteListingImage = (listingId, imageId) => request('DELETE', `/dealer/listings/${listingId}/images/${imageId}`)

/* ---------------- admin ---------------- */
export const allDealers = () => get('/admin/dealers')
export const reviewDealer = (userId, decision, reason = '') => post(`/admin/dealers/${userId}/review`, { decision, reason })
