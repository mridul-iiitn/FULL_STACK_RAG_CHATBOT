import { Routes, Route } from 'react-router-dom';
import LoginPage from './pages/LoginPage';
import RegisterPage from './pages/RegisterPage';
import ChatPage from './pages/ChatPage';
import { useState, useEffect } from 'react';

function App() {
  const [theme, setTheme] = useState('dark');

  // Theme toggle function ab yahan, parent component mein hai
  const toggleTheme = () => {
    setTheme(prevTheme => (prevTheme === 'dark' ? 'light' : 'dark'));
  };

  useEffect(() => {
    const root = window.document.documentElement;
    root.classList.remove('light', 'dark');
    root.classList.add(theme);
  }, [theme]);

  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      {/* Hum theme aur toggleTheme ko props ke zariye ChatPage ko bhej rahe hain */}
      <Route path="/" element={<ChatPage theme={theme} toggleTheme={toggleTheme} />} />
    </Routes>
  );
}

export default App;