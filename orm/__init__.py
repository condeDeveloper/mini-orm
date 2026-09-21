"""ORM em Python puro sobre ``sqlite3``.

    >>> from orm import Modelo, Sessao, Texto, Dinheiro
    >>> class Produto(Modelo):
    ...     nome = Texto(nulo=False)
    ...     preco = Dinheiro()
    >>> with Sessao() as sessao:
    ...     Produto.criar_tabela()
    ...     caneta = Produto.criar(nome="caneta", preco="2.50")
    ...     Produto.onde(nome__comeca_com="can").primeiro().nome
    'caneta'
"""

from __future__ import annotations

from .campos import (
    Booleano,
    Campo,
    ChaveEstrangeira,
    Data,
    DataHora,
    Dinheiro,
    ErroDeCampo,
    Inteiro,
    Real,
    Texto,
)
from .consulta import Condicao, Consulta, ErroDeConsulta, condicao
from .migracao import ErroDeMigracao, Migracao, Migrador
from .modelo import ErroDeModelo, Modelo
from .sessao import ErroDeSessao, Sessao

__version__ = "1.0.0"

__all__ = [
    "Booleano",
    "Campo",
    "ChaveEstrangeira",
    "Condicao",
    "Consulta",
    "Data",
    "DataHora",
    "Dinheiro",
    "ErroDeCampo",
    "ErroDeConsulta",
    "ErroDeMigracao",
    "ErroDeModelo",
    "ErroDeSessao",
    "Inteiro",
    "Migracao",
    "Migrador",
    "Modelo",
    "Real",
    "Sessao",
    "Texto",
    "condicao",
]
