import { BrowserRouter } from 'react-router-dom'
import AppRoutes from './AppRoutes.tsx'
import AuthProvider from './auth/AuthContext.tsx'

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  )
}

export default App
