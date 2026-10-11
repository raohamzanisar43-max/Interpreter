import { Route, Routes } from 'react-router-dom'
import { ProtectedRoute } from './shared/auth'
import { ErrorPage, Forgot, Home, InviteAccept, Login, Privacy, ResetPassword, Terms } from './shared/pages'
import AdminApp from './portals/admin/AdminApp'
import CompanyApp from './portals/company/CompanyApp'
import InterpreterApp, { EntryLink } from './portals/interpreter/InterpreterApp'
import RaterApp from './portals/rater/RaterApp'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/login" element={<Login />} />
      <Route path="/forgot" element={<Forgot />} />
      <Route path="/reset/:token" element={<ResetPassword />} />
      <Route path="/invite/:token" element={<InviteAccept />} />
      <Route path="/privacy" element={<Privacy />} />
      <Route path="/terms" element={<Terms />} />
      <Route path="/i/:token" element={<EntryLink />} />
      <Route path="/interpret/*" element={<InterpreterApp />} />
      <Route path="/admin/*" element={<ProtectedRoute role="admin"><AdminApp /></ProtectedRoute>} />
      <Route path="/company/*" element={<ProtectedRoute role="company"><CompanyApp /></ProtectedRoute>} />
      <Route path="/rater/*" element={<ProtectedRoute role="rater"><RaterApp /></ProtectedRoute>} />
      <Route path="/403" element={<ErrorPage code={403} />} />
      <Route path="*" element={<ErrorPage code={404} />} />
    </Routes>
  )
}
