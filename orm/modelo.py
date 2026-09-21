"""O modelo: a classe que vira tabela.

A metaclasse recolhe os campos declarados, descobre o nome da tabela e deixa
tudo pronto antes de a classe existir. É por isso que o modelo fica limpo: só
os campos aparecem no código de quem usa.
"""

from __future__ import annotations

from typing import Any

from .campos import Campo, ChaveEstrangeira, Inteiro
from .consulta import Consulta
from .sessao import Sessao


class ErroDeModelo(RuntimeError):
    """O modelo não pôde ser usado como pedido."""


class _MetaModelo(type):
    """Recolhe os campos declarados na classe."""

    def __new__(mcs, nome, bases, corpo, **extras):
        campos: dict[str, Campo] = {}

        # Herdar os campos das bases é o que permite uma classe abstrata com
        # campos comuns, tipo criado_em e atualizado_em.
        for base in bases:
            campos.update(getattr(base, "_campos", {}))

        for chave, valor in corpo.items():
            if isinstance(valor, Campo):
                campos[chave] = valor

        classe = super().__new__(mcs, nome, bases, corpo)

        if not bases or nome == "Modelo":
            return classe

        if "id" not in campos:
            identificador = Inteiro(primaria=True)
            identificador.__set_name__(classe, "id")
            setattr(classe, "id", identificador)
            campos = {"id": identificador, **campos}

        classe._campos = campos
        classe._tabela = corpo.get("_tabela") or _pluralizar(nome)
        classe._primaria = next(
            (campo for campo in campos.values() if campo.primaria), campos["id"]
        )

        return classe


def _pluralizar(nome: str) -> str:
    """Um plural ingênuo, suficiente para nome de tabela.

    Vale a pena ser ingênuo aqui: quando erra, o modelo declara `_tabela` e
    pronto. Um pluralizador de verdade seria mais código do que benefício.
    """
    minusculo = _para_minusculo(nome)

    if minusculo.endswith(("s", "x", "z")):
        return minusculo + "es"
    if minusculo.endswith(("r", "n")):
        return minusculo + "es"
    if minusculo.endswith("m"):
        return minusculo[:-1] + "ns"
    if minusculo.endswith("l"):
        return minusculo[:-1] + "is"
    if minusculo.endswith("ao"):
        return minusculo[:-2] + "oes"

    return minusculo + "s"


def _para_minusculo(nome: str) -> str:
    saida = []

    for posicao, letra in enumerate(nome):
        if letra.isupper() and posicao > 0:
            saida.append("_")
        saida.append(letra.lower())

    return "".join(saida)


