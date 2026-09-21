"""Migrações: a evolução do esquema, versionada.

O ponto de uma migração não é criar a tabela — isso o ``criar_tabela`` já faz.
É garantir que um banco que já existe chegue ao mesmo estado de um banco novo,
sem apagar dado, e que rodar duas vezes não estrague nada.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .sessao import Sessao

TABELA_DE_CONTROLE = "orm_migracoes"


class ErroDeMigracao(RuntimeError):
    """Uma migração não pôde ser aplicada."""


@dataclass(frozen=True, slots=True)
class Migracao:
    """Um passo de evolução do esquema."""

    versao: int
    nome: str
    aplicar: Callable[[Sessao], None]

    def __post_init__(self) -> None:
        if self.versao < 1:
            raise ErroDeMigracao("A versão precisa começar em 1.")

    def __str__(self) -> str:
        return f"{self.versao:04d} {self.nome}"


class Migrador:
    """Aplica as migrações pendentes, na ordem."""

    def __init__(self, sessao: Sessao) -> None:
        self.sessao = sessao
        self._migracoes: list[Migracao] = []
        self._preparar()

    def _preparar(self) -> None:
        self.sessao.executar(
            f'CREATE TABLE IF NOT EXISTS "{TABELA_DE_CONTROLE}" ('
            " versao INTEGER PRIMARY KEY,"
            " nome TEXT NOT NULL,"
            " aplicada_em TEXT NOT NULL DEFAULT (datetime('now'))"
            ")"
        )

    def registrar(self, versao: int, nome: str, aplicar: Callable[[Sessao], None]) -> "Migrador":
        """Acrescenta uma migração à lista."""
        if any(m.versao == versao for m in self._migracoes):
            raise ErroDeMigracao(f"Já existe migração com a versão {versao}.")

        self._migracoes.append(Migracao(versao, nome, aplicar))
        self._migracoes.sort(key=lambda m: m.versao)
        return self

    def migracao(self, versao: int, nome: str):
        """Decorador que registra a função como migração."""

        def decorar(funcao: Callable[[Sessao], None]):
            self.registrar(versao, nome, funcao)
            return funcao

        return decorar

    @property
    def registradas(self) -> list[Migracao]:
        """As migrações conhecidas, em ordem de versão."""
        return list(self._migracoes)

    def aplicadas(self) -> list[int]:
        """As versões já aplicadas neste banco."""
        linhas = self.sessao.buscar(f'SELECT versao FROM "{TABELA_DE_CONTROLE}" ORDER BY versao')
        return [linha[0] for linha in linhas]

    def pendentes(self) -> list[Migracao]:
        """As migrações que ainda faltam."""
        ja = set(self.aplicadas())
        return [migracao for migracao in self._migracoes if migracao.versao not in ja]

    @property
    def versao_atual(self) -> int:
        """A maior versão aplicada, ou zero."""
        aplicadas = self.aplicadas()
        return aplicadas[-1] if aplicadas else 0

    def migrar(self) -> list[Migracao]:
        """Aplica tudo o que falta e devolve o que foi aplicado.

        Cada migração roda na própria transação: se a terceira falhar, as duas
        primeiras continuam aplicadas e registradas, e é só corrigir a terceira
        e rodar de novo.
        """
        aplicadas = []

        for migracao in self.pendentes():
            try:
                with self.sessao.transacao():
                    migracao.aplicar(self.sessao)
                    self.sessao.executar(
                        f'INSERT INTO "{TABELA_DE_CONTROLE}" (versao, nome) VALUES (?, ?)',
                        [migracao.versao, migracao.nome],
                    )
            except Exception as erro:
                raise ErroDeMigracao(f"A migração {migracao} falhou: {erro}") from erro

            aplicadas.append(migracao)

        return aplicadas
