"""Modelos e sessão de apoio aos testes."""

from __future__ import annotations

import pytest

from orm import (
    Booleano,
    ChaveEstrangeira,
    Data,
    DataHora,
    Dinheiro,
    Inteiro,
    Modelo,
    Real,
    Sessao,
    Texto,
)


class Cliente(Modelo):
    nome = Texto(nulo=False, tamanho=80)
    email = Texto(unico=True)
    ativo = Booleano(padrao=True)
    nascimento = Data()


class Produto(Modelo):
    nome = Texto(nulo=False)
    preco = Dinheiro(nulo=False)
    estoque = Inteiro(padrao=0)
    peso = Real()


class Pedido(Modelo):
    cliente_id = ChaveEstrangeira("clientes", ao_apagar="CASCADE", nulo=False)
    total = Dinheiro(nulo=False)
    criado_em = DataHora()


@pytest.fixture()
def sessao():
    """Uma sessão em memória com as três tabelas criadas."""
    with Sessao() as aberta:
        Cliente.criar_tabela()
        Produto.criar_tabela()
        Pedido.criar_tabela()
        yield aberta


@pytest.fixture()
def catalogo(sessao):
    """Alguns produtos para consultar."""
    Produto.criar(nome="caneta", preco="2.50", estoque=100, peso=0.01)
    Produto.criar(nome="caderno", preco="15.00", estoque=30, peso=0.3)
    Produto.criar(nome="mochila", preco="90.00", estoque=5, peso=0.8)
    Produto.criar(nome="lapis", preco="1.20", estoque=0, peso=0.005)
    return sessao
