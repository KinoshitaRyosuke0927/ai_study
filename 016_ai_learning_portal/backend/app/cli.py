"""管理用コマンド(backend/ で実行)。

    python -m app.cli create-user --login yamada --name "山田 太郎" [--admin]
    python -m app.cli set-password --login yamada
    python -m app.cli delete-user --login yamada
    python -m app.cli import-course ../content/statistics-basics [--author yamada] [--replace]
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

from sqlalchemy import select

from app.infra.db import new_session
from app.models import User
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
    # 実行
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
