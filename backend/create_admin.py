"""Create the first administrator using interactive credentials."""
from getpass import getpass

from sqlalchemy import select

if __package__:
    from .database import SessionLocal, User
    from .API.contas import password_hash
else:
    from database import SessionLocal, User
    from API.contas import password_hash


def main() -> None:
    name = input("Nome do administrador: ").strip()
    email = input("E-mail do administrador: ").strip().lower()
    password = getpass("Senha: ")
    confirmation = getpass("Confirme a senha: ")
    if not name or not email or len(password) < 6 or password != confirmation:
        raise SystemExit("Dados inválidos ou senhas diferentes.")
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email == email)):
            raise SystemExit("Este e-mail já está cadastrado.")
        db.add(User(name=name, email=email, password_hash=password_hash.hash(password), role="admin"))
        db.commit()
    print("Administrador criado.")


if __name__ == "__main__":
    main()
