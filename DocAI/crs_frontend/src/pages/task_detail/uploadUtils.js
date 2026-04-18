/**
 * アップロードファイル/フォルダ管理のユーティリティ関数群
 *
 * 状態（State）構造:
 * - nodesById: { [id]: node } - ノードIDをキーとしたノード情報のマップ
 * - rootOrder: string[] - ルート直下のノードIDリスト（追加順）
 * - childrenOrderById: { [parentId]: string[] } - 各フォルダ直下の子ノードIDリスト（追加順）
 * - errors: array - エラー情報の配列
 *
 * ノード（node）構造:
 * - id: string - ノードの一意識別子（パス）
 * - name: string - 表示名
 * - kind: "file" | "folder" - ノードの種類
 * - parentId: string | null - 親ノードのID（ルートの場合はnull）
 * - collapsed: boolean - フォルダの開閉状態（フォルダの場合のみ）
 * - fileMeta: object - ファイルメタデータ（ファイルの場合のみ）
 *
 * 仕様:
 * - 同一階層で同名（file/folder問わず）はエラー（追加しない）
 * - 追加順を維持（ソートしない）
 * - フォルダは初期状態でcollapsed=true（閉じている）
 */

/**
 * 空の初期状態を作成
 *
 * @returns {object} 初期状態オブジェクト
 */
export function createEmptyState() {
    return {
        nodesById: {},
        rootOrder: [],
        childrenOrderById: {},
        errors: [],
    };
}

/**
 * パスを正規化（バックスラッシュをスラッシュに統一、前後の余白とスラッシュを削除）
 *
 * @param {string} p - 正規化するパス
 * @returns {string} 正規化されたパス
 */
export function normalizePath(p) {
    return String(p ?? "")
        .replace(/\\/g, "/")
        .replace(/^\/+/, "")
        .replace(/\/+$/, "")
        .trim();
}

/**
 * 相対パスから親パスを取得
 *
 * @param {string} relativePath - 相対パス
 * @returns {string | null} 親パス（ルートの場合はnull）
 */
export function getParentPath(relativePath) {
    const clean = normalizePath(relativePath);
    const idx = clean.lastIndexOf("/");
    if (idx < 0) return null;
    return clean.slice(0, idx);
}

/**
 * パスから最後のファイル/フォルダ名を取得
 *
 * @param {string} relativePath - 相対パス
 * @returns {string} ファイル/フォルダ名
 */

export function getNameFromPath(relativePath) {
    const clean = normalizePath(relativePath);
    const idx = clean.lastIndexOf("/");
    return idx < 0 ? clean : clean.slice(idx + 1);
}

/**
 * エラーを状態に追加（内部関数）
 *
 * @param {object} state - 現在の状態
 * @param {object} err - エラー情報
 * @returns {object} 更新された状態
 */
function pushError(state, err) {
    return { ...state, errors: [err, ...state.errors] };
}

/**
 * 親ノードに子ノードをリンク（内部関数）
 *
 * @param {object} state - 現在の状態
 * @param {string | null} parentId - 親ノードID
 * @param {string} childId - 子ノードID
 * @returns {object} 更新された状態
 */
function linkChild(state, parentId, childId) {
    if (parentId == null) {
        if (state.rootOrder.includes(childId)) return state;
        return { ...state, rootOrder: [...state.rootOrder, childId] };
    }
    const list = state.childrenOrderById[parentId] || [];
    if (list.includes(childId)) return state;
    return {
        ...state,
        childrenOrderById: { ...state.childrenOrderById, [parentId]: [...list, childId] },
    };
}

/**
 * 同一階層に同名のノードが存在するかチェック
 *
 * @param {object} state - 現在の状態
 * @param {string | null} parentId - 親ノードID
 * @param {string} name - チェックする名前
 * @returns {boolean} 同名が存在すればtrue
 */
export function siblingsHasSameName(state, parentId, name) {
    const ids = parentId == null ? state.rootOrder : state.childrenOrderById[parentId] || [];
    for (const id of ids) {
        const n = state.nodesById[id];
        if (n && n.name === name) return true;
    }
    return false;
}

/**
 * ノードを状態に挿入（内部関数）
 *
 * @param {object} state - 現在の状態
 * @param {object} node - 挿入するノード
 * @returns {object} 更新された状態
 */
function insertNode(state, node) {
    if (state.nodesById[node.id]) {
        return pushError(state, { type: "DUPLICATE_ID", parentId: node.parentId, name: node.name });
    }
    const next = {
        ...state,
        nodesById: { ...state.nodesById, [node.id]: node },
    };
    return linkChild(next, node.parentId, node.id);
}

