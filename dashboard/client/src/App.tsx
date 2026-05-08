import { AppProvider } from './context/AppContext';
import Dashboard from './pages/Dashboard';

function App() {
  return (
    <AppProvider>
      <Dashboard />
    </AppProvider>
  );
}

export default App;
