import { Navigate, Route, Routes } from 'react-router-dom'
import { DialogProvider } from './components/ConfirmDialog'
import Layout from './components/Layout'
import ProtectedRoute from './components/ProtectedRoute'
import Account from './pages/Account'
import Admin from './pages/Admin'
import CheatSheet from './pages/CheatSheet'
import Coach from './pages/Coach'
import CoachCandidate from './pages/CoachCandidate'
import CoachReport from './pages/CoachReport'
import Dashboard from './pages/Dashboard'
import Debrief from './pages/Debrief'
import Decoder from './pages/Decoder'
import Demo from './pages/Demo'
import Interview from './pages/Interview'
import Join from './pages/Join'
import Lab from './pages/Lab'
import Login from './pages/Login'
import OrgSettings from './pages/OrgSettings'
import Report, { SharedReport } from './pages/Report'
import Reverse, { ReverseSetup } from './pages/Reverse'
import Setup from './pages/Setup'
import Signup from './pages/Signup'
import Stories from './pages/Stories'

export default function App() {
  return (
    <DialogProvider>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/signup" element={<Signup />} />
        {/* Public: the decoder works without an account and its results are shareable. */}
        <Route path="/decode" element={<Decoder standalone />} />
        <Route path="/decode/:token" element={<Decoder standalone />} />
        <Route path="/shared/:token" element={<SharedReport />} />
        <Route
          element={
            <ProtectedRoute>
              <Layout />
            </ProtectedRoute>
          }
        >
          <Route index element={<Dashboard />} />
          <Route path="setup" element={<Setup />} />
          <Route path="account" element={<Account />} />
          <Route path="admin" element={<Admin />} />
          <Route path="interview/:id" element={<Interview />} />
          <Route path="report/:id" element={<Report />} />
          <Route path="report/:id/cheatsheet" element={<CheatSheet />} />
          <Route path="stories" element={<Stories />} />
          <Route path="decoder" element={<Decoder />} />
          <Route path="decoder/:token" element={<Decoder />} />
          <Route path="debrief" element={<Debrief />} />
          <Route path="lab" element={<Lab />} />
          <Route path="reverse" element={<ReverseSetup />} />
          <Route path="reverse/:id" element={<Reverse />} />
          {/* Organizations and the sales demo (T-166): the API 404s anyone not allowed. */}
          <Route path="demo" element={<Demo />} />
          <Route path="coach" element={<Coach />} />
          <Route path="coach/:orgId/candidates/:candidateId" element={<CoachCandidate />} />
          <Route path="coach/:orgId/candidates/:candidateId/report/:sessionId" element={<CoachReport />} />
          <Route path="org/:orgId/settings" element={<OrgSettings />} />
          <Route path="join/:token" element={<Join />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </DialogProvider>
  )
}
