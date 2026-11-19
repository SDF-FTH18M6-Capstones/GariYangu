import { createContext, useContext, useState, useCallback, useEffect } from 'react'
import * as api from './api.js'


const AuthContext = createContext(null)
const KEY = 'gariyangu_user'

const readStored = () => {
  try { return JSON.parse(localStorage.getItem(KEY)) } catch { return null }
}
const store = (u) => {
  try { u ? localStorage.setItem(KEY, JSON.stringify(u)) : localStorage.removeItem(KEY) } catch { /* ignore */ }
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(readStored)

  const set = (u) => { setUser(u); store(u); return u }

  const login = async (email, password) => set(await api.login(email, password))
  const register = (data) => api.register(data) 
  const verifySignup = async (email, code) => set(await api.verifySignup(email, code))
  const logout = () => { api.logout(); set(null) }
  
  const refresh = useCallback(async () => {
    if (!readStored()) return null
    try { return set(await api.getUser()) } catch (e) { return e.status === 401 ? set(null) : readStored() } 
  }, [])

  
  useEffect(() => {
    const onUnauthorized = () => set(null)
    window.addEventListener(api.UNAUTHORIZED_EVENT, onUnauthorized)
    return () => window.removeEventListener(api.UNAUTHORIZED_EVENT, onUnauthorized)
  }, [])

  
  useEffect(() => { refresh() }, [refresh])

  return <AuthContext.Provider value={{ user, login, register, verifySignup, logout, refresh }}>{children}</AuthContext.Provider>
}

export const useAuth = () => useContext(AuthContext)

export const homeFor = (user) =>
  user?.role === 'dealer' ? '/dealer' : user?.role === 'admin' ? '/admin/dealers' : '/my-offers'
