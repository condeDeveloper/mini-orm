from datetime import date, datetime
from decimal import Decimal

import pytest

from orm import Booleano, Data, DataHora, Dinheiro, ErroDeCampo, Inteiro, Modelo, Real, Texto


class Exemplo(Modelo):
    texto = Texto()
    inteiro = Inteiro()
    real = Real()
    booleano = Booleano()
    dinheiro = Dinheiro()
    data = Data()
    momento = DataHora()


def test_o_campo_descobre_o_proprio_nome():
    assert Exemplo._campos["texto"].nome == "texto"
    assert Exemplo._campos["texto"].coluna == "texto"


def test_o_modelo_ganha_um_id_automatico():
    assert "id" in Exemplo._campos
    assert Exemplo._campos["id"].primaria


def test_valor_padrao():
    class ComPadrao(Modelo):
        quantidade = Inteiro(padrao=7)

    assert ComPadrao().quantidade == 7


def test_padrao_pode_ser_uma_funcao():
    class ComFabrica(Modelo):
        criado = DataHora(padrao=lambda: datetime(2026, 9, 21, 10, 0))

    assert ComFabrica().criado == datetime(2026, 9, 21, 10, 0)


@pytest.mark.parametrize(
    "campo, valor",
    [
        ("texto", 123),
        ("inteiro", "abc"),
        ("booleano", 1),
        ("data", datetime(2026, 1, 1)),
    ],
)
def test_tipo_errado_reclama(campo, valor):
    with pytest.raises(ErroDeCampo):
        setattr(Exemplo(), campo, valor)


def test_booleano_nao_passa_por_inteiro():
    # bool é subclasse de int em Python; sem a checagem, True viraria 1 numa
    # coluna que espera número.
    with pytest.raises(ErroDeCampo):
        Exemplo().inteiro = True


def test_campo_obrigatorio_recusa_nulo():
    class Obrigatorio(Modelo):
        nome = Texto(nulo=False)

    with pytest.raises(ErroDeCampo):
        Obrigatorio().nome = None


def test_texto_respeita_o_tamanho():
    class Curto(Modelo):
        nome = Texto(tamanho=5)

    Curto().nome = "abcde"

    with pytest.raises(ErroDeCampo):
        Curto().nome = "abcdef"


def test_real_converte_inteiro_em_float():
    exemplo = Exemplo()
    exemplo.real = 3

    assert exemplo.real == 3.0
    assert isinstance(exemplo.real, float)


def test_dinheiro_vira_decimal_com_duas_casas():
    exemplo = Exemplo()
    exemplo.dinheiro = "19.9"

    assert exemplo.dinheiro == Decimal("19.90")


def test_dinheiro_vai_e_volta_em_centavos():
    campo = Exemplo._campos["dinheiro"]

    assert campo.para_banco(Decimal("19.90")) == 1990
    assert campo.do_banco(1990) == Decimal("19.90")


def test_dinheiro_nao_perde_centavo_somando():
    # Em float, 0.1 + 0.2 não dá 0.3; em centavos inteiros, dá.
    campo = Exemplo._campos["dinheiro"]
    total = campo.do_banco(campo.para_banco(Decimal("0.10")) + campo.para_banco(Decimal("0.20")))

    assert total == Decimal("0.30")


def test_booleano_vai_e_volta_como_inteiro():
    campo = Exemplo._campos["booleano"]

    assert campo.para_banco(True) == 1
    assert campo.do_banco(0) is False


def test_data_e_datahora_vao_em_iso():
    assert Exemplo._campos["data"].para_banco(date(2026, 9, 21)) == "2026-09-21"
    assert Exemplo._campos["momento"].para_banco(datetime(2026, 9, 21, 10, 30)) == "2026-09-21 10:30:00"


def test_nulo_atravessa_a_conversao():
    for nome in ("dinheiro", "booleano", "data", "momento"):
        campo = Exemplo._campos[nome]
        assert campo.para_banco(None) is None
        assert campo.do_banco(None) is None


def test_a_definicao_da_coluna_sai_em_ddl():
    class Tabela(Modelo):
        nome = Texto(nulo=False, unico=True)

    definicao = Tabela._campos["nome"].definicao()

    assert "TEXT" in definicao
    assert "NOT NULL" in definicao
    assert "UNIQUE" in definicao


def test_a_chave_primaria_e_autoincremento():
    assert "AUTOINCREMENT" in Exemplo._campos["id"].definicao()


def test_o_campo_se_descreve_de_volta():
    assert repr(Exemplo._campos["texto"]) == "Texto('texto')"
