"""管理用コマンド(backend/ で実行)。

    python -m app.cli create-user --login yamada --name "山田 太郎" [--admin]
    python -m app.cli set-password --login yamada
    python -m app.cli delete-user --login yamada
    python -m app.cli import-course ../content/statistics-basics [--author yamada] [--replace]
    python -m app.cli db-state | db-start | db-stop       (Azure の MySQL サーバーの状態確認・起動・停止)
    python -m app.cli db-idle-stop [--idle-minutes 60]    (一定時間アクセスが無ければ DB を停止)
"""

from __future__ import annotations

import argparse
import getpass
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select

from app.config.settings import get_settings
from app.infra.db import new_session
from app.infra.db_power import STATE_READY, DbPowerError, get_db_power
from app.models import User
from app.services.activity_service import last_activity
from app.services.auth_service import create_user, hash_password
from app.services.notebook_import import NotebookFormatError, import_course


def _read_password(provided: str | None) -> str:
    """
    パスワードを取得する(未指定なら対話入力)

    Args
    -----------------
    - provided: str | None,             コマンド引数で渡されたパスワード

    Returns
    -----------------
    - password: str,                    パスワード

    """
    # 引数で渡されていればそれを使う
    if provided:
        return provided
    # 対話入力で2回入力させて一致を確認
    first = getpass.getpass("パスワード: ")
    second = getpass.getpass("パスワード(確認): ")
    if first != second or not first:
        sys.exit("パスワードが一致しないか、空です")
    # 入力されたパスワードを返却
    return first


def cmd_create_user(args: argparse.Namespace) -> None:
    """
    ユーザを作成する

    Args
    -----------------
    - args: argparse.Namespace,         コマンド引数

    """
    # パスワードを取得
    password = _read_password(args.password)
    # ユーザを作成して確定
    with new_session() as session:
        try:
            user = create_user(session, args.login, args.name, password, args.admin)
        except ValueError as e:
            sys.exit(str(e))
        session.commit()
        # 結果を表示
        role = "管理者" if user.is_admin else "ユーザ"
        print(f"作成しました: {user.login_name}({user.display_name} / {role})")


def cmd_set_password(args: argparse.Namespace) -> None:
    """
    ユーザのパスワードを変更する

    Args
    -----------------
    - args: argparse.Namespace,         コマンド引数

    """
    with new_session() as session:
        # 対象ユーザを検索
        user = session.scalar(select(User).where(User.login_name == args.login))
        if user is None:
            sys.exit(f"ユーザ '{args.login}' が見つかりません")
        # 新しいパスワードを設定して確定
        user.password_hash = hash_password(_read_password(args.password))
        session.commit()
        print(f"パスワードを変更しました: {user.login_name}")


def cmd_delete_user(args: argparse.Namespace) -> None:
    """
    ユーザを削除する(受講記録も削除される)

    Args
    -----------------
    - args: argparse.Namespace,         コマンド引数

    """
    with new_session() as session:
        # 対象ユーザを検索
        user = session.scalar(select(User).where(User.login_name == args.login))
        if user is None:
            sys.exit(f"ユーザ '{args.login}' が見つかりません")
        # 削除して確定(提出・進捗は外部キーの連動削除で消える)
        session.delete(user)
        session.commit()
        print(f"削除しました: {args.login}")


def cmd_import_course(args: argparse.Namespace) -> None:
    """
    講座フォルダ(course.json + .ipynb)を取り込む

    Args
    -----------------
    - args: argparse.Namespace,         コマンド引数

    """
    with new_session() as session:
        # 作成者の指定があればユーザを検索
        author = None
        if args.author:
            author = session.scalar(select(User).where(User.login_name == args.author))
            if author is None:
                sys.exit(f"ユーザ '{args.author}' が見つかりません")
        # 講座を取り込んで確定(書き方の誤りがあれば何も登録しない)
        try:
            course = import_course(session, Path(args.course_dir), author=author, replace=args.replace)
        except NotebookFormatError as e:
            session.rollback()
            sys.exit(f"取り込みに失敗しました: {e}")
        session.commit()
        # 結果を表示
        print(f"取り込みました: {course.title}({course.slug} / 単元 {len(course.units)} / {course.status})")


