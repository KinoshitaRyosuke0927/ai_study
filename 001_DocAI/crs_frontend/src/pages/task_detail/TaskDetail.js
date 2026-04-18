import { useEffect, useMemo, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import DocAIResultPanel from './DocAIResultPanel.js';
import Dialog from '../../components/dialog/dialog.js';
import Header from '../../components/header/Header.js';
import Loading from '../../components/loading/Loading';
import { showToast } from '../../components/toast/Toast';
import { API_ENDPOINTS, POLLING_INTERVAL_MS, SYSTEM_ERROR_MESSAGE, TASK_STATE_NAMES } from '../../utils/constants.js';
import '../../utils/css/util.css';
import './taskDetail.css';
import {
  addFileByPath,
  buildVisibleRows,
  convertServerDataToState,
  convertStateToServerData,
  createEmptyState,
  deleteSubtree,
  toggleFolder
} from './uploadUtils.js';

export default function TaskDetail() {
  const location = useLocation();
  const navigate = useNavigate();
  const storedUserId = sessionStorage.getItem('user_id');
  const storedUserName = sessionStorage.getItem('user_name');
  const userId = storedUserId ? Number(storedUserId) : null;
  const userName = location.state?.userName ?? storedUserName;
  // 画面の自動更新間隔(ms)
  const pollingInterval = POLLING_INTERVAL_MS

  // タスク詳細情報をstateで管理
  const [taskDetail, setTaskDetail] = useState(location.state?.taskDetail?.task_detail || null);
  const [displayObjectInfo, setDisplayObjectInfo] = useState(location.state?.taskDetail?.display_object_info || []);
  const taskId = taskDetail?.task_id || null;
  const taskName = taskDetail?.task_name || '';
  const taskStateId = taskDetail?.task_state_id || null;

  const [state, setState] = useState(() => createEmptyState());
  const [displayState, setDisplayState] = useState(() => createEmptyState());
  const [selectedRowId, setSelectedRowId] = useState(null);
  const [showBackToListDialog, setShowBackToListDialog] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [showLoading, setShowLoading] = useState(false);
  const [loadingMessage, setLoadingMessage] = useState('処理中...');
  const [loadingProgress, setLoadingProgress] = useState(null);
  const [showSelectMenu, setShowSelectMenu] = useState(false);

  // タスク名編集用のstate
  const [isEditingName, setIsEditingName] = useState(false);
  const [editingTaskName, setEditingTaskName] = useState('');

  // タスク削除ダイアログ用のstate
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);

  const fileInputRef = useRef(null);
  const folderInputRef = useRef(null);
  const selectMenuRef = useRef(null);
  const visibleRows = useMemo(() => buildVisibleRows(state), [state]);

  const displayVisibleRows = useMemo(() => buildVisibleRows(displayState), [displayState]);

  // display_object_infoからfull_pathをキーとしたresult_textのマッピングを作成
  const resultTextMap = useMemo(() => {
    const map = {};
    if (Array.isArray(displayObjectInfo)) {
      displayObjectInfo.forEach(obj => {
        map[obj.full_path] = obj.result_text || '';
      });
    }
    return map;
  }, [displayObjectInfo]);

  // 選択された行のresult_textを取得
  const selectedResultText = selectedRowId ? (resultTextMap[selectedRowId] || '') : '';

  // display_object_infoが変更されたときにdisplayStateを更新し、task_state_id=4の場合は先頭ファイルを自動選択
  useEffect(() => {
    if ((taskStateId === 2 || taskStateId === 4) && Array.isArray(displayObjectInfo) && displayObjectInfo.length > 0) {
      const newState = convertServerDataToState(displayObjectInfo);

      // task_state_id=4の場合、先頭のファイルを探索して自動選択
      if (taskStateId === 4) {
        // 先頭のファイルを探索し、パス上のフォルダを展開
        const findFirstFileAndExpandPath = (state) => {
          const foldersToExpand = [];

          function findFile(nodeIds) {
            if (!nodeIds || nodeIds.length === 0) return null;

            for (const id of nodeIds) {
              const node = state.nodesById[id];
              if (!node) continue;

              if (node.kind === 'file') {
                return { fileId: id, foldersToExpand };
              }

              if (node.kind === 'folder') {
                const childIds = state.childrenOrderById[id] || [];
                if (childIds.length > 0) {
                  foldersToExpand.push(id);
                  const result = findFile(childIds);
                  if (result) return result;
                  foldersToExpand.pop();
                }
              }
            }
            return null;
          }

          return findFile(state.rootOrder);
        };

        const result = findFirstFileAndExpandPath(newState);
        if (result) {
          // フォルダを展開（不変性を保つ）
          const updatedNodesById = { ...newState.nodesById };
          result.foldersToExpand.forEach(folderId => {
            if (updatedNodesById[folderId]) {
              updatedNodesById[folderId] = {
                ...updatedNodesById[folderId],
                collapsed: false
              };
            }
          });
          newState.nodesById = updatedNodesById;

          // displayStateを更新してからファイルを選択
          setDisplayState(newState);
          setSelectedRowId(result.fileId);
        } else {
          // ファイルが見つからない場合
          setDisplayState(newState);
          setSelectedRowId(null);
        }
      } else {
        // task_state_id=2の場合
        setDisplayState(newState);
        setSelectedRowId(null);
      }
    } else {
      setDisplayState(createEmptyState());
      setSelectedRowId(null);
    }
  }, [taskStateId, displayObjectInfo]);

  // ユーザ情報が存在しない場合はログイン画面に遷移
  useEffect(() => {
    if (!userId || !userName) {
      navigate('/login', { replace: true });
    }
  }, [userId, userName, navigate]);

  // ページ全体でのドラッグ&ドロップのデフォルト動作を防ぐ
  // アップロードエリア以外でファイルをドロップした際にブラウザでファイルが開かれるのを防止
  useEffect(() => {
    const preventDefaults = (e) => {
      e.preventDefault();
      e.stopPropagation();
    };

    document.addEventListener('dragover', preventDefaults);
    document.addEventListener('drop', preventDefaults);

    return () => {
      document.removeEventListener('dragover', preventDefaults);
      document.removeEventListener('drop', preventDefaults);
    };
  }, []);

  // エラーメッセージをトーストで表示（新規エラーのみ）
  // TODO メッセージは仮置き
  const prevErrorCountRef = useRef(0);
  useEffect(() => {
    // 新しくエラーが追加された場合のみ表示
    if (state.errors.length > prevErrorCountRef.current) {
      const newErrors = state.errors.slice(0, state.errors.length - prevErrorCountRef.current);
      newErrors.forEach(error => {
        const message = error.type === 'DUPLICATE_NAME'
          ? `同じ階層に同名のファイル/フォルダが既に存在します: ${error.name}`
          : error.type === 'DUPLICATE_ID'
            ? `重複するパスが検出されました: ${error.name}`
            : '不明なエラーが発生しました';
        showToast(message, 'error');
      });
    }
    prevErrorCountRef.current = state.errors.length;
  }, [state.errors]);

  // プルダウンメニューの外側クリックで閉じる処理
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (selectMenuRef.current && !selectMenuRef.current.contains(event.target)) {
        setShowSelectMenu(false);
      }
    };

    if (showSelectMenu) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [showSelectMenu]);

  // 初期表示処理
  useEffect(() => {
    // 選択したタスクの状態が「翻訳済」の場合は翻訳結果のファイル情報を取得する
    if (taskStateId === 4 && taskId) {
      getTaskDetail();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ポーリング処理
  // タスク状態が「翻訳中」の場合はpollingIntervalごとにタスク詳細画面更新処理を実行
  useEffect(() => {
    if (taskStateId === 2 && taskId) {
      const intervalId = setInterval(async () => {
        // タスク状態を取得
        const updatedTaskStateId = await getTaskState();
        // タスク状態が「翻訳済」になった場合は翻訳結果を取得
        if (updatedTaskStateId === 4) {
          await getTaskDetail();
        }
      }, pollingInterval);

      return () => {
        clearInterval(intervalId);
      };
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [taskStateId, taskId]);

  // ユーザ情報が取得できなかった場合はnullをセット
  if (!userId || !userName) return null;

  // ログアウト処理
  const handleLogout = () => {
    sessionStorage.removeItem('user_id');
    sessionStorage.removeItem('user_name');
    navigate('/login', { replace: true });
  };

  // 一覧に戻る処理
  const handleBackToList = () => {
    // タスク状態が翻訳中・中断状態の場合、かつ、アップロードされたファイルが存在する場合は、確認ダイアログを表示
    if (visibleRows.length > 0 && (taskStateId === 1 || taskStateId === 3)) {
      setShowBackToListDialog(true);
    } else {
      navigate('/task-list', { state: { userName } });
    }
  };

  // 一覧に戻る確認ダイアログで「一覧に戻る」を選択した場合
  const handleConfirmBackToList = () => {
    setShowBackToListDialog(false);
    navigate('/task-list', { state: { userName } });
  };

  // 一覧に戻る確認ダイアログで「キャンセル」を選択した場合
  const handleCancelBackToList = () => {
    setShowBackToListDialog(false);
  };

  // タスク状態取得処理
  // 画面上でのユーザ操作を許容するためロード状態は設定しない
  const getTaskState = async () => {
    try {
      // タスク状態を取得
      const res_state = await fetch(API_ENDPOINTS.TASK_INQUIRY, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task_id: taskId })
      });
      // 通信に失敗した場合
      if (!res_state.ok) {
        showToast(SYSTEM_ERROR_MESSAGE, 'error');
        return null;
      }
      // レスポンスをJSON形式に変換
      const result_state = await res_state.json();
      // レスポンスにメッセージが設定されている場合
      if (Array.isArray(result_state?.messages) && result_state.messages.length > 0) {
        // トーストメッセージとして表示
        showToast(result_state.messages[0].message, result_state.messages[0].message_type);
        // エラーの場合は画面遷移せず処理を終了
        if (result_state.messages[0].message_type === 'error') {
          return null;
        }
      }
      // タスクの情報が取得できた場合はセットする
      if (result_state?.task_detail) {
        setTaskDetail(result_state.task_detail);
        setDisplayObjectInfo(result_state.display_object_info);
        // 更新後のtask_state_idを返す
        return result_state.task_detail.task_state_id;
      }
      return null;
    } catch (e) {
      showToast(SYSTEM_ERROR_MESSAGE, 'error');
      return null;
    }
  }

  // 翻訳結果取得処理
  // 翻訳結果取得中のユーザ操作を防ぐためロード状態を設定する
  const getTaskDetail = async () => {
    // ロード状態設定
    setLoadingMessage('最新のタスク情報を取得しています。');
    setShowLoading(true);
    try {
      // 翻訳結果ファイルの情報を取得
      const res = await fetch(API_ENDPOINTS.TASK_READ, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task_id: taskId })
      });
      // 通信に失敗した場合
      if (!res.ok) {
        showToast(SYSTEM_ERROR_MESSAGE, 'error');
        return;
      }
      // レスポンスをJSON形式に変換
      const result = await res.json();
      // レスポンスにメッセージが設定されている場合
      if (Array.isArray(result?.messages) && result.messages.length > 0) {
        // トーストメッセージとして表示
        showToast(result.messages[0].message, result.messages[0].message_type);
        if (result.messages[0].message_type === 'error') {
          return;
        }
      }
      // タスクの詳細情報が取得できた場合はセットする
      if (result?.task_detail) {
        setTaskDetail(result.task_detail);
        setDisplayObjectInfo(result.display_object_info);
      }
    } catch (e) {
      showToast(SYSTEM_ERROR_MESSAGE, 'error');
    } finally {
      // ロード状態解除
      setShowLoading(false);
      setLoadingMessage(null);
    }
  }

  // 「画面を更新する」ボタンクリック時処理
  const handleRefreshTaskInfo = async () => {
    try {
      // タスクIDが取得できない場合はエラー
      if (!taskId) {
        showToast('タスクIDが取得できませんでした。', 'error');
        return;
      }
      // タスク状態取得処理呼び出し
      const updatedTaskStateId = await getTaskState();
      // タスク状態が「翻訳済」の場合
      if (updatedTaskStateId === 4) {
        // 翻訳結果取得処理呼び出し
        await getTaskDetail();
      }
      // メッセージ表示
      showToast('最新のタスク情報を反映しました。', 'info');
    } catch (e) {
      showToast(SYSTEM_ERROR_MESSAGE, 'error');
    }
  };

  // 変換可能なファイル形式かどうか確認する共通処理
  const validateUploadObjects = async (uploadObjects) => {
    const res = await fetch(API_ENDPOINTS.FILE_FILTER, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', },
      body: JSON.stringify({ target_data: uploadObjects }),
    });
    // レスポンス取得
    const data = await res.json();
    // フィルタ結果返却
    return data.filter_result
  };

  // ---- ファイル選択処理 ----
  async function onPickFiles(e) {
    setLoadingMessage('アップロード中です。画面を閉じずにお待ちください。');
    setLoadingProgress(0);
    setShowLoading(true);
    try {
      // 登録されたファイルからなる配列作成
      const files = Array.from(e.target.files || []);
      // ファイルをアルファベット順に並び替え
      files.sort((a, b) => a.name.localeCompare(b.name));

      setLoadingProgress(20);

      // 変換対象として登録可能かを確認するための処理
      // 確認用データ作成
      const uploadObjects = files.map(f => ({
        upload_object_name: f.name,
        upload_object_type: 'file',
        full_path: f.name,
        file_size: f.size,
      }));

      setLoadingProgress(40);

      // データフィルタ
      const filter_result = await validateUploadObjects(uploadObjects);

      setLoadingProgress(60);
      const errorFileName = files.filter((file, index) => !filter_result[index]).map(file => `・${file.name}`).join('\n');

      // フィルタ結果のチェック
      const allFalse = filter_result.every(result => result === false);
      const hasFalse = filter_result.some(result => result === false);
      if (allFalse) {
        showToast('登録可能なファイルがありません。アップロード可能なファイルは「.py」形式のファイルに限ります。', 'error');
      } else if (hasFalse) {
        showToast(`登録できない形式のファイルが含まれていたため、登録対象から除外しました。\n除外されたファイル:\n${errorFileName}`, 'warning');
      }

      // 変換対象として適切なファイルのみ抽出
      const filtered_files = files.filter((file, index) => filter_result[index]);

      setLoadingProgress(80);

      // すべてのデータをstateにセット
      setState((prev) => {
        let s = { ...prev, errors: [] };
        for (const f of filtered_files) {
          s = addFileByPath(s, f.name, { size: f.size, type: f.type, lastModified: f.lastModified, file: f });
        }
        return s;
      });

      setLoadingProgress(100);

      // オブジョクト初期化
      e.target.value = "";
    } finally {
      setShowLoading(false);
      setLoadingProgress(null);
    }
  }

  // ---- フォルダ選択処理（webkitdirectory）----
  async function onPickFolder(e) {
    setLoadingMessage('アップロード中です。画面を閉じずにお待ちください。');
    setLoadingProgress(0);
    setShowLoading(true);
    try {
      // 登録されたファイルからなる配列作成
      const files = Array.from(e.target.files || []);

      setLoadingProgress(10);

      // ファイルをパス順に並び替え（各階層でフォルダ→ファイルの順、アルファベット順）
      files.sort((a, b) => {
        const pathA = (a.webkitRelativePath || a.name).split('/');
        const pathB = (b.webkitRelativePath || b.name).split('/');

        // 各階層を比較
        const minLength = Math.min(pathA.length, pathB.length);
        for (let i = 0; i < minLength; i++) {
          // 最後のセグメントかどうかを判定（ファイル名かフォルダ名か）
          const isLastA = i === pathA.length - 1;
          const isLastB = i === pathB.length - 1;

          // 同じ階層で片方がフォルダ、片方がファイルの場合
          if (isLastA !== isLastB) {
            return isLastA ? 1 : -1; // フォルダを先に
          }

          // 同じ種類（両方フォルダまたは両方ファイル）の場合、アルファベット順
          const comparison = pathA[i].localeCompare(pathB[i]);
          if (comparison !== 0) {
            return comparison;
          }
        }

        // パスの長さが異なる場合、短い方を先に（フォルダが先）
        return pathA.length - pathB.length;
      });

      setLoadingProgress(30);

      // 変換対象として登録可能かを確認するための処理
      // 確認用データ作成
      const uploadObjects = files.map(f => ({
        upload_object_name: f.name,
        upload_object_type: 'file',
        full_path: f.webkitRelativePath || f.name,
        file_size: f.size,
      }));
      // データフィルタ
      const filter_result = await validateUploadObjects(uploadObjects);
      const errorFileName = files.filter((file, index) => !filter_result[index]).map(file => `・${file.name}`).join('\n');

      // フィルタ結果のチェック
      const allFalse = filter_result.every(result => result === false);
      const hasFalse = filter_result.some(result => result === false);
      if (allFalse) {
        showToast('登録可能なファイルがありません。アップロード可能なファイルは「.py」形式のファイルに限ります。', 'error');
      } else if (hasFalse) {
        showToast(`登録できない形式のファイルが含まれていたため、登録対象から除外しました。\n除外されたファイル:\n${errorFileName}`, 'warning');
      }

      // 変換対象として適切なファイルのみ抽出
      const filtered_files = files.filter((file, index) => filter_result[index]);

      setLoadingProgress(90);

      // すべてのデータをstateにセット
      setState((prev) => {
        let s = { ...prev, errors: [] };
        for (const f of filtered_files) {
          const rel = f.webkitRelativePath || f.name;
          s = addFileByPath(s, rel, { size: f.size, type: f.type, lastModified: f.lastModified, file: f });
        }
        return s;
      });

      setLoadingProgress(100);

      // オブジェクト初期化
      e.target.value = "";
    } finally {
      setShowLoading(false);
      setLoadingProgress(null);
    }
  }

  // ---- Drag & Drop処理（ファイル/フォルダ）----
  // ドラッグエリアに入ったときの処理
  function onDragEnter(e) {
    // 要素ごとのデフォルト動作を抑制する
    e.preventDefault();
    // ドラッグ状態をONにする
    setIsDragging(true);
  }

  // ドラッグエリアから出たときの処理
  function onDragLeave(e) {
    // 要素ごとのデフォルト動作を抑制する
    e.preventDefault();
    // relatedTargetがアップロードエリアの子要素でない場合のみfalseにする
    if (!e.currentTarget.contains(e.relatedTarget)) {
      // ドラッグ状態をOFFにする
      setIsDragging(false);
    }
  }

  function onDragOver(e) {
    e.preventDefault();
    e.dataTransfer.dropEffect = "copy";
  }

  async function onDrop(e) {
    // 要素ごとのデフォルト動作を抑制する
    e.preventDefault();
    // ドラッグ状態をOFFにする
    setIsDragging(false);
    // 待機アニメーション開始
    setLoadingMessage('アップロード中です。画面を閉じずにお待ちください。');
    setLoadingProgress(0);
    setShowLoading(true);
    try {
      // ドラッグされたアイテムを取得
      const items = Array.from(e.dataTransfer.items || []);
      // 非同期処理の前にすべてのentryを取得しておく
      const entries = items.map(item => item.webkitGetAsEntry?.()).filter(entry => entry !== null);

      setLoadingProgress(10);

      // entriesをフォルダとファイルに分離してそれぞれアルファベット順に並び替え
      const folders = entries.filter(entry => entry.isDirectory);
      const files = entries.filter(entry => entry.isFile);
      folders.sort((a, b) => a.name.localeCompare(b.name));
      files.sort((a, b) => a.name.localeCompare(b.name));
      // フォルダ → ファイルの順に並べ替え
      const sortedEntries = [...folders, ...files];
      setLoadingProgress(20);
      // 登録対象のすべてのファイルを再帰的に取得
      const allFiles = [];
      for (const entry of sortedEntries) {
        if (entry.isFile) {
          // ファイルの場合
          const file = await new Promise((resolve) => {
            entry.file(resolve, () => resolve(null));
          });
          if (file) {
            // 親のフォルダが存在しない場合はファイル名をセット
            file.relativePath = file.name;
            allFiles.push(file);
          }
        } else if (entry.isDirectory) {
          // フォルダの場合：フォルダ内のすべてのファイルを取得
          const filesFromFolder = await getAllFilesFromDirectory(entry, entry.name);
          allFiles.push(...filesFromFolder);
        }
      }

      setLoadingProgress(40);

      // 登録対象のデータが存在するのみ処理
      if (allFiles.length > 0) {
        // 変換対象として登録可能かを確認するための処理
        // 確認用データ作成
        const uploadObjects = allFiles.map(f => ({
          upload_object_name: f.name,
          upload_object_type: 'file',
          full_path: f.relativePath || f.name,
          file_size: f.size,
        }));

        setLoadingProgress(60);

        // データフィルタ
        const filter_result = await validateUploadObjects(uploadObjects);

        setLoadingProgress(80);

        // フィルタ結果のチェック
        const allFalse = filter_result.every(result => result === false);
        const hasFalse = filter_result.some(result => result === false);
        const errorFileName = uploadObjects.filter((object, index) => !filter_result[index]).map(object => `・${object.upload_object_name}`).join('\n');

        if (allFalse) {
          showToast('登録可能なファイルがありません。アップロード可能なファイルは「.py」形式のファイルに限ります。', 'error');
        } else if (hasFalse) {
          showToast(`登録できない形式のファイルが含まれていたため、登録対象から除外しました。\n除外されたファイル:\n${errorFileName}`, 'warning');
        }

        // 変換対象として適切なファイルのみ抽出
        const filtered_files = allFiles.filter((file, index) => filter_result[index]);

        // すべてのデータを順次stateにセット
        setState((prev) => {
          let s = { ...prev, errors: [] };
          for (const f of filtered_files) {
            const path = f.relativePath || f.name;
            s = addFileByPath(s, path, {
              size: f.size,
              type: f.type,
              lastModified: f.lastModified,
              file: f,
            });
          }
          return s;
        });

        setLoadingProgress(100);
      }
    } finally {
      setShowLoading(false);
      setLoadingProgress(null);
    }
  }

  // フォルダ内のすべてのファイルを再帰的に取得する処理
  async function getAllFilesFromDirectory(dirEntry, basePath = '') {
    // 入れ物用意
    const files = [];
    // 対象のフォルダを取得
    const reader = dirEntry.createReader();
    // 対象のフォルダ配下のデータをすべて取得する処理
    const readEntries = () => {
      return new Promise((resolve, reject) => {
        reader.readEntries(
          (entries) => resolve(entries),
          (error) => reject(error)
        );
      });
    };

    // フォルダ配下のデータを取得
    let entries = await readEntries();
    // すべてのデータに対して処理
    while (entries.length > 0) {
      // 取得したデータをフォルダとファイルに分離
      const folders = entries.filter(entry => entry.isDirectory);
      const fileEntries = entries.filter(entry => entry.isFile);
      // それぞれをアルファベット順にソート
      folders.sort((a, b) => a.name.localeCompare(b.name));
      fileEntries.sort((a, b) => a.name.localeCompare(b.name));
      // フォルダを先に処理
      for (const entry of folders) {
        // フォルダのパスを作成
        const subPath = basePath ? `${basePath}/${entry.name}` : entry.name;
        // フォルダ配下のファイルを再帰的に取得
        const subFiles = await getAllFilesFromDirectory(entry, subPath);
        files.push(...subFiles);
      }
      // その後ファイルを処理
      for (const entry of fileEntries) {
        // ファイルを取得
        const file = await new Promise((resolve, reject) => {
          entry.file(resolve, reject);
        });
        // フルパスを作成
        file.relativePath = basePath ? `${basePath}/${file.name}` : file.name;
        // 配列に追加
        files.push(file);
      }
      // 次の登録データを取得
      entries = await readEntries();
    }

    // ファイルの一覧を返却
    return files;
  }

  // ---- UI操作 ----
  function onToggle(id) {
    setState((prev) => toggleFolder(prev, id));
  }

  function onDelete(id) {
    setState((prev) => deleteSubtree(prev, id));
  }

  // display_object_info用のUI操作
  function onDisplayToggle(id) {
    setDisplayState((prev) => toggleFolder(prev, id));
  }

  // 行を選択する処理
  function onSelectRow(id) {
    setSelectedRowId(id);
  }

  // ---- タスク名編集処理 ----
  function handleStartEditName() {
    setEditingTaskName(taskName);
    setIsEditingName(true);
  }

  function handleCancelEditName() {
    setIsEditingName(false);
    setEditingTaskName('');
  }

  async function handleSaveTaskName() {
    const trimmed = editingTaskName.trim();
    if (!trimmed) {
      showToast('タスク名を入力してください。', 'error');
      return;
    }
    if (trimmed === taskName) {
      setIsEditingName(false);
      return;
    }
    setLoadingMessage('タスク名を更新しています。');
    setShowLoading(true);
    try {
      const res = await fetch(API_ENDPOINTS.TASK_UPDATE, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task_id: taskId, task_name: trimmed }),
      });
      if (!res.ok) {
        showToast(SYSTEM_ERROR_MESSAGE, 'error');
        return;
      }
      const result = await res.json();
      if (Array.isArray(result?.messages) && result.messages.length > 0) {
        showToast(result.messages[0].message, result.messages[0].message_type);
        if (result.messages[0].message_type === 'error') return;
      }
      if (result?.task_detail) {
        setTaskDetail(result.task_detail);
      }
      setIsEditingName(false);
      showToast('タスク名を更新しました。', 'info');
    } catch (e) {
      showToast(SYSTEM_ERROR_MESSAGE, 'error');
    } finally {
      setShowLoading(false);
      setLoadingMessage(null);
    }
  }

  // ---- タスク削除処理 ----
  function handleDeleteTask() {
    setShowDeleteDialog(true);
  }

  function handleCancelDelete() {
    setShowDeleteDialog(false);
  }

  async function handleConfirmDelete() {
    setShowDeleteDialog(false);
    setLoadingMessage('タスクを削除しています。');
    setShowLoading(true);
    try {
      const res = await fetch(API_ENDPOINTS.TASK_DELETE, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task_id: taskId }),
      });
      if (!res.ok) {
        showToast(SYSTEM_ERROR_MESSAGE, 'error');
        return;
      }
      const result = await res.json();
      if (Array.isArray(result?.messages) && result.messages.length > 0) {
        showToast(result.messages[0].message, result.messages[0].message_type);
        if (result.messages[0].message_type === 'error') return;
      }
      navigate('/task-list', { state: { userName } });
    } catch (e) {
      showToast(SYSTEM_ERROR_MESSAGE, 'error');
    } finally {
      setShowLoading(false);
      setLoadingMessage(null);
    }
  }

  // ---- 送信処理 ----
  async function handleSubmit() {
    setLoadingMessage('翻訳準備中です。画面を閉じずにお待ちください。');
    setLoadingProgress(0);
    setShowLoading(true);
    try {
      // リクエストの整合性最終チェック
      // stateから登録対象のメタデータ作成
      const uploadObjects = convertStateToServerData(state);

      setLoadingProgress(10);

      // データフィルタ
      const filter_result = await validateUploadObjects(uploadObjects);

      setLoadingProgress(20);
      // 変換対象として適切なファイルが1つでも存在する場合
      if (filter_result.includes(false)) {
        showToast('翻訳対象のファイルに不適切なファイルが含まれるため、データの登録に失敗しました。現在登録されているデータを削除して、再度翻訳データの登録からお試しください。', 'error');
        return;
      }

      // ファイルのメタデータを追加
      const formData = new FormData();
      formData.append('task_id', taskId ? taskId.toString() : '');
      formData.append('user_id', userId.toString());
      formData.append('metadata', JSON.stringify(uploadObjects));

      setLoadingProgress(30);

      // ファイル本体を追加
      Object.values(state.nodesById).forEach((node) => {
        if (node.kind === 'file' && node.fileMeta?.file) {
          // full_pathをキーとしてファイルを追加
          formData.append('target_file_list', node.fileMeta.file, node.id);
        }
      });

      setLoadingProgress(50);

      // 変換対象データの登録
      try {
        // API送信
        const response = await fetch(API_ENDPOINTS.TASK_TRANSLATE, {
          method: 'POST',
          body: formData
        });

        setLoadingProgress(80);

        // レスポンス取得
        const data = await response.json();

        setLoadingProgress(90);
        // メッセージ表示
        if (Array.isArray(data?.messages) && data.messages.length > 0) {
          // メッセージ種別取得
          const messageType = data.messages?.[0]?.message_type ?? 'error';
          // メッセージ内容取得
          const message = data.messages?.[0]?.message ?? SYSTEM_ERROR_MESSAGE;
          // 翻訳処理が正常に登録された場合
          if (messageType === 'info') {
            setLoadingProgress(95);
            // タスク状態を再度取得して画面を更新
            await getTaskState();
            setLoadingProgress(100);
          }
          // メッセージ表示
          showToast(message, messageType);
        }
      } catch (error) {
        // データの登録時に予期せぬエラーが発生した場合
        showToast(SYSTEM_ERROR_MESSAGE, 'error');
      }
    } finally {
      setShowLoading(false);
      setLoadingProgress(null);
    }
  }

  return (
    <>
      <Loading show={showLoading} message={loadingMessage} progress={loadingProgress} />
      <Header pageTitle="タスク詳細" showUser={true} userName={userName} onLogout={handleLogout} />

      {/*TODO： DBから文言を取得したほうがより良いと思うので、後日対応したい*/}
      <Dialog
        isOpen={showBackToListDialog}
        title={`確認`}
        message={`まだ 翻訳を開始していません\n今一覧に戻ると、アップロード状況は初期化されます\n一覧に戻りますか？`}
        titleToConfirm={`◀ 一覧に戻る`}
        colorToConfirm={`bg-warn`}
        titleToCancel={`キャンセル`}
        onConfirm={handleConfirmBackToList}
        onCancel={handleCancelBackToList}
      />
      <Dialog
        isOpen={showDeleteDialog}
        title={`タスクの削除`}
        message={`「${taskName}」を削除します。\nこの操作は取り消せません。\n削除しますか？`}
        titleToConfirm={`削除する`}
        colorToConfirm={`bg-err`}
        titleToCancel={`キャンセル`}
        onConfirm={handleConfirmDelete}
        onCancel={handleCancelDelete}
      />

      <div className='task-detail-page-container bg-base'>
        <div className="header-spacer"></div>

        {/* ページヘッダー：タスク名 + ステータスバッジ + 編集・削除 */}
        <div className="task-detail-page-header">
          <button className="task-detail-back-arrow" onClick={handleBackToList} title="一覧に戻る">
            ←
          </button>

          {isEditingName ? (
            /* 編集モード */
            <div className="task-name-edit-area">
              <div className="task-name-input-wrapper">
                <input
                  className="task-name-edit-input"
                  value={editingTaskName}
                  onChange={e => setEditingTaskName(e.target.value)}
                  maxLength={255}
                  autoFocus
                  onKeyDown={e => { if (e.key === 'Enter') handleSaveTaskName(); if (e.key === 'Escape') handleCancelEditName(); }}
                />
                {editingTaskName && (
                  <button className="task-name-clear-btn" onClick={() => setEditingTaskName('')} tabIndex={-1} title="入力内容をクリア">
                    ×
                  </button>
                )}
              </div>
              <button className="btn bg-info txt-other task-name-action-btn" onClick={handleSaveTaskName}>保存</button>
              <button className="btn bg-warn task-name-action-btn" onClick={handleCancelEditName}>キャンセル</button>
            </div>
          ) : (
            /* 表示モード */
            <>
              <span className="task-detail-title-text">{taskName || 'タスク名が取得できませんでした'}</span>
              {taskStateId && (
                <span className={`tasklist-review-status tasklist-review-status-${taskStateId}`}>
                  {TASK_STATE_NAMES[taskStateId] || '不明'}
                </span>
              )}
              <button className="task-name-edit-btn" onClick={handleStartEditName} title="タスク名を編集">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04a1 1 0 000-1.41l-2.34-2.34a1 1 0 00-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z" fill="currentColor"/>
                </svg>
              </button>
            </>
          )}

          {/* 削除ボタン（翻訳中は非活性） */}
          <button
            className="task-delete-btn"
            onClick={handleDeleteTask}
            disabled={taskStateId === 2}
            title={taskStateId === 2 ? '翻訳中のタスクは削除できません' : 'タスクを削除'}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z" fill="currentColor"/>
            </svg>
          </button>
        </div>

        <main>
          {/* grid左カラム */}
          <div className="task-detail-left-column">
            {/* task_state_idが1（準備中）または3（中断）の場合のみアップロード用のUIを表示 */}
            {(taskStateId === 1 || taskStateId === 3) && (
              <section className={`upload-area radius-l task-detail-upload-area-section ${isDragging ? 'dragover' : ''}`} onDragEnter={onDragEnter} onDragLeave={onDragLeave} onDragOver={onDragOver} onDrop={onDrop}>
                <div className='upload-area-inner'>
                  <svg className="upload-area-svg-icon" width="52" height="52" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M19.35 10.04C18.67 6.59 15.64 4 12 4C9.11 4 6.6 5.64 5.35 8.04C2.34 8.36 0 10.91 0 14c0 3.31 2.69 6 6 6h13c2.76 0 5-2.24 5-5 0-2.64-2.05-4.78-4.65-4.96zM14 13v4h-4v-4H7l5-5 5 5h-3z" fill="currentColor"/>
                  </svg>
                  <div className='upload-info txt-base-on fs-md'>翻訳するプログラムファイル および ファイル群（フォルダ）をドロップ</div>
                  <div className='upload-info txt-base-on fs-md'>あるいは</div>
                  <div className='upload-select-dropdown' ref={selectMenuRef}>
                    <button
                      className='btn bg-info txt-other'
                      onClick={() => setShowSelectMenu(!showSelectMenu)}
                    >
                      選択する ▼
                    </button>
                    {showSelectMenu && (
                      <div className='upload-select-menu'>
                        <button
                          className='upload-select-menu-item txt-base-on fs-md'
                          onClick={() => {
                            setShowSelectMenu(false);
                            fileInputRef.current?.click();
                          }}
                        >
                          ファイルを選択する
                        </button>
                        <button
                          className='upload-select-menu-item txt-base-on fs-md'
                          onClick={() => {
                            setShowSelectMenu(false);
                            folderInputRef.current?.click();
                          }}
                        >
                          フォルダを選択する
                        </button>
                      </div>
                    )}
                  </div>
                  <input
                    ref={fileInputRef}
                    type='file'
                    multiple
                    onChange={onPickFiles}
                    style={{ display: 'none' }}
                  />
                  <input
                    ref={folderInputRef}
                    type='file'
                    multiple
                    /* @ts-ignore */
                    webkitdirectory=""
                    /* @ts-ignore */
                    directory=""
                    onChange={onPickFolder}
                    style={{ display: 'none' }}
                  />
                </div>
              </section>
            )}
            {/* task_state_idが2（翻訳中）の場合のみ翻訳中である旨を示すメッセージを表示 */}
            {(taskStateId === 2) && (
              <section className='upload-area radius-l task-detail-upload-area-section'>
                <div className='upload-area-inner'>
                  <div className="upload-area-spinner">
                    {[...Array(8)].map((_, i) => (
                      <div key={i} className={`upload-area-dot upload-area-dot-${i + 1}`}></div>
                    ))}
                  </div>
                  <div className='upload-info txt-base-on fs-md'>翻訳中です</div>
                  <div className='upload-info txt-base-on fs-md'>しばらくお待ちください</div>
                </div>
              </section>
            )}
            {/* task_state_idが4の場合のresult_text表示エリア */}
            {taskStateId === 4 && (
              <section className='result-area'>
                {displayObjectInfo.some(obj => obj.upload_object_type === 'file') ? (
                  selectedResultText ? (
                    <DocAIResultPanel markdownText={selectedResultText} />
                  ) : (
                    <div className='result-text-area radius-l'>
                      <div className='result-text-placeholder'>
                        ファイルを選択すると翻訳結果が表示されます
                      </div>
                    </div>
                  )
                ) : (
                  <div className='result-text-area radius-l'>
                    <div className='result-text-placeholder'>
                      翻訳するファイルが存在しません。システム管理者に問い合わせください
                    </div>
                  </div>
                )}
              </section>
            )}
          </div>
          {/* grid右カラム */}
          <div className="task-detail-right-column">
            {/* アップロードファイルカード */}
            <div className="upload-list-card">
              <div className='upload-list-title-area'>
                <div className='upload-list-title-row'>
                  <span className="upload-list-card-icon">📁</span>
                  <div className='upload-list-title-text txt-base-on bold'>アップロード一覧</div>
                </div>
              </div>
              <section className='upload-list'>
                {/* task_state_idが1または3の場合はアップロードしたファイルを表示 */}
                {(taskStateId === 1 || taskStateId === 3) && (
                  <div className='upload-list-container'>
                    {visibleRows.length === 0 ? (
                      <div className='upload-list-empty txt-base-on fs-md'>アップロードされたファイルはありません</div>
                    ) : (
                      <div className='upload-list-rows'>
                        {visibleRows.map((row) => (
                          <Row
                            key={row.id}
                            row={row}
                            onToggle={() => onToggle(row.id)}
                            onDelete={() => onDelete(row.id)}
                          />
                        ))}
                      </div>
                    )}
                  </div>
                )}
                {/* task_state_idが2または4の場合はdisplay_object_infoの情報を表示 */}
                {(taskStateId === 2 || taskStateId === 4) && (
                  <div className='upload-list-container'>
                    {displayVisibleRows.length === 0 ? (
                      <div className='upload-list-empty txt-base-on fs-md'>表示するファイルがありません</div>
                    ) : (
                      <div className='upload-list-rows' style={{ flex: taskStateId === 4 ? '1' : '1' }}>
                        {displayVisibleRows.map((row) => (
                          <DisplayRow
                            key={row.id}
                            row={row}
                            onToggle={() => {
                              onDisplayToggle(row.id);
                              setSelectedRowId(null);
                            }}
                            onSelect={() => onSelectRow(row.id)}
                            isSelected={selectedRowId === row.id}
                          />
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </section>
            </div>

            {/* アクションボタン群 */}
            <div className='task-detail-buttons'>
              {(taskStateId === 1 || taskStateId === 3) && (
                <button className='btn bg-info txt-other' onClick={handleSubmit} disabled={visibleRows.length === 0}>翻訳を開始する</button>
              )}
              {(taskStateId === 2) && (
                <button className='btn bg-info txt-other' onClick={handleRefreshTaskInfo}>画面を更新する</button>
              )}
            </div>
          </div>
        </main>
      </div>
    </>
  );
}


function Row({ row, onToggle, onDelete }) {
  const indentPx = row.depth * 20;

  return (
    <div
      className="upload-row"
      onClick={row.kind === "folder" ? onToggle : undefined}
      style={{ cursor: row.kind === "folder" ? 'pointer' : 'default' }}
    >
      <div className="upload-row-name">
        <div className="upload-row-indent" style={{ width: indentPx }} />

        {row.kind === "folder" ? (
          <button
            className="upload-row-toggle-btn"
            onClick={(e) => { e.stopPropagation(); onToggle(); }}
            title="フォルダを開閉"
          >
            <img
              src={row.collapsed ? "/img/closed_icon.svg" : "/img/open_icon.svg"}
              alt={row.kind === "folder" ? (row.collapsed ? "フォルダ（閉）" : "フォルダ（開）") : "ファイル"}
              className="upload-row-img-icon"
            />
          </button>
        ) : (
          <div className="upload-row-icon-placeholder" />
        )}

        <div className="upload-row-icon" title={row.kind === "folder" ? "フォルダ" : "ファイル"}>
          <img
            src={
              row.kind === "folder"
                ? (row.collapsed
                  ? "/img/folder_close_icon.png"
                  : "/img/folder_open_icon.png")
                : "/img/file_icon.png"
            }
            alt={row.kind === "folder" ? (row.collapsed ? "フォルダ（閉）" : "フォルダ（開）") : "ファイル"}
            className="upload-row-img-icon"
          />
        </div>

        <div className="upload-row-name-text txt-base-on fs-md">{row.name}</div>
      </div>

      <div className="upload-row-actions">
        <button
          className="txt-base-on bold fs-lg"
          onClick={(e) => { e.stopPropagation(); onDelete(); }}
        >
          ×
        </button>
      </div>
    </div>
  );
}

/* display_object_info用の表示コンポーネント（削除ボタンなし） */
function DisplayRow({ row, onToggle, onSelect, isSelected }) {
  const indentPx = row.depth * 20;

  return (
    <div
      className={`upload-row ${isSelected ? 'upload-row-selected' : ''}`}
      onClick={row.kind === "folder" ? onToggle : (onSelect ? onSelect : undefined)}
      style={{ cursor: 'pointer' }}
    >
      <div className="upload-row-name">
        <div className="upload-row-indent" style={{ width: indentPx }} />

        {row.kind === "folder" ? (
          <button
            className="upload-row-toggle-btn"
            onClick={(e) => { e.stopPropagation(); onToggle(); }}
            title="フォルダを開閉"
          >
            <img
              src={row.collapsed ? "/img/closed_icon.svg" : "/img/open_icon.svg"}
              alt={row.kind === "folder" ? (row.collapsed ? "フォルダ（閉）" : "フォルダ（開）") : "ファイル"}
              className="upload-row-img-icon"
            />
          </button>
        ) : (
          <div className="upload-row-icon-placeholder" />
        )}

        <div className="upload-row-icon" title={row.kind === "folder" ? "フォルダ" : "ファイル"}>
          <img
            src={
              row.kind === "folder"
                ? (row.collapsed
                  ? "/img/folder_close_icon.png"
                  : "/img/folder_open_icon.png")
                : "/img/file_icon.png"
            }
            alt={row.kind === "folder" ? (row.collapsed ? "フォルダ（閉）" : "フォルダ（開）") : "ファイル"}
            className="upload-row-img-icon"
          />
        </div>

        <div className="upload-row-name-text txt-base-on fs-md">{row.name}</div>
      </div>
    </div>
  );
}