/**
 * フォルダパスに必要な階層をすべて作成
 *
 * @param {object} state - 現在の状態
 * @param {string} folderPath - フォルダパス
 * @returns {object} { state: 更新された状態, lastFolderId: 最終フォルダID }
 */
export function ensureFolderChain(state, folderPath) {
    const clean = normalizePath(folderPath);
    if (!clean) return { state, lastFolderId: null };

    const parts = clean.split("/").filter(Boolean);
    if (parts.length === 0) return { state, lastFolderId: null };

    let currentParent = null;
    let currentPath = "";
    let s = state;

    for (const part of parts) {
        currentPath = currentPath ? `${currentPath}/${part}` : part;
        const folderId = currentPath;

        if (!s.nodesById[folderId]) {
            if (siblingsHasSameName(s, currentParent, part)) {
                s = pushError(s, { type: "DUPLICATE_NAME", parentId: currentParent, name: part });
                return { state: s, lastFolderId: null };
            }
            s = insertNode(s, {
                id: folderId,
                name: part,
                kind: "folder",
                parentId: currentParent,
                collapsed: true,
            });
        }
        currentParent = folderId;
    }

    return { state: s, lastFolderId: currentParent };
}

/**
 * 相対パスを使用してファイルを追加
 *
 * @param {object} state - 現在の状態
 * @param {string} relativePath - ファイルの相対パス
 * @param {object | null} fileMeta - ファイルメタデータ（size, type, lastModified, fileオブジェクト本体を含む）
 * @returns {object} 更新された状態
 */
export function addFileByPath(state, relativePath, fileMeta = null) {
    const clean = normalizePath(relativePath);
    if (!clean) return state;

    const name = getNameFromPath(clean);
    const parentId = getParentPath(clean);

    if (siblingsHasSameName(state, parentId, name)) {
        return pushError(state, { type: "DUPLICATE_NAME", parentId, name });
    }

    let s = state;

    if (parentId) {
        const r = ensureFolderChain(s, parentId);
        s = r.state;
        if (r.lastFolderId == null) return s;
    }

    return insertNode(s, {
        id: clean,
        name,
        kind: "file",
        parentId,
        fileMeta: fileMeta ?? undefined,
    });
}

/**
 * フォルダの開閉状態を切り替え
 *
 * @param {object} state - 現在の状態
 * @param {string} folderId - フォルダID
 * @returns {object} 更新された状態
 */
export function toggleFolder(state, folderId) {
    const n = state.nodesById[folderId];
    if (!n || n.kind !== "folder") return state;
    return {
        ...state,
        nodesById: {
            ...state.nodesById,
            [folderId]: { ...n, collapsed: !n.collapsed },
        },
    };
}

/**
 * 指定されたノードとその子孫をすべて削除
 *
 * @param {object} state - 現在の状態
 * @param {string} id - 削除するノードID
 * @returns {object} 更新された状態
 */
export function deleteSubtree(state, id) {
    const target = state.nodesById[id];
    if (!target) return state;

    const toDelete = new Set();
    const stack = [id];

    while (stack.length) {
        const cur = stack.pop();
        if (!cur || toDelete.has(cur)) continue;
        toDelete.add(cur);

        const node = state.nodesById[cur];
        if (node?.kind === "folder") {
            const kids = state.childrenOrderById[cur] || [];
            for (const k of kids) stack.push(k);
        }
    }

    const nextNodes = { ...state.nodesById };
    for (const delId of toDelete) delete nextNodes[delId];

    const nextRoot = state.rootOrder.filter((x) => !toDelete.has(x));

    const nextChildren = { ...state.childrenOrderById };

    if (target.parentId != null) {
        const list = nextChildren[target.parentId] || [];
        nextChildren[target.parentId] = list.filter((x) => !toDelete.has(x));
    }

    for (const delId of toDelete) delete nextChildren[delId];

    for (const [pid, list] of Object.entries(nextChildren)) {
        nextChildren[pid] = list.filter((x) => !toDelete.has(x));
    }

    return {
        ...state,
        nodesById: nextNodes,
        rootOrder: nextRoot,
        childrenOrderById: nextChildren,
    };
}

/**
 * 表示用の行データを生成（折り畳まれたフォルダの子は除外）
 *
 * @param {object} state - 現在の状態
 * @returns {array} 表示用行データの配列
 */
export function buildVisibleRows(state) {
    const rows = [];

    const walk = (id, depth) => {
        const node = state.nodesById[id];
        if (!node) return;
        rows.push({ id, depth, name: node.name, kind: node.kind, collapsed: node.collapsed });

        if (node.kind === "folder" && node.collapsed) return;
        const kids = state.childrenOrderById[id] || [];
        for (const k of kids) walk(k, depth + 1);
    };

    for (const id of state.rootOrder) walk(id, 0);
    return rows;
}

