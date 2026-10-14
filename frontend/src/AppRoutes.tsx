import { Navigate, Route, Routes } from 'react-router-dom'
import ProtectedRoute from './auth/ProtectedRoute.tsx'
import BookAppointment from './pages/BookAppointment.tsx'
import Confirmation from './pages/Confirmation.tsx'
import Login from './pages/Login.tsx'
import PatientDetails from './pages/PatientDetails.tsx'
import QueueStatus from './pages/QueueStatus.tsx'

function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/login" replace />} />
      <Route path="/login" element={<Login />} />
      <Route element={<ProtectedRoute />}>
        <Route path="/patient-details" element={<PatientDetails />} />
        <Route path="/book-appointment" element={<BookAppointment />} />
        <Route path="/queue-status" element={<QueueStatus />} />
        <Route path="/confirmation" element={<Confirmation />} />
      </Route>
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  )
}

export default AppRoutes
