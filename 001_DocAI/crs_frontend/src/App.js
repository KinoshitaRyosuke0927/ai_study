import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { ToastRoot } from './components/toast/Toast';
import Login from './pages/login/Login';
import TaskDetail from './pages/task_detail/TaskDetail';
import TaskList from './pages/task_list/TaskList';
import './utils/css/util.css';

// アプリケーションのルーティング設定
function App() {
  return (
    <BrowserRouter>
      {/* トースト通知のルートコンテナ */}
      <ToastRoot />
      <Routes>
        <Route path="/login"       element={<Login />} />
        <Route path="/task-list"   element={<TaskList />} />
        <Route path="/task-detail" element={<TaskDetail />} />
        {/* 未定義パスはログイン画面へリダイレクト */}
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
