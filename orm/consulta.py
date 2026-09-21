"""O construtor de consultas.

A ideia é que a consulta se monte por partes e só vire SQL no fim, quando
alguém pedir o resultado. Isso permite encadear ``.onde().ordenar().limite()``
em qualquer ordem, reaproveitar um trecho, e — o que mais importa — manter os
valores separados do texto do SQL, como parâmetros.
"""

from __future__ import annotations

from typing import Any, Iterator

#: Operadores aceitos no sufixo de um filtro, e o SQL de cada um.
OPERADORES = {
    "igual": "=",
    "diferente": "<>",
    "maior": ">",
    "maior_ou_igual": ">=",
    "menor": "<",
    "menor_ou_igual": "<=",
    "contem": "LIKE",
    "comeca_com": "LIKE",
    "termina_com": "LIKE",
    "em": "IN",
    "nulo": "IS",
}

#: Operadores que trabalham sobre texto e não passam pela conversão do campo.
TEXTUAIS = frozenset({"contem", "comeca_com", "termina_com"})


class ErroDeConsulta(ValueError):
    """A consulta não pôde ser montada."""


class Condicao:
    """Um pedaço de cláusula WHERE, com os parâmetros dele."""

    __slots__ = ("sql", "parametros")

    def __init__(self, sql: str, parametros: list[Any]) -> None:
        self.sql = sql
        self.parametros = parametros

    def __and__(self, outra: "Condicao") -> "Condicao":
        return Condicao(f"({self.sql} AND {outra.sql})", self.parametros + outra.parametros)

    def __or__(self, outra: "Condicao") -> "Condicao":
        return Condicao(f"({self.sql} OR {outra.sql})", self.parametros + outra.parametros)

    def __invert__(self) -> "Condicao":
        return Condicao(f"(NOT {self.sql})", list(self.parametros))

    def __repr__(self) -> str:
        return f"Condicao({self.sql!r}, {self.parametros!r})"


def condicao(campo: str, valor: Any, campos: dict | None = None) -> Condicao:
    """Monta uma condição a partir de ``coluna__operador=valor``.

    Sem sufixo, o operador é a igualdade. O ``__em`` recebe uma sequência e
    vira um ``IN`` com um parâmetro por item — nunca com os valores colados no
    SQL, que é como nasce injeção.

    Quando o mapa de campos é informado, o valor passa pela conversão do campo
    antes de virar parâmetro. É isso que faz ``preco__menor=10`` significar dez
    reais, e não dez centavos: quem escreve a consulta pensa no valor do
    domínio, não na forma como ele foi guardado.
    """
    nome, _, sufixo = campo.partition("__")
    sufixo = sufixo or "igual"

    if sufixo not in OPERADORES:
        conhecidos = ", ".join(sorted(OPERADORES))
        raise ErroDeConsulta(f"Operador desconhecido: {sufixo!r}. Conhecidos: {conhecidos}.")

    coluna = f'"{nome}"'

    if sufixo == "nulo":
        return Condicao(f"{coluna} IS {'NULL' if valor else 'NOT NULL'}", [])

    if sufixo == "contem":
        return Condicao(f"{coluna} LIKE ?", [f"%{valor}%"])

    if sufixo == "comeca_com":
        return Condicao(f"{coluna} LIKE ?", [f"{valor}%"])

    if sufixo == "termina_com":
        return Condicao(f"{coluna} LIKE ?", [f"%{valor}"])

    if sufixo == "em":
        itens = [_converter(nome, item, campos) for item in valor]

        if not itens:
            # IN () não é SQL válido, e a resposta certa é "nada casa".
            return Condicao("0 = 1", [])

        marcadores = ", ".join("?" for _ in itens)
        return Condicao(f"{coluna} IN ({marcadores})", itens)

    return Condicao(f"{coluna} {OPERADORES[sufixo]} ?", [_converter(nome, valor, campos)])


def _converter(nome: str, valor: Any, campos: dict | None) -> Any:
    if campos is None:
        return valor

    campo = campos.get(nome)

    if campo is None:
        return valor

    return campo.para_banco(campo.validar(valor))


