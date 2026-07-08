import { useState } from 'react'
import LoginScreen from './components/LoginScreen'
import HomeScreen from './components/HomeScreen'

type Screen = 'login' | 'home'

function App() {
  const [screen, setScreen] = useState<Screen>('login')
  const [userName, setUserName] = useState('')

  if (screen === 'home') {
    return <HomeScreen userName={userName} onLogout={() => setScreen('login')} />
  }
  return (
    <LoginScreen
      onLogin={(name) => {
        setUserName(name)
        setScreen('home')
      }}
    />
  )
}

export default App
