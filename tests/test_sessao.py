import pytest

from orm import ErroDeSessao, Migrador, Sessao
from tests.conftest import Cliente, Produto


class TestIdentidade:
    def test_a_mesma_linha_vira_o_mesmo_objeto(self, sessao):
        cliente = Cliente.criar(nome="Maria")

        um = Cliente.onde(id=cliente.id).primeiro()
        outro = Cliente.onde(id=cliente.id).primeiro()

        assert um is outro

    def test_alterar_um_reflete_no_outro(self, sessao):
        # É exatamente o bug que o mapa de identidade evita: sem ele, seriam
        # dois objetos e um ficaria desatualizado.
        cliente = Cliente.criar(nome="Maria")

        um = Cliente.buscar(cliente.id)
        outro = Cliente.onde(nome="Maria").primeiro()
        um.nome = "Maria Souza"

        assert outro.nome == "Maria Souza"

    def test_buscar_usa_o_mapa_antes_do_banco(self, sessao):
        cliente = Cliente.criar(nome="Maria")
        sessao.consultas.clear()

        Cliente.buscar(cliente.id)

        assert not [sql for sql in sessao.consultas if sql.startswith("SELECT")]

    def test_esvaziar_forca_a_releitura(self, sessao):
        cliente = Cliente.criar(nome="Maria")
        sessao.esvaziar_identidade()

        outro = Cliente.buscar(cliente.id)

        assert outro is not cliente
        assert outro.nome == "Maria"

    def test_remover_tira_do_mapa(self, sessao):
        cliente = Cliente.criar(nome="Maria")
        assert sessao.carregados == 1

        cliente.remover()

        assert sessao.carregados == 0

    def test_o_objeto_novo_nao_entra_no_mapa(self, sessao):
        Cliente(nome="Maria")

        assert sessao.carregados == 0


class TestTransacao:
    def test_confirma_no_fim(self, sessao):
        with sessao.transacao():
            Cliente.criar(nome="Maria")

        assert Cliente.contar() == 1

    def test_desfaz_quando_algo_escapa(self, sessao):
        with pytest.raises(RuntimeError):
            with sessao.transacao():
                Cliente.criar(nome="Maria")
                raise RuntimeError("deu ruim")

        assert Cliente.contar() == 0

    def test_desfazer_esvazia_o_mapa(self, sessao):
        with pytest.raises(RuntimeError):
            with sessao.transacao():
                Cliente.criar(nome="Maria")
                raise RuntimeError("deu ruim")

        # Manter no mapa um objeto que o banco já descartou seria servir dado
        # que não existe mais.
        assert sessao.carregados == 0

    def test_confirmar_e_desfazer_na_mao(self, sessao):
        Cliente.criar(nome="Maria")
        sessao.confirmar()

        Cliente.criar(nome="João")
        sessao.desfazer()

        assert Cliente.contar() == 1


class TestSessao:
    def test_sem_sessao_aberta_reclama(self):
        Sessao.corrente().fechar() if _tem_sessao() else None

        with pytest.raises(ErroDeSessao):
            Cliente.contar()

    def test_a_sessao_registra_as_consultas(self, sessao):
        Cliente.criar(nome="Maria")

        assert any(sql.startswith("INSERT") for sql in sessao.consultas)

    def test_o_eco_imprime_o_sql(self, capsys):
        with Sessao(eco=True) as aberta:
            aberta.executar("SELECT 1")

        assert "[sql]" in capsys.readouterr().out

    def test_a_chave_estrangeira_esta_ligada(self, sessao):
        ligada = sessao.buscar("PRAGMA foreign_keys")[0][0]

        assert ligada == 1


class TestMigracao:
    def test_aplica_na_ordem_e_marca(self, sessao):
        migrador = Migrador(sessao)
        aplicadas = []

        migrador.registrar(2, "segunda", lambda s: aplicadas.append(2))
        migrador.registrar(1, "primeira", lambda s: aplicadas.append(1))

        migrador.migrar()

        assert aplicadas == [1, 2]
        assert migrador.versao_atual == 2

    def test_nao_aplica_duas_vezes(self, sessao):
        migrador = Migrador(sessao)
        contador = []

        migrador.registrar(1, "uma", lambda s: contador.append(1))
        migrador.migrar()
        migrador.migrar()

        assert len(contador) == 1
        assert migrador.pendentes() == []

    def test_a_migracao_muda_o_esquema(self, sessao):
        migrador = Migrador(sessao)

        migrador.registrar(
            1,
            "acrescenta desconto",
            lambda s: s.executar("ALTER TABLE produtos ADD COLUMN desconto INTEGER"),
        )
        migrador.migrar()

        colunas = [linha[1] for linha in sessao.buscar("PRAGMA table_info(produtos)")]
        assert "desconto" in colunas

    def test_versao_repetida_reclama(self, sessao):
        migrador = Migrador(sessao)
        migrador.registrar(1, "uma", lambda s: None)

        with pytest.raises(Exception):
            migrador.registrar(1, "outra", lambda s: None)

    def test_versao_zero_reclama(self, sessao):
        from orm import Migracao

        with pytest.raises(Exception):
            Migracao(0, "invalida", lambda s: None)

    def test_a_falha_de_uma_nao_derruba_as_anteriores(self, sessao):
        migrador = Migrador(sessao)

        migrador.registrar(
            1, "cria", lambda s: s.executar("CREATE TABLE extra (id INTEGER PRIMARY KEY)")
        )
        migrador.registrar(2, "quebra", lambda s: s.executar("ISSO NAO E SQL"))

        with pytest.raises(Exception):
            migrador.migrar()

        assert migrador.versao_atual == 1
        assert len(migrador.pendentes()) == 1

    def test_o_decorador_registra(self, sessao):
        migrador = Migrador(sessao)

        @migrador.migracao(1, "pelo decorador")
        def _(s):
            s.executar("CREATE TABLE decorada (id INTEGER PRIMARY KEY)")

        migrador.migrar()

        assert migrador.versao_atual == 1

    def test_a_migracao_se_descreve_de_volta(self, sessao):
        migrador = Migrador(sessao)
        migrador.registrar(3, "terceira", lambda s: None)

        assert str(migrador.registradas[0]) == "0003 terceira"


def _tem_sessao() -> bool:
    try:
        Sessao.corrente()
        return True
    except ErroDeSessao:
        return False
