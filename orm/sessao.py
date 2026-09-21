"""A sessão: a conexão, o mapa de identidade e a transação.

O mapa de identidade é o que impede o mesmo registro de virar dois objetos
diferentes na memória. Sem ele, carregar o cliente 7 duas vezes daria dois
objetos, e alterar um deixaria o outro desatualizado — o tipo de bug que só
aparece em produção.
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from typing import Any

_atual = threading.local()


class ErroDeSessao(RuntimeError):
    """Não há sessão aberta, ou ela está em estado inválido."""


class Sessao:
    """Uma conexão com o banco, com mapa de identidade."""

    def __init__(self, caminho: str = ":memory:", *, eco: bool = False) -> None:
        self.caminho = caminho
        self.eco = eco
        self.consultas: list[str] = []

        self.conexao = sqlite3.connect(caminho)
        self.conexao.row_factory = sqlite3.Row
        # Sem isso o SQLite aceita apagar uma linha referenciada, e a chave
        # estrangeira vira enfeite.
        self.conexao.execute("PRAGMA foreign_keys = ON")

        self._identidade: dict[tuple[str, Any], Any] = {}

    # --- ciclo de vida ----------------------------------------------------

    def __enter__(self) -> "Sessao":
        self.ativar()
        return self

    def __exit__(self, *_) -> None:
        self.fechar()

    def ativar(self) -> "Sessao":
        """Torna esta a sessão corrente da thread."""
        _atual.sessao = self
        return self

    def fechar(self) -> None:
        """Fecha a conexão e esvazia o mapa de identidade."""
        self._identidade.clear()
        self.conexao.close()

        if getattr(_atual, "sessao", None) is self:
            _atual.sessao = None

    @staticmethod
    def corrente() -> "Sessao":
        """A sessão da thread, ou erro se não houver."""
        sessao = getattr(_atual, "sessao", None)

        if sessao is None:
            raise ErroDeSessao("Não há sessão aberta. Use `with Sessao(...):`.")

        return sessao

    # --- execução ---------------------------------------------------------

    def executar(self, sql: str, parametros: list[Any] | tuple = ()) -> sqlite3.Cursor:
        """Roda um comando."""
        self._registrar(sql, parametros)
        return self.conexao.execute(sql, tuple(parametros))

    def buscar(self, sql: str, parametros: list[Any] | tuple = ()) -> list[sqlite3.Row]:
        """Roda uma consulta e devolve todas as linhas."""
        return self.executar(sql, parametros).fetchall()

    def _registrar(self, sql: str, parametros) -> None:
        self.consultas.append(sql)

        if self.eco:
            print(f"[sql] {sql} {list(parametros)}")

    # --- transação --------------------------------------------------------

    @contextmanager
    def transacao(self):
        """Confirma no fim, desfaz se algo escapar."""
        try:
            yield self
        except Exception:
            self.conexao.rollback()
            # O mapa de identidade guarda objetos com valores que o banco já
            # descartou; mantê-lo seria servir dado que não existe mais.
            self._identidade.clear()
            raise
        else:
            self.conexao.commit()

    def confirmar(self) -> None:
        """Confirma a transação corrente."""
        self.conexao.commit()

    def desfazer(self) -> None:
        """Desfaz a transação corrente."""
        self.conexao.rollback()
        self._identidade.clear()

    # --- mapa de identidade -----------------------------------------------

    def registrar(self, objeto) -> Any:
        """Guarda o objeto no mapa, ou devolve o que já estava lá."""
        chave = self._chave(objeto)

        if chave is None:
            return objeto

        existente = self._identidade.get(chave)

        if existente is not None:
            return existente

        self._identidade[chave] = objeto
        return objeto

    def buscar_na_memoria(self, modelo, identificador):
        """O objeto já carregado com esse identificador, se houver."""
        return self._identidade.get((modelo._tabela, identificador))

    def esquecer(self, objeto) -> None:
        """Tira o objeto do mapa."""
        chave = self._chave(objeto)

        if chave is not None:
            self._identidade.pop(chave, None)

    def esvaziar_identidade(self) -> None:
        """Esvazia o mapa, forçando as próximas leituras a irem ao banco."""
        self._identidade.clear()

    @property
    def carregados(self) -> int:
        """Quantos objetos estão no mapa de identidade."""
        return len(self._identidade)

    @staticmethod
    def _chave(objeto):
        identificador = getattr(objeto, "id", None)
        return None if identificador is None else (type(objeto)._tabela, identificador)