class Modelo(metaclass=_MetaModelo):
    """Base dos modelos."""

    _campos: dict[str, Campo] = {}
    _tabela: str = ""

    def __init__(self, **valores) -> None:
        self._sujos: set[str] = set()
        self._novo = True

        desconhecidos = set(valores) - set(self._campos)
        if desconhecidos:
            raise ErroDeModelo(
                f"{type(self).__name__} não tem o campo {', '.join(sorted(desconhecidos))}."
            )

        for nome, campo in self._campos.items():
            setattr(self, nome, valores.get(nome, campo.valor_padrao()))

        self._sujos.clear()

    # --- estado -----------------------------------------------------------

    def _marcar_sujo(self, nome: str) -> None:
        self._sujos.add(nome)

    @property
    def sujo(self) -> bool:
        """Indica se algum campo mudou desde a última gravação."""
        return bool(self._sujos)

    @property
    def alterados(self) -> set[str]:
        """Os campos alterados desde a última gravação."""
        return set(self._sujos)

    @property
    def novo(self) -> bool:
        """Indica se o objeto ainda não foi gravado."""
        return self._novo

    def valores(self) -> dict[str, Any]:
        """Os valores dos campos, do jeito que estão no Python."""
        return {nome: getattr(self, nome) for nome in self._campos}

    # --- acesso à sessão --------------------------------------------------

    @classmethod
    def _sessao(cls) -> Sessao:
        return Sessao.corrente()

    @classmethod
    def _da_linha(cls, linha) -> "Modelo":
        """Monta o objeto a partir de uma linha do banco."""
        valores = {}

        for nome, campo in cls._campos.items():
            if campo.coluna in linha.keys():
                valores[nome] = campo.do_banco(linha[campo.coluna])

        objeto = cls.__new__(cls)
        objeto._sujos = set()
        objeto._novo = False

        for nome, campo in cls._campos.items():
            objeto.__dict__[nome] = valores.get(nome, campo.valor_padrao())

        return cls._sessao().registrar(objeto)

    # --- esquema ----------------------------------------------------------

    @classmethod
    def ddl(cls) -> str:
        """O CREATE TABLE deste modelo."""
        linhas = [campo.definicao() for campo in cls._campos.values()]
        linhas.extend(
            campo.restricao()
            for campo in cls._campos.values()
            if isinstance(campo, ChaveEstrangeira)
        )

        corpo = ",\n  ".join(linhas)
        return f'CREATE TABLE IF NOT EXISTS "{cls._tabela}" (\n  {corpo}\n)'

    @classmethod
    def criar_tabela(cls) -> None:
        """Cria a tabela, se ela ainda não existir."""
        cls._sessao().executar(cls.ddl())

    @classmethod
    def apagar_tabela(cls) -> None:
        """Remove a tabela."""
        cls._sessao().executar(f'DROP TABLE IF EXISTS "{cls._tabela}"')

    # --- consulta ---------------------------------------------------------

    @classmethod
    def consulta(cls) -> Consulta:
        """Uma consulta vazia sobre este modelo."""
        return Consulta(cls)

    @classmethod
    def onde(cls, *condicoes, **filtros) -> Consulta:
        """Atalho para ``consulta().onde(...)``."""
        return cls.consulta().onde(*condicoes, **filtros)

    @classmethod
    def todos(cls) -> list:
        """Todos os registros."""
        return cls.consulta().todos()

    @classmethod
    def contar(cls) -> int:
        """Quantos registros existem."""
        return cls.consulta().contar()

    @classmethod
    def buscar(cls, identificador):
        """Busca pelo identificador, olhando primeiro o mapa de identidade."""
        na_memoria = cls._sessao().buscar_na_memoria(cls, identificador)

        if na_memoria is not None:
            return na_memoria

        return cls.onde(id=identificador).primeiro()

    @classmethod
    def criar(cls, **valores) -> "Modelo":
        """Cria e grava de uma vez."""
        objeto = cls(**valores)
        objeto.salvar()
        return objeto

    # --- gravação ---------------------------------------------------------

    def salvar(self) -> "Modelo":
        """Insere ou atualiza, conforme o objeto já exista ou não."""
        return self._inserir() if self._novo else self._atualizar()

    def _inserir(self) -> "Modelo":
        campos = [
            (nome, campo)
            for nome, campo in self._campos.items()
            if not (campo.primaria and getattr(self, nome) is None)
        ]

        colunas = ", ".join(f'"{campo.coluna}"' for _, campo in campos)
        marcadores = ", ".join("?" for _ in campos)
        valores = [campo.para_banco(getattr(self, nome)) for nome, campo in campos]

        sql = f'INSERT INTO "{self._tabela}" ({colunas}) VALUES ({marcadores})'
        cursor = self._sessao().executar(sql, valores)

        if getattr(self, "id", None) is None:
            self.__dict__["id"] = cursor.lastrowid

        self._novo = False
        self._sujos.clear()

        return self._sessao().registrar(self)

    def _atualizar(self) -> "Modelo":
        if not self._sujos:
            return self

        # Só o que mudou vai no UPDATE: além de ser menos escrita, evita
        # sobrescrever com valor velho uma coluna que outro processo mexeu.
        alterados = [(nome, self._campos[nome]) for nome in sorted(self._sujos)]
        atribuicoes = ", ".join(f'"{campo.coluna}" = ?' for _, campo in alterados)
        valores = [campo.para_banco(getattr(self, nome)) for nome, campo in alterados]

        sql = f'UPDATE "{self._tabela}" SET {atribuicoes} WHERE "id" = ?'
        self._sessao().executar(sql, valores + [self.id])

        self._sujos.clear()
        return self

    def remover(self) -> None:
        """Apaga do banco."""
        if self._novo or getattr(self, "id", None) is None:
            raise ErroDeModelo("Não dá para remover um objeto que nunca foi gravado.")

        self._sessao().executar(f'DELETE FROM "{self._tabela}" WHERE "id" = ?', [self.id])
        self._sessao().esquecer(self)
        self._novo = True

    def recarregar(self) -> "Modelo":
        """Relê os valores do banco, descartando alterações não gravadas."""
        if getattr(self, "id", None) is None:
            raise ErroDeModelo("Não dá para recarregar um objeto sem identificador.")

        linhas = self._sessao().buscar(
            f'SELECT * FROM "{self._tabela}" WHERE "id" = ?', [self.id]
        )

        if not linhas:
            raise ErroDeModelo(f"O registro {self.id} não existe mais.")

        for nome, campo in self._campos.items():
            if campo.coluna in linhas[0].keys():
                self.__dict__[nome] = campo.do_banco(linhas[0][campo.coluna])

        self._sujos.clear()
        self._novo = False
        return self

    # --- representação ----------------------------------------------------

    def __eq__(self, outro) -> bool:
        if not isinstance(outro, type(self)):
            return NotImplemented

        identificador = getattr(self, "id", None)
        return identificador is not None and identificador == getattr(outro, "id", None)

    def __hash__(self) -> int:
        return hash((type(self).__name__, getattr(self, "id", None)))

    def __repr__(self) -> str:
        campos = ", ".join(
            f"{nome}={getattr(self, nome)!r}" for nome in list(self._campos)[:4]
        )
        return f"{type(self).__name__}({campos})"
