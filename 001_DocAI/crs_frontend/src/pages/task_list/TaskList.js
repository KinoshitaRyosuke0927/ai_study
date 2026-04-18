import { useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import Header from '../../components/header/Header.js';
import { showToast } from '../../components/toast/Toast';
import { API_ENDPOINTS, SYSTEM_ERROR_MESSAGE, TASK_STATE_NAMES } from '../../utils/constants.js';
import { formatDateTime, generateTaskName } from '../../utils/helpers.js';
import '../../utils/css/util.css';
import './tasklist.css';

export default function TaskList() {
  const navigate = useNavigate();
  const location = useLocation();
  const [tasks, setTasks] = useState([]);
  const fromLogin = location.state?.fromLogin ?? false;
  const [sortKey, setSortKey] = useState(() => {
    if (fromLogin) return 'update_at';
    return sessionStorage.getItem('taskList_sortKey') || null;
  });
  const [sortDir, setSortDir] = useState(() => {
    if (fromLogin) return 'desc';
    return sessionStorage.getItem('taskList_sortDir') || 'asc';
  });
  const storedUserId = sessionStorage.getItem('user_id');
  const storedUserName = sessionStorage.getItem('user_name');
  const userId = storedUserId ? Number(storedUserId) : null;
  const userName = location.state?.userName ?? storedUserName;

  useEffect(() => {
    if (!userId || !userName) {
      navigate('/login', { replace: true });
    }
  }, [userId, userName, navigate]);

  // タスク一覧取得
  useEffect(() => {
    const fetchTaskList = async () => {
      try {
        const res = await fetch(API_ENDPOINTS.TASK_LIST, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ user_id: userId })
        });

        if (!res.ok) {
          showToast(SYSTEM_ERROR_MESSAGE, 'error');
          return;
        }

        const result = await res.json();
        if (Array.isArray(result?.messages) && result.messages.length > 0) {
          showToast(result.messages[0].message, result.messages[0].message_type);
        }

        if (Array.isArray(result?.task_list)) {
          setTasks(result.task_list);
        }
      } catch (e) {
        showToast(SYSTEM_ERROR_MESSAGE, 'error');
      }
    };

    if (userId) {
      fetchTaskList();
    }
  }, [userId]);

  // タスククリック時の処理
  const handleTaskClick = async (taskId) => {
    try {
      const res = await fetch(API_ENDPOINTS.TASK_INQUIRY, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task_id: taskId })
      });

      if (!res.ok) {
        showToast(SYSTEM_ERROR_MESSAGE, 'error');
        return;
      }

      const result = await res.json();
      if (Array.isArray(result?.messages) && result.messages.length > 0) {
        showToast(result.messages[0].message, result.messages[0].message_type);
        // タスクの情報がない場合は遷移しない
        if (!result.task_detail) {
          return;
        }
      }

      // タスク詳細画面へ遷移（レスポンス情報を保持）
      navigate('/task-detail', {
        state: {
          userName,
          taskDetail: result
        }
      });
    } catch (e) {
      showToast(SYSTEM_ERROR_MESSAGE, 'error');
    }
  };

  // タスク新規作成
  const handleCreateTask = async () => {
    try {
      const taskName = generateTaskName();
      const res = await fetch(API_ENDPOINTS.TASK_CREATE, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, task_name: taskName })
      });

      if (!res.ok) {
        showToast(SYSTEM_ERROR_MESSAGE, 'error');
        return;
      }

      const result = await res.json();
      if (Array.isArray(result?.messages) && result.messages.length > 0) {
        showToast(result.messages[0].message, result.messages[0].message_type);
      } else {
        // 詳細画面へ遷移（作成したタスクの情報を保持）
        navigate('/task-detail', {
          state: {
            userName,
            taskDetail: result
          }
        });
      }
    } catch (e) {
      showToast(SYSTEM_ERROR_MESSAGE, 'error');
    }
  };

  const handleLogout = () => {
    sessionStorage.removeItem('user_id');
    sessionStorage.removeItem('user_name');
    navigate('/login', { replace: true });
  };

  // ログイン直後のソート初期値をsessionStorageに保存
  useEffect(() => {
    if (fromLogin) {
      sessionStorage.setItem('taskList_sortKey', 'update_at');
      sessionStorage.setItem('taskList_sortDir', 'desc');
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ソート処理
  const handleSort = (key) => {
    if (sortKey === key) {
      const newDir = sortDir === 'asc' ? 'desc' : 'asc';
      setSortDir(newDir);
      sessionStorage.setItem('taskList_sortDir', newDir);
    } else {
      setSortKey(key);
      setSortDir('asc');
      sessionStorage.setItem('taskList_sortKey', key);
      sessionStorage.setItem('taskList_sortDir', 'asc');
    }
  };

  const sortedTasks = [...tasks].sort((a, b) => {
    if (!sortKey) return 0;
    let valA = a[sortKey] ?? '';
    let valB = b[sortKey] ?? '';
    if (sortKey === 'update_at') {
      valA = valA ? new Date(valA).getTime() : 0;
      valB = valB ? new Date(valB).getTime() : 0;
    } else if (typeof valA === 'string') {
      valA = valA.toLowerCase();
      valB = valB.toLowerCase();
    }
    if (valA < valB) return sortDir === 'asc' ? -1 : 1;
    if (valA > valB) return sortDir === 'asc' ? 1 : -1;
    return 0;
  });

  // ソートアイコン表示
  const sortIcon = (key) => {
    if (sortKey !== key) return <span className="sort-icon sort-icon-neutral">↕</span>;
    return <span className="sort-icon sort-icon-active">{sortDir === 'asc' ? '↑' : '↓'}</span>;
  };

  if (!userId || !userName) return null;

  return (
    <>
      <Header pageTitle="タスク一覧" showUser={true} userName={userName} onLogout={handleLogout} />
      <div className="task-list-page-container bg-base">
        <div className="header-spacer"></div>
        <main>
          {/* タスク一覧セクション */}
          <div className="tasklist-review-section">
            <div className="tasklist-review-header">
              <span className="tasklist-section-title">タスク一覧</span>
              <button className="btn bg-info tasklist-create-btn" onClick={handleCreateTask}>
                + 新規作成
              </button>
            </div>

            {/* テーブルカード */}
            <div className="tasklist-review-table-card">
              {tasks.length === 0 ? (
                <div className="tasklist-review-empty">
                  タスクはまだありません
                </div>
              ) : (
                <table className="tasklist-review-table">
                  <thead>
                    <tr>
                      <th className="tasklist-review-col-name tasklist-th-sortable" onClick={() => handleSort('task_name')}>
                        タスク名 {sortIcon('task_name')}
                      </th>
                      <th className="tasklist-review-col-status tasklist-th-sortable" onClick={() => handleSort('task_state_id')}>
                        ステータス {sortIcon('task_state_id')}
                      </th>
                      <th className="tasklist-review-col-date tasklist-th-sortable" onClick={() => handleSort('update_at')}>
                        最終更新日時 {sortIcon('update_at')}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {sortedTasks.map((task) => (
                      <tr
                        key={task.task_id}
                        className="tasklist-review-row"
                        onClick={() => handleTaskClick(task.task_id)}
                        style={{ cursor: 'pointer' }}
                      >
                        <td className="tasklist-review-col-name">
                          {task.task_name}
                        </td>
                        <td className="tasklist-review-col-status">
                          <span className={`tasklist-review-status tasklist-review-status-${task.task_state_id}`}>
                            {TASK_STATE_NAMES[task.task_state_id] || '不明'}
                          </span>
                        </td>
                        <td className="tasklist-review-col-date">{formatDateTime(task.update_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>

        </main>
      </div>
    </>
  );
}
