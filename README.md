# AIRE · Consumo e custos de observabilidade

Serviço Python de consulta para a frente de integração do AIRE. A v1 funciona offline com dois tenants e três referências de integração sintéticas. Todas as respostas analíticas identificam a origem sintética. Consulte a [matriz de provedores](docs/providers.md) para cobertura, permissões e homologação.

## Executar

Requer Python 3.12 e usa apenas a biblioteca padrão. A coleta usa SQLite e o servidor abre a base em modo de leitura. A identidade do tenant vem de um bearer token local exclusivo. Na integração corporativa, o gateway deve fornecer a identidade autenticada e o resolver de referências do AIRE.

~~~bash
python -m unittest discover -s tests -v
python -m aire collect
export TOKEN="$(python -c 'import secrets;print(secrets.token_urlsafe(32))')"
export AIRE_READ_TOKENS="$(python -c 'import json,os;print(json.dumps({"commerce-demo":os.environ["TOKEN"]}))')"
python -m aire serve
~~~

No segundo terminal, disponibilize o mesmo TOKEN. O serviço escuta em 127.0.0.1:8080.

~~~bash
curl -s http://127.0.0.1:8080/health
curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8080/v1/inventory
curl -s -H "Authorization: Bearer $TOKEN" 'http://127.0.0.1:8080/v1/report?start=2026-10-03&end=2026-10-05&product=metrics.custom'
curl -s -H "Authorization: Bearer $TOKEN" 'http://127.0.0.1:8080/v1/samples?day=2026-10-03&ref=dd-demo'
curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8080/v1/scenarios/example
~~~

### Docker

O comando utiliza o AIRE_READ_TOKENS definido acima. O volume nomeado mantém o checkpoint entre execuções.

~~~bash
docker build -t aire-cost-insights:v1 .
docker run --rm -p 127.0.0.1:8080:8080 -v aire-cost-data:/data -e AIRE_READ_TOKENS aire-cost-insights:v1
~~~

## API v1

| GET | Contrato |
|---|---|
| /health | Liveness local |
| /v1/inventory | Referências autorizadas, modelo de licença, produtos do manifesto sintético, medidores, unidades, agregações, retenção e ambientes conhecidos |
| /v1/report | start e end obrigatórios, UTC, fim exclusivo, até 366 dias. Filtros opcionais ref, environment e product. Retorna série diária, intervalo anterior de igual duração, variação absoluta, projeção de 30 dias, ranking entre ambientes com dados completos e oportunidades |
| /v1/samples | ref e day obrigatórios. Registros normalizados com tenant, referência, ambiente, medidor, intervalo, valor decimal ou nulo e identificador de origem |
| /v1/scenarios/example | Resultado do cenário comercial sintético do tenant autorizado |

[Exemplo completo de relatório](docs/report-example.json) · [Exemplo de cenário](docs/scenario-example.json). Valores decimais são strings. Ausência de valor é null. Custos do provedor retornam lista vazia quando nenhum extrato corresponde exatamente ao escopo e período. Um compromisso em nível de assinatura não é rateado implicitamente. Os filtros de tenant são rejeitados e referências de outro tenant não são consultáveis.

## Dados e coleta

Os arquivos em fixtures definem fontes reproduzíveis entre 1 e 8/out/2026 inclusive. O catálogo simula o contrato de integração com tenant, referência opaca, provedor, escopo autorizado, ambientes e referência da credencial. É um manifesto de testes, sem senhas ou cadastro operacional. O parser Datadog lê measurements por hora. O parser DPS lê data[].usage por ambiente. O custo reportado DPS é um extrato sintético separado no catálogo.

A coleta avança o checkpoint até o fim exclusivo solicitado. O SQLite funciona como cache persistente. O leitor não chama os provedores. A chave única combina tenant, integração, medidor, ambiente e início. Cada execução por integração é atômica. Um escritor serializado, limite padrão de 100 chamadas por integração e até três tentativas com backoff para timeout/erro de conexão. Uma repetição sem novos dias consome zero chamadas.

~~~bash
python -m aire --db replay.db collect --until 2026-10-05
python -m aire --db replay.db collect --until 2026-10-09
python -m aire --db replay.db collect --until 2026-10-09 --refresh
~~~

Refresh relê os três dias anteriores ao checkpoint (ou ao fim solicitado, se anterior) e reconcilia inclusive remoções. Use um fim anterior com refresh para revisar uma janela antiga. Lacunas de cobertura temporal ou valores nulos suprimem totais, variação e projeção que dependeriam desses dados. A data de referência da fixture é 9/out/2026 UTC. Os últimos três dias Datadog estão sinalizados como provisórios. Os rankings usam o consumo observado das séries completas da mesma integração e medidor. Não há ranking artificial quando só existe o total organizacional.

## Financeiro e cobertura

O simulador recebe um JSON parametrizado pelo operador. Suporta um medidor aditivo, um ambiente e um pool exclusivo para o período de liquidação completo indicado. A origem e a vigência são obrigatórias. A tarifa usa franquia, faixas progressivas, desconto sobre excedente, parcela fixa e piso contratual. Nenhuma conversão cambial é aplicada. Para pools compartilhados, compromissos anuais distribuídos entre capacidades ou SKUs com regras distintas, é necessário modelar e reconciliar o contrato antes de estimar a fatura.

~~~bash
python -m aire scenario fixtures/scenario.json --tenant commerce-demo
~~~

O cenário mede 52 GiB, simula a redução de 10 GiB e calcula USD 100 em ambos os cenários. A economia potencial é USD 0 e a economia observada fica desconhecida. O extrato sintético de USD 180 da assinatura abrange todos os ambientes e tem escopo diferente do cenário. Economia efetiva dependerá de uma mudança aprovada, evidência de implementação, comparação reconciliada e controle de mudanças de preço, volume e cobertura.

Para reproduzir uma oportunidade, consulte metrics.custom de 3 a 5/out, fim exclusivo. A média sobe de 110 para 150 séries. A oportunidade solicita testar a dimensão request_id e revalidar alertas, SLOs, dashboards e um incidente conhecido. A quantificação de redução fica pendente. Em 7/out falta uma hora do Datadog e em 6/out o ambiente lab do DPS contém valores indisponíveis. Esses casos exercitam a diferença entre ausência de dado, zero medido e ausência de atribuição.
