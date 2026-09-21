from decimal import Decimal

import pytest

from orm import ErroDeConsulta, condicao
from tests.conftest import Cliente, Produto


def nomes(consulta):
    return [produto.nome for produto in consulta]


def test_todos_traz_tudo(catalogo):
    assert Produto.contar() == 4


def test_filtro_por_igualdade(catalogo):
    assert nomes(Produto.onde(nome="caneta")) == ["caneta"]


def test_filtros_se_somam_com_e(catalogo):
    assert nomes(Produto.onde(estoque__maior=0, preco__menor=10)) == ["caneta"]


@pytest.mark.parametrize(
    "filtro, esperado",
    [
        ({"estoque__maior": 30}, ["caneta"]),
        ({"estoque__maior_ou_igual": 30}, ["caneta", "caderno"]),
        ({"estoque__menor": 5}, ["lapis"]),
        ({"estoque__menor_ou_igual": 5}, ["mochila", "lapis"]),
        ({"nome__diferente": "caneta"}, ["caderno", "mochila", "lapis"]),
    ],
)
def test_operadores_de_comparacao(catalogo, filtro, esperado):
    assert sorted(nomes(Produto.onde(**filtro))) == sorted(esperado)


def test_contem_comeca_e_termina(catalogo):
    assert nomes(Produto.onde(nome__contem="der")) == ["caderno"]
    assert sorted(nomes(Produto.onde(nome__comeca_com="ca"))) == ["caderno", "caneta"]
    assert nomes(Produto.onde(nome__termina_com="la")) == ["mochila"]


def test_em_com_lista(catalogo):
    assert sorted(nomes(Produto.onde(nome__em=["caneta", "lapis"]))) == ["caneta", "lapis"]


def test_em_com_lista_vazia_nao_traz_nada(catalogo):
    # IN () não é SQL válido; a resposta certa é "nada casa".
    assert nomes(Produto.onde(nome__em=[])) == []


def test_filtro_por_nulo(catalogo):
    Produto.criar(nome="sem peso", preco="1.00", peso=None)

    assert nomes(Produto.onde(peso__nulo=True)) == ["sem peso"]
    assert len(Produto.onde(peso__nulo=False).todos()) == 4


def test_operador_desconhecido_reclama():
    with pytest.raises(ErroDeConsulta):
        condicao("nome__parecido", "x")


def test_as_condicoes_se_combinam():
    uma = condicao("a", 1)
    outra = condicao("b", 2)

    assert (uma & outra).sql == '("a" = ? AND "b" = ?)'
    assert (uma | outra).sql == '("a" = ? OR "b" = ?)'
    assert (~uma).sql == '(NOT "a" = ?)'
    assert (uma & outra).parametros == [1, 2]


def test_condicao_solta_na_consulta(catalogo):
    barato = condicao("preco__menor", 500)
    caro = condicao("preco__maior", 5000)

    assert len(Produto.onde(barato | caro).todos()) == 3


def test_ordenar_crescente_e_decrescente(catalogo):
    assert nomes(Produto.consulta().ordenar("nome"))[0] == "caderno"
    assert nomes(Produto.consulta().ordenar("-nome"))[0] == "mochila"


def test_ordenar_por_mais_de_um_campo(catalogo):
    assert nomes(Produto.consulta().ordenar("-estoque", "nome"))[0] == "caneta"


def test_limite_e_pulo(catalogo):
    ordenados = Produto.consulta().ordenar("nome")

    assert len(ordenados.limite(2).todos()) == 2
    assert nomes(ordenados.limite(2, pular=2)) == ["lapis", "mochila"]


def test_limite_negativo_reclama():
    with pytest.raises(ErroDeConsulta):
        Produto.consulta().limite(-1)


def test_apenas_traz_tuplas(catalogo):
    linhas = Produto.consulta().apenas("nome", "estoque").ordenar("nome").todos()

    assert linhas[0] == ("caderno", 30)


def test_primeiro_e_none_quando_nao_acha(catalogo):
    assert Produto.onde(nome="inexistente").primeiro() is None


def test_um_exige_exatamente_um(catalogo):
    assert Produto.onde(nome="caneta").um().nome == "caneta"

    with pytest.raises(ErroDeConsulta):
        Produto.onde(nome="inexistente").um()

    with pytest.raises(ErroDeConsulta):
        Produto.consulta().um()


def test_contar_e_existe(catalogo):
    assert Produto.onde(estoque=0).contar() == 1
    assert Produto.onde(estoque=0).existe()
    assert not Produto.onde(nome="inexistente").existe()


def test_len_conta(catalogo):
    assert len(Produto.consulta()) == 4


def test_remover_pela_consulta(catalogo):
    removidos = Produto.onde(estoque=0).remover()

    assert removidos == 1
    assert Produto.contar() == 3


def test_a_consulta_e_imutavel(catalogo):
    base = Produto.consulta()
    filtrada = base.onde(nome="caneta")

    assert len(base.todos()) == 4
    assert len(filtrada.todos()) == 1


def test_a_consulta_gera_sql_com_parametros():
    sql, parametros = Produto.onde(nome="caneta", estoque__maior=0).ordenar("-preco").limite(5).sql()

    assert sql.startswith('SELECT * FROM "produtos" WHERE')
    assert "ORDER BY" in sql
    assert "LIMIT ?" in sql
    assert parametros == ["caneta", 0, 5]


def test_o_valor_nunca_entra_colado_no_sql():
    # É isso que separa parâmetro de injeção: o texto do SQL não muda com o
    # valor, por mais hostil que ele seja.
    sql, parametros = Cliente.onde(nome="'; DROP TABLE clientes; --").sql()

    assert "DROP" not in sql
    assert parametros == ["'; DROP TABLE clientes; --"]


def test_o_valor_hostil_e_tratado_como_texto(sessao):
    Cliente.criar(nome="'; DROP TABLE clientes; --")

    assert Cliente.contar() == 1
    assert Cliente.onde(nome__contem="DROP").contar() == 1


def test_a_consulta_se_descreve_de_volta():
    assert "SELECT" in repr(Produto.onde(nome="x"))


def test_o_dinheiro_e_filtrado_em_reais(catalogo):
    # O valor vai para o banco em centavos, mas quem escreve a consulta pensa
    # em reais: a conversão é do ORM, não de quem usa.
    assert nomes(Produto.onde(preco__maior=50)) == ["mochila"]
    assert nomes(Produto.onde(preco__menor="2.00")) == ["lapis"]
    assert Produto.onde(nome="mochila").primeiro().preco == Decimal("90.00")


def test_o_em_tambem_converte_cada_item(catalogo):
    assert sorted(nomes(Produto.onde(preco__em=["2.50", "15.00"]))) == ["caderno", "caneta"]


def test_o_booleano_e_filtrado_como_booleano(sessao):
    Cliente.criar(nome="ativa", ativo=True)
    Cliente.criar(nome="inativa", ativo=False)

    assert Cliente.onde(ativo=False).um().nome == "inativa"
