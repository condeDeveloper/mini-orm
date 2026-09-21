"""Os campos que descrevem uma coluna.

Cada campo é um descritor: ele sabe o tipo SQL da coluna, sabe converter entre
o valor do Python e o valor do banco, e — por ser descritor — consegue avisar o
modelo toda vez que alguém escreve nele. É desse aviso que sai o controle de
alterações, sem precisar comparar o objeto inteiro com uma cópia.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any


class ErroDeCampo(ValueError):
    """O valor não serve para o campo."""


class Campo:
    """Base de todos os campos."""

    tipo_sql = "TEXT"
    tipos_aceitos: tuple[type, ...] = ()

    def __init__(
        self,
        *,
        primaria: bool = False,
        nulo: bool = True,
        unico: bool = False,
        padrao: Any = None,
        coluna: str | None = None,
    ) -> None:
        self.primaria = primaria
        # A chave primária precisa aceitar None no Python: o valor só existe
        # depois que o banco atribui o autoincremento. No DDL o PRIMARY KEY já
        # implica NOT NULL, então nada se perde.
        self.nulo = True if primaria else nulo
        self.unico = unico or primaria
        self.padrao = padrao
        self.coluna = coluna
        self.nome = ""

    # --- protocolo de descritor -------------------------------------------

    def __set_name__(self, dono: type, nome: str) -> None:
        self.nome = nome
        self.coluna = self.coluna or nome

    def __get__(self, instancia, dono=None):
        if instancia is None:
            return self
        return instancia.__dict__.get(self.nome, self.valor_padrao())

    def __set__(self, instancia, valor) -> None:
        convertido = self.validar(valor)
        anterior = instancia.__dict__.get(self.nome, _AUSENTE)

        instancia.__dict__[self.nome] = convertido

        if anterior is not _AUSENTE and anterior != convertido:
            instancia._marcar_sujo(self.nome)

    # --- conversão --------------------------------------------------------

    def valor_padrao(self):
        """O valor inicial do campo."""
        return self.padrao() if callable(self.padrao) else self.padrao

    def validar(self, valor):
        """Confere e converte o valor vindo do Python."""
        if valor is None:
            if not self.nulo:
                raise ErroDeCampo(f"O campo {self.nome!r} não aceita nulo.")
            return None

        if self.tipos_aceitos and not isinstance(valor, self.tipos_aceitos):
            esperado = " ou ".join(tipo.__name__ for tipo in self.tipos_aceitos)
            raise ErroDeCampo(
                f"O campo {self.nome!r} esperava {esperado}, veio {type(valor).__name__}."
            )

        return self.converter(valor)

    def converter(self, valor):
        """Ajusta o valor já validado."""
        return valor

    def para_banco(self, valor):
        """Converte o valor do Python para o que o sqlite3 aceita."""
        return valor

    def do_banco(self, valor):
        """Converte o valor lido do banco de volta para o Python."""
        return valor

    def definicao(self) -> str:
        """O pedaço de DDL que define esta coluna."""
        partes = [f'"{self.coluna}"', self.tipo_sql]

        if self.primaria:
            partes.append("PRIMARY KEY")
            if isinstance(self, Inteiro):
                partes.append("AUTOINCREMENT")
        else:
            if not self.nulo:
                partes.append("NOT NULL")
            if self.unico:
                partes.append("UNIQUE")

        return " ".join(partes)

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.nome!r})"


class _Ausente:
    def __repr__(self) -> str:
        return "<ausente>"


_AUSENTE = _Ausente()


class Texto(Campo):
    """Uma coluna de texto."""

    tipo_sql = "TEXT"
    tipos_aceitos = (str,)

    def __init__(self, *, tamanho: int | None = None, **extras) -> None:
        super().__init__(**extras)
        self.tamanho = tamanho

    def converter(self, valor: str) -> str:
        if self.tamanho is not None and len(valor) > self.tamanho:
            raise ErroDeCampo(
                f"O campo {self.nome!r} aceita até {self.tamanho} caracteres, veio {len(valor)}."
            )
        return valor


class Inteiro(Campo):
    """Uma coluna de número inteiro."""

    tipo_sql = "INTEGER"
    tipos_aceitos = (int,)

    def validar(self, valor):
        # bool é subclasse de int em Python, e deixar passar aqui gravaria
        # True em uma coluna que espera número.
        if isinstance(valor, bool):
            raise ErroDeCampo(f"O campo {self.nome!r} esperava int, veio bool.")
        return super().validar(valor)


class Real(Campo):
    """Uma coluna de ponto flutuante."""

    tipo_sql = "REAL"
    tipos_aceitos = (int, float)

    def converter(self, valor) -> float:
        return float(valor)


class Booleano(Campo):
    """Uma coluna de verdadeiro ou falso.

    O SQLite não tem tipo booleano: o valor vai como 0 ou 1 e volta convertido.
    """

    tipo_sql = "INTEGER"
    tipos_aceitos = (bool,)

    def para_banco(self, valor):
        return None if valor is None else int(valor)

    def do_banco(self, valor):
        return None if valor is None else bool(valor)


class Dinheiro(Campo):
    """Uma coluna monetária, guardada em centavos.

    Guardar ``Decimal`` como texto ou ``REAL`` é o caminho curto para o
    centavo que some. Em centavos inteiros a aritmética fecha.
    """

    tipo_sql = "INTEGER"
    tipos_aceitos = (int, float, Decimal, str)

    def converter(self, valor) -> Decimal:
        return Decimal(str(valor)).quantize(Decimal("0.01"))

    def para_banco(self, valor):
        return None if valor is None else int(Decimal(str(valor)) * 100)

    def do_banco(self, valor):
        return None if valor is None else Decimal(valor) / 100


class DataHora(Campo):
    """Uma coluna de data e hora, gravada em ISO 8601."""

    tipo_sql = "TEXT"
    tipos_aceitos = (datetime,)

    def para_banco(self, valor):
        return None if valor is None else valor.isoformat(sep=" ", timespec="seconds")

    def do_banco(self, valor):
        return None if valor is None else datetime.fromisoformat(valor)


class Data(Campo):
    """Uma coluna de data, gravada em ISO 8601."""

    tipo_sql = "TEXT"
    tipos_aceitos = (date,)

    def validar(self, valor):
        if isinstance(valor, datetime):
            raise ErroDeCampo(f"O campo {self.nome!r} esperava date, veio datetime.")
        return super().validar(valor)

    def para_banco(self, valor):
        return None if valor is None else valor.isoformat()

    def do_banco(self, valor):
        return None if valor is None else date.fromisoformat(valor)


class ChaveEstrangeira(Inteiro):
    """Uma coluna que aponta para a chave primária de outro modelo."""

    def __init__(self, para: str, *, ao_apagar: str = "RESTRICT", **extras) -> None:
        super().__init__(**extras)
        self.para = para
        self.ao_apagar = ao_apagar

    def restricao(self) -> str:
        """A cláusula FOREIGN KEY correspondente."""
        return (
            f'FOREIGN KEY ("{self.coluna}") REFERENCES "{self.para}" (id) '
            f"ON DELETE {self.ao_apagar}"
        )