/**
 * サーバから受け取ったアップロードオブジェクトの配列を状態構造に変換
 *
 * @param {array} uploadObjects - DBから取得したアップロードオブジェクトの配列（full_path含む）
 * @returns {object} 変換された状態オブジェクト
 */
export function convertServerDataToState(uploadObjects) {
    if (!Array.isArray(uploadObjects) || uploadObjects.length === 0) {
        return createEmptyState();
    }

    const state = createEmptyState();

    // 親IDごとにグループ化
    const byParent = {};
    for (const obj of uploadObjects) {
        // フルパスとオブジェクト名称が同じ場合はルート直下とし, それ以外の場合は最後のスラッシュまでを親IDとする
        const pid = obj.full_path === obj.upload_object_name ? 'ROOT' : obj.full_path.slice(0, obj.full_path.lastIndexOf('/'));
        if (!byParent[pid]) byParent[pid] = [];
        byParent[pid].push(obj);
    }

    // upload_object_id → full_path のマッピングを作成
    const idToPath = {};
    for (const obj of uploadObjects) {
        idToPath[obj.upload_object_id] = obj.full_path;
    }

    // 各オブジェクトを状態に追加
    for (const obj of uploadObjects) {
        const path = obj.full_path;
        const name = obj.upload_object_name;
        const kind = obj.upload_object_type === 'folder' ? 'folder' : 'file';

        // パスから親パスを取得
        const lastSlashIdx = path.lastIndexOf('/');
        const parentId = lastSlashIdx < 0 ? null : path.slice(0, lastSlashIdx);

        // ノードを追加
        state.nodesById[path] = {
            id: path,
            name: name,
            kind: kind,
            parentId: parentId,
            collapsed: kind === 'folder' ? true : undefined,
        };
    }

    // 親子関係を構築
    // ルート要素を追加
    const rootObjects = byParent['ROOT'] || [];
    state.rootOrder = rootObjects.map(obj => obj.full_path);

    // 各親の子要素を追加
    for (const pid in byParent) {
        if (pid === 'ROOT') continue;
        // pidは既に親パス（文字列）なので、そのまま使用
        const children = byParent[pid] || [];
        state.childrenOrderById[pid] = children.map(obj => obj.full_path);
    }

    return state;
}

/**
 * 状態構造をサーバ送信用のアップロードオブジェクト配列に変換
 *
 * フロントエンドの階層構造（state）をDBに保存するための配列形式に変換する。
 * 各ノード（ファイル/フォルダ）をアップロードオブジェクトとして出力し、
 * 親子関係、表示順序、フルパス情報を含める。
 *
 * @param {object} state - 現在の状態（nodesById, rootOrder, childrenOrderById を含む）
 * @returns {array} サーバ送信用のアップロードオブジェクト配列
 */
export function convertStateToServerData(state) {
    const uploadObjects = [];

    /**
     * ノードIDから完全なパス文字列を再帰的に構築
     *
     * @param {string} nodeId - ノードID（パス）
     * @returns {string} ルートからの完全なパス（例: "folder1/folder2/file.txt"）
     */
    function buildPath(nodeId) {
        const node = state.nodesById[nodeId];
        // ノードが存在しない場合は空文字列を返却
        if (!node) return '';

        // ルート直下のノードの場合は名前のみを返却
        if (node.parentId === null) {
            return node.name;
        }

        // 親パスを再帰的に取得してノード名を結合
        const parentPath = buildPath(node.parentId);
        return `${parentPath}/${node.name}`;
    }

    /**
     * ノードを再帰的に処理してアップロードオブジェクトとして配列に追加
     *
     * @param {string} nodeId - 処理するノードID
     * @param {number} depth - ノードの深さ（0から開始）
     */
    function processNode(nodeId, depth = 0) {
        const node = state.nodesById[nodeId];
        // ノードが存在しない場合は処理をスキップ
        if (!node) return;

        // ノードの完全なパスを構築
        const fullPath = buildPath(nodeId);

        // アップロードオブジェクトを作成して配列に追加
        uploadObjects.push({
            upload_object_name: node.name,
            upload_object_type: node.kind,
            full_path: fullPath,
        });

        // 子ノードがある場合は再帰的に処理
        const children = state.childrenOrderById[nodeId];
        if (children && children.length > 0) {
            children.forEach((childId) => {
                // 子ノードを処理（親パスとして現在のノードID、display_orderは子ノード内で0から連番）
                processNode(childId, depth + 1);
            });
        }
    }

    // ルートノードから順に処理を開始（ルート直下のdisplay_orderは配列のindexを使用）
    state.rootOrder.forEach((rootId) => {
        processNode(rootId, 0);
    });

    return uploadObjects;
}
