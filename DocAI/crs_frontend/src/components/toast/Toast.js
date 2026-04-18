import { ToastContainer, toast } from 'react-toastify';
import 'react-toastify/dist/ReactToastify.css';
import './toast.css';

// 共通トースト表示関数
export function showToast(message, type) {
    if (type === 'warning') {
        type = 'bg-warn';
    } else if (type === 'error') {
        type = 'bg-err';
    } else {
        type = 'toast-info';
    }

    toast(message, {
        autoClose: false,
        closeOnClick: false,
        draggable: false,
        className: 'custom-toast' + ((' ' + type) || ''),
        position: 'top-right',
    });
}

// ToastContainerをアプリのルートで一度だけ配置
export function ToastRoot() {
    return <ToastContainer />;
}