class Consulta:
    """Uma consulta preguiçosa sobre um modelo."""

    def __init__(self, modelo) -> None:
        self.modelo = modelo
        self._condicoes: list[Condicao] = []
        self._ordem: list[str] = []
        self._limite: int | None = None
        self._pulo: int = 0
        self._colunas: list[str] | None = None

    # --- construção -------------------------------------------------------

    def _copia(self) -> "Consulta":
        nova = Consulta(self.modelo)
        nova._condicoes = list(self._condicoes)
        nova._ordem = list(self._ordem)
        nova._limite = self._limite
        nova._pulo = self._pulo
        nova._colunas = None if self._colunas is None else list(self._colunas)
        return nova

    def _mapa_de_campos(self) -> dict:
        return {campo.coluna: campo for campo in self.modelo._campos.values()}

    def onde(self, *condicoes: Condicao, **filtros: Any) -> "Consulta":
        """Acrescenta filtros, que se somam com E."""
        nova = self._copia()
        campos = self._mapa_de_campos()

        nova._condicoes.extend(condicoes)
        nova._condicoes.extend(
            condicao(campo, valor, campos) for campo, valor in filtros.items()
        )

        return nova

    def ordenar(self, *campos: str) -> "Consulta":
        """Ordena. Um campo com ``-`` na frente ordena ao contrário."""
        nova = self._copia()

        for campo in campos:
            descendente = campo.startswith("-")
            nome = campo[1:] if descendente else campo
            nova._ordem.append(f'"{nome}" {"DESC" if descendente else "ASC"}')

        return nova

    def limite(self, quantos: int, pular: int = 0) -> "Consulta":
        """Limita a quantidade de linhas."""
        if quantos < 0 or pular < 0:
            raise ErroDeConsulta("Limite e pulo não podem ser negativos.")

        nova = self._copia()
        nova._limite = quantos
        nova._pulo = pular
        return nova

    def apenas(self, *colunas: str) -> "Consulta":
        """Traz só algumas colunas, como tuplas em vez de objetos."""
        nova = self._copia()
        nova._colunas = list(colunas)
        return nova

    # --- SQL --------------------------------------------------------------

    def _where(self) -> tuple[str, list[Any]]:
        if not self._condicoes:
            return "", []

        juntas = self._condicoes[0]
        for outra in self._condicoes[1:]:
            juntas = juntas & outra

        return f" WHERE {juntas.sql}", juntas.parametros

    def sql(self) -> tuple[str, list[Any]]:
        """O SELECT e os parâmetros dele."""
        colunas = ", ".join(f'"{c}"' for c in self._colunas) if self._colunas else "*"
        texto = f'SELECT {colunas} FROM "{self.modelo._tabela}"'

        where, parametros = self._where()
        texto += where

        if self._ordem:
            texto += " ORDER BY " + ", ".join(self._ordem)

        if self._limite is not None:
            texto += " LIMIT ?"
            parametros = parametros + [self._limite]

            if self._pulo:
                texto += " OFFSET ?"
                parametros = parametros + [self._pulo]

        return texto, parametros

    def sql_de_contagem(self) -> tuple[str, list[Any]]:
        """O SELECT COUNT e os parâmetros dele."""
        where, parametros = self._where()
        return f'SELECT COUNT(*) FROM "{self.modelo._tabela}"{where}', parametros

    def sql_de_remocao(self) -> tuple[str, list[Any]]:
        """O DELETE e os parâmetros dele."""
        where, parametros = self._where()
        return f'DELETE FROM "{self.modelo._tabela}"{where}', parametros

    # --- execução ---------------------------------------------------------

    def todos(self) -> list:
        """Executa e devolve a lista."""
        return list(self)

    def __iter__(self) -> Iterator:
        texto, parametros = self.sql()
        linhas = self.modelo._sessao().buscar(texto, parametros)

        if self._colunas:
            return iter([tuple(linha) for linha in linhas])

        return iter([self.modelo._da_linha(linha) for linha in linhas])

    def primeiro(self):
        """O primeiro resultado, ou None."""
        for item in self.limite(1):
            return item
        return None

    def um(self):
        """O único resultado; reclama se houver zero ou mais de um."""
        achados = self.limite(2).todos()

        if not achados:
            raise ErroDeConsulta("A consulta não encontrou nenhuma linha.")
        if len(achados) > 1:
            raise ErroDeConsulta("A consulta encontrou mais de uma linha.")

        return achados[0]

    def contar(self) -> int:
        """Quantas linhas a consulta encontra."""
        texto, parametros = self.sql_de_contagem()
        return self.modelo._sessao().buscar(texto, parametros)[0][0]

    def existe(self) -> bool:
        """Indica se a consulta encontra ao menos uma linha."""
        return self.limite(1).contar() > 0

    def remover(self) -> int:
        """Apaga as linhas que a consulta encontra e devolve quantas foram."""
        texto, parametros = self.sql_de_remocao()
        return self.modelo._sessao().executar(texto, parametros).rowcount

    def __len__(self) -> int:
        return self.contar()

    def __repr__(self) -> str:
        texto, parametros = self.sql()
        return f"<Consulta {texto!r} {parametros!r}>"
