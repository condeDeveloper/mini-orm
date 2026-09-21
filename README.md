# mini-orm

ORM em Python puro sobre `sqlite3`: modelos declarativos, construtor de
consultas, mapa de identidade, controle de alterações e migrações versionadas.
Sem dependência nenhuma.

```python
from orm import Modelo, Sessao, Texto, Dinheiro, Inteiro

class Produto(Modelo):
    nome = Texto(nulo=False)
    preco = Dinheiro(nulo=False)
    estoque = Inteiro(padrao=0)

with Sessao("loja.db"):
    Produto.criar_tabela()
    Produto.criar(nome="caneta", preco="2.50", estoque=100)

    baratos = Produto.onde(preco__menor=10, estoque__maior=0).ordenar("preco").todos()
```

## Por que existe

Todo mundo usa ORM e quase ninguém sabe o que ele faz por baixo. São quatro
mecanismos independentes, e cada um resolve um problema específico:

**1. Descritores** — cada campo é um descritor, então ele intercepta toda
escrita no atributo. É daí que sai o controle de alterações: o ORM sabe que só
o `nome` mudou sem precisar comparar o objeto com uma cópia. O `UPDATE`
resultante toca só a coluna alterada, o que além de ser menos escrita evita
sobrescrever com valor velho uma coluna que outro processo mexeu.

**2. Metaclasse** — recolhe os campos declarados, deduz o nome da tabela e
monta o esquema antes de a classe existir. É o que permite o modelo ficar
limpo, só com os campos.

**3. Mapa de identidade** — impede que a mesma linha vire dois objetos na
memória. Sem ele, carregar o cliente 7 duas vezes daria dois objetos, e alterar
um deixaria o outro desatualizado. Com ele:

```python
um = Cliente.buscar(7)
outro = Cliente.onde(nome="Maria").primeiro()
um.nome = "Maria Souza"

outro.nome        # "Maria Souza" — é o mesmo objeto
um is outro       # True
```

**4. Consulta preguiçosa** — a consulta se monta por partes e só vira SQL
quando alguém pede o resultado, o que a torna imutável e reaproveitável.

## Campos

| Campo | Coluna | Detalhe |
| --- | --- | --- |
| `Texto` | `TEXT` | com `tamanho` opcional |
| `Inteiro` | `INTEGER` | recusa `bool`, que em Python é subclasse de `int` |
| `Real` | `REAL` | |
| `Booleano` | `INTEGER` | o SQLite não tem booleano; vai 0/1 e volta `bool` |
| `Dinheiro` | `INTEGER` | **guardado em centavos** |
| `Data` / `DataHora` | `TEXT` | ISO 8601 |
| `ChaveEstrangeira` | `INTEGER` | gera a cláusula `FOREIGN KEY` com `ON DELETE` |

O `Dinheiro` em centavos é a decisão mais importante da lista. Guardar valor
monetário como `REAL` é o caminho curto para o centavo que some — em ponto
flutuante, `0.10 + 0.20` não dá `0.30`. Em centavos inteiros, dá.

E a conversão é do ORM, não de quem usa: você filtra em reais.

```python
Produto.onde(preco__menor=10)        # dez reais, não dez centavos
Produto.onde(preco__em=["2.50", "15.00"])
```

## Consultas

```python
Produto.onde(nome="caneta")
Produto.onde(estoque__maior=0, preco__menor=10)   # os filtros se somam com E
Produto.onde(nome__contem="cad")
Produto.onde(nome__em=["caneta", "lapis"])
Produto.onde(peso__nulo=True)

Produto.consulta().ordenar("-preco", "nome").limite(10, pular=20)
Produto.consulta().apenas("nome", "preco")        # tuplas, não objetos

Produto.onde(estoque=0).contar()
Produto.onde(estoque=0).existe()
Produto.onde(estoque=0).remover()
```

Operadores: `igual` (o padrão), `diferente`, `maior`, `maior_ou_igual`,
`menor`, `menor_ou_igual`, `contem`, `comeca_com`, `termina_com`, `em`, `nulo`.

Para `OU` e `NÃO`, as condições se combinam:

```python
from orm import condicao

barato = condicao("preco__menor", 500)
sem_estoque = condicao("estoque", 0)

Produto.onde(barato | ~sem_estoque)
```

### Sobre injeção de SQL

Nenhum valor entra colado no texto do SQL — nem no `IN`, que gera um marcador
por item. O texto da consulta não muda com o valor, por mais hostil que ele
seja, e há teste guardando isso:

```python
Cliente.criar(nome="'; DROP TABLE clientes; --")   # vira um nome, não um comando
```

## Sessão e transação

```python
with Sessao("loja.db") as sessao:
    with sessao.transacao():
        pedido.salvar()
        estoque.salvar()
    # confirma no fim; qualquer exceção desfaz tudo
```

Ao desfazer, o mapa de identidade é esvaziado: manter em memória um objeto com
valores que o banco já descartou seria servir dado que não existe mais.

## Migrações

```python
migrador = Migrador(sessao)

@migrador.migracao(1, "acrescenta desconto")
def _(s):
    s.executar("ALTER TABLE produtos ADD COLUMN desconto INTEGER")

migrador.migrar()      # aplica só o que falta, na ordem
migrador.versao_atual  # 1
```

Cada migração roda na própria transação. Se a terceira falhar, as duas
primeiras continuam aplicadas e registradas — é só corrigir e rodar de novo.

## Estrutura

```
orm/campos.py     os descritores, a conversão Python ↔ banco e o DDL da coluna
orm/modelo.py     a metaclasse, o CRUD e o controle de alterações
orm/consulta.py   condições, construtor preguiçoso e geração do SQL
orm/sessao.py     conexão, mapa de identidade e transação
orm/migracao.py   migrações versionadas
```

## Rodando

```bash
pip install -e ".[dev]"
pytest
```

107 testes, sem dependência de runtime. Python 3.10 ou mais novo.

## Limites conhecidos

- **Só SQLite.** O DDL e alguns tipos são específicos dele.
- **Sem relacionamentos navegáveis.** A `ChaveEstrangeira` gera a restrição no
  banco, mas não existe `pedido.cliente` — só `pedido.cliente_id`. Carregamento
  preguiçoso de relação é um projeto à parte.
- Sem `JOIN` no construtor de consultas; para isso, `sessao.buscar()` com SQL.
- Sem agregações além de `COUNT`.
- Sem pool de conexões nem suporte a assíncrono.
- O pluralizador do nome da tabela é ingênuo de propósito; quando ele erra, o
  modelo declara `_tabela` e pronto.

## Licença

MIT.
