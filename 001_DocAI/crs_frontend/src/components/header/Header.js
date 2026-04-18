import { useNavigate } from 'react-router-dom';
import '../../lib/destyle.css-master/destyle.min.css';
import '../../utils/css/util.css';
import './header.css';

export default function Header({ pageTitle, userName, onLogout, showUser = true }) {
  const navigate = useNavigate();

  const handleLogoClick = () => {
    if (showUser) {
      navigate('/task-list');
    }
  };

  return (
    <header className='header-body'>
      <div
        className={`header-left ${showUser ? 'header-left-clickable' : ''}`}
        onClick={handleLogoClick}
      >
        <div className='header-brand-icon'>D</div>
        <span className='header-brand-name'>DocAI</span>
      </div>
      <div className='header-right'>
        {showUser && userName && (
          <div className='header-user-badge'>
            <div className='header-user-avatar'>{userName.charAt(0)}</div>
            <span className='header-user-name'>{userName}</span>
          </div>
        )}
        {showUser && (
          <button
            className='header-logout-btn'
            onClick={onLogout}
            title="ログアウト"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 3c1.66 0 3 1.34 3 3s-1.34 3-3 3-3-1.34-3-3 1.34-3 3-3zm0 14.2c-2.5 0-4.71-1.28-6-3.22.03-1.99 4-3.08 6-3.08 1.99 0 5.97 1.09 6 3.08-1.29 1.94-3.5 3.22-6 3.22z" fill="currentColor"/>
            </svg>
          </button>
        )}
      </div>
    </header>
  );
}