def cmd_db_power(args: argparse.Namespace) -> None:
    """
    DB(Azure の MySQL フレキシブルサーバー)の状態確認・起動・停止を行う

    Args
    -----------------
    - args: argparse.Namespace,         コマンド引数(action: state / start / stop)

    """
    # 操作を実行して結果を表示
    try:
        power = get_db_power()
        if args.action == "start":
            power.start()
            print("DB の起動を要求しました(起動まで数分かかります)")
        elif args.action == "stop":
            power.stop()
            print("DB の停止を要求しました")
        else:
            print(power.state())
    except DbPowerError as e:
        sys.exit(str(e))


def cmd_db_idle_stop(args: argparse.Namespace) -> None:
    """
    一定時間アクセスが無ければ DB を停止する(Container Apps のスケジュールジョブから定期的に実行する)

    Args
    -----------------
    - args: argparse.Namespace,         コマンド引数(idle_minutes)

    """
    idle = timedelta(minutes=args.idle_minutes or get_settings().db_idle_stop_minutes)
    try:
        power = get_db_power()
        # 起動中でなければ何もしない(停止済み・起動処理中など)
        state = power.state()
        if state != STATE_READY:
            print(f"DB は {state} のため何もしません")
            return
        # 最終アクセス日時を確認(記録が無ければ未使用として扱う)
        with new_session() as session:
            last = last_activity(session)
        now = datetime.now(timezone.utc)
        if last is not None and now - last < idle:
            print(f"最終アクセスから {int((now - last).total_seconds() // 60)} 分のため停止しません")
            return
        # 一定時間使われていないので停止する
        power.stop()
        print("一定時間アクセスが無いため、DB の停止を要求しました")
    except DbPowerError as e:
        sys.exit(str(e))


def main() -> None:
    """
    コマンドライン引数を解釈してサブコマンドを実行する
    """
    # 引数の定義
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(required=True)
    # create-user
    p = sub.add_parser("create-user", help="ユーザを作成する")
    p.add_argument("--login", required=True, help="ログイン名")
    p.add_argument("--name", required=True, help="表示名")
    p.add_argument("--password", help="パスワード(省略時は対話入力)")
    p.add_argument("--admin", action="store_true", help="管理者にする")
    p.set_defaults(func=cmd_create_user)
    # set-password
    p = sub.add_parser("set-password", help="パスワードを変更する")
    p.add_argument("--login", required=True, help="ログイン名")
    p.add_argument("--password", help="新しいパスワード(省略時は対話入力)")
    p.set_defaults(func=cmd_set_password)
    # delete-user
    p = sub.add_parser("delete-user", help="ユーザを削除する(受講記録も削除)")
    p.add_argument("--login", required=True, help="ログイン名")
    p.set_defaults(func=cmd_delete_user)
    # import-course
    p = sub.add_parser("import-course", help="講座フォルダを取り込む")
    p.add_argument("course_dir", help="course.json のある講座フォルダ")
    p.add_argument("--author", help="作成者のログイン名")
    p.add_argument("--replace", action="store_true", help="同じ識別名の講座を置き換える")
    p.set_defaults(func=cmd_import_course)
    # db-state / db-start / db-stop
    for action, label in (("state", "状態確認"), ("start", "起動"), ("stop", "停止")):
        p = sub.add_parser(f"db-{action}", help=f"DB の{label}(Azure の MySQL サーバー)")
        p.set_defaults(func=cmd_db_power, action=action)
    # db-idle-stop
    p = sub.add_parser("db-idle-stop", help="一定時間アクセスが無ければ DB を停止する")
    p.add_argument("--idle-minutes", type=int, default=None, help="この時間(分)アクセスが無ければ停止(既定は設定値)")
    p.set_defaults(func=cmd_db_idle_stop)
    # 実行
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
