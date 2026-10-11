import { Route, Routes } from 'react-router-dom'
import PortalLayout from '../../shared/Layout'
import { ErrorPage } from '../../shared/pages'
import Dashboard from './Dashboard'
import { Audit, DataProtection, Exports, Practice, RaterAnalytics, Settings } from './Misc'
import { Companies, Raters } from './People'
import RoundDetail from './RoundDetail'
import { RoundWizard, RoundsList } from './Rounds'

const LINKS = [
  { to: '/admin', label: 'Dashboard', end: true }, { to: '/admin/rounds', label: 'Rounds' }, { to: '/admin/companies', label: 'Companies' },
  { to: '/admin/raters', label: 'Raters' }, { to: '/admin/rater-quality', label: 'Rater quality' }, { to: '/admin/practice', label: 'Practice items' },
  { to: '/admin/exports', label: 'Exports' }, { to: '/admin/audit', label: 'Audit log' }, { to: '/admin/data', label: 'Data protection' }, { to: '/admin/settings', label: 'Settings' },
]

export default function AdminApp() {
  return (
    <PortalLayout title="Admin" links={LINKS}>
      <Routes>
        <Route index element={<Dashboard />} />
        <Route path="rounds" element={<RoundsList />} />
        <Route path="rounds/new" element={<RoundWizard />} />
        <Route path="rounds/:id/edit" element={<RoundWizard />} />
        <Route path="rounds/:id" element={<RoundDetail />} />
        <Route path="companies" element={<Companies />} />
        <Route path="raters" element={<Raters />} />
        <Route path="rater-quality" element={<RaterAnalytics />} />
        <Route path="practice" element={<Practice />} />
        <Route path="exports" element={<Exports />} />
        <Route path="audit" element={<Audit />} />
        <Route path="data" element={<DataProtection />} />
        <Route path="settings" element={<Settings />} />
        <Route path="*" element={<ErrorPage code={404} />} />
      </Routes>
    </PortalLayout>
  )
}
