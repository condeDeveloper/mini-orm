from datetime import date
from decimal import Decimal

import pytest

from orm import ErroDeModelo, Inteiro, Modelo, Texto
from tests.conftest import Cliente, Pedido, Produto


def test_o_nome_da_tabela_sai_do_nome_da_classe():
    assert Cliente._tabela == "clientes"
    assert Produto._tabela == "produtos"


def test_a_tabela_pode_ser_declarada():
    class Item(Modelo):
        _tabela = "itens_do_pedido"
        nome = Texto()

    assert Item._tabela == "itens_do_pedido"


@pytest.mark.parametrize(
    "classe, tabela",
    [("Animal", "animais"), ("Ordem", "ordens"), ("Mes", "meses"), ("Item", "itens")],
)
def test_o_plural_cobre_os_casos_comuns(classe, tabela):
    modelo = type(classe, (Modelo,), {"nome": Texto()})

    assert modelo._tabela == tabela


def test_o_nome_composto_vira_snake_case():
    class ItemDoPedido(Modelo):
        nome = Texto()

    assert ItemDoPedido._tabela == "item_do_pedidos"


def test_campo_desconhecido_no_construtor_reclama():
    with pytest.raises(ErroDeModelo):
        Cliente(nome="Maria", inexistente=1)


def test_o_objeto_novo_nasce_novo_e_limpo(sessao):
    cliente = Cliente(nome="Maria")

    assert cliente.novo
    assert not cliente.sujo


def test_salvar_insere_e_atribui_o_id(sessao):
    cliente = Cliente(nome="Maria", email="maria@exemplo.com")
    cliente.salvar()

    assert cliente.id is not None
    assert not cliente.novo
    assert Cliente.contar() == 1


def test_criar_insere_de_uma_vez(sessao):
    cliente = Cliente.criar(nome="João")

    assert cliente.id is not None


def test_alterar_marca_o_campo_como_sujo(sessao):
    cliente = Cliente.criar(nome="Maria")

    cliente.nome = "Maria Souza"

    assert cliente.sujo
    assert cliente.alterados == {"nome"}


def test_atribuir_o_mesmo_valor_nao_suja(sessao):
    cliente = Cliente.criar(nome="Maria")

    cliente.nome = "Maria"

    assert not cliente.sujo


def test_salvar_atualiza_so_o_que_mudou(sessao):
    cliente = Cliente.criar(nome="Maria", email="maria@exemplo.com")
    sessao.consultas.clear()

    cliente.nome = "Maria Souza"
    cliente.salvar()

    atualizacoes = [sql for sql in sessao.consultas if sql.startswith("UPDATE")]
    assert len(atualizacoes) == 1
    assert "nome" in atualizacoes[0]
    assert "email" not in atualizacoes[0]


def test_salvar_sem_alteracao_nao_vai_ao_banco(sessao):
    cliente = Cliente.criar(nome="Maria")
    sessao.consultas.clear()

    cliente.salvar()

    assert not [sql for sql in sessao.consultas if sql.startswith("UPDATE")]


def test_salvar_limpa_o_estado_sujo(sessao):
    cliente = Cliente.criar(nome="Maria")
    cliente.nome = "Outro"
    cliente.salvar()

    assert not cliente.sujo


def test_os_valores_voltam_com_o_tipo_certo(sessao):
    Cliente.criar(nome="Maria", ativo=False, nascimento=date(1990, 5, 3))
    sessao.esvaziar_identidade()

    lido = Cliente.onde(nome="Maria").primeiro()

    assert lido.ativo is False
    assert lido.nascimento == date(1990, 5, 3)


def test_o_dinheiro_volta_como_decimal(sessao):
    Produto.criar(nome="caneta", preco="2.50")
    sessao.esvaziar_identidade()

    assert Produto.onde(nome="caneta").primeiro().preco == Decimal("2.50")


def test_buscar_pelo_id(sessao):
    cliente = Cliente.criar(nome="Maria")

    assert Cliente.buscar(cliente.id).nome == "Maria"


def test_buscar_o_que_nao_existe_devolve_nulo(sessao):
    assert Cliente.buscar(999) is None


def test_remover_apaga_do_banco(sessao):
    cliente = Cliente.criar(nome="Maria")

    cliente.remover()

    assert Cliente.contar() == 0
    assert cliente.novo


def test_remover_o_que_nunca_foi_gravado_reclama(sessao):
    with pytest.raises(ErroDeModelo):
        Cliente(nome="Maria").remover()


def test_recarregar_descarta_alteracoes(sessao):
    cliente = Cliente.criar(nome="Maria")
    cliente.nome = "Errado"

    cliente.recarregar()

    assert cliente.nome == "Maria"
    assert not cliente.sujo


def test_recarregar_o_que_sumiu_reclama(sessao):
    cliente = Cliente.criar(nome="Maria")
    sessao.executar("DELETE FROM clientes")

    with pytest.raises(ErroDeModelo):
        cliente.recarregar()


def test_a_igualdade_e_pelo_id(sessao):
    cliente = Cliente.criar(nome="Maria")
    outro = Cliente.onde(id=cliente.id).primeiro()

    assert cliente == outro
    assert cliente != Cliente.criar(nome="João")


def test_objeto_sem_id_nunca_e_igual_a_outro():
    assert Cliente(nome="Maria") != Cliente(nome="Maria")


def test_o_ddl_traz_as_colunas_e_a_chave_estrangeira():
    ddl = Pedido.ddl()

    assert "CREATE TABLE IF NOT EXISTS" in ddl
    assert "FOREIGN KEY" in ddl
    assert "ON DELETE CASCADE" in ddl


def test_a_chave_estrangeira_e_respeitada(sessao):
    with pytest.raises(Exception):
        Pedido.criar(cliente_id=999, total="10.00")


def test_apagar_o_pai_leva_o_filho_junto(sessao):
    cliente = Cliente.criar(nome="Maria")
    Pedido.criar(cliente_id=cliente.id, total="10.00")

    cliente.remover()

    assert Pedido.contar() == 0


def test_campos_sao_herdados():
    class Base(Modelo):
        criado_por = Texto()

    class Derivado(Base):
        valor = Inteiro()

    assert "criado_por" in Derivado._campos
    assert "valor" in Derivado._campos


def test_o_objeto_se_descreve_de_volta(sessao):
    cliente = Cliente.criar(nome="Maria")

    assert "Cliente(" in repr(cliente)
    assert "Maria" in repr(cliente)
