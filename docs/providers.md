# Cobertura de provedores

Documentação oficial consultada em 4 de novembro de 2026. A implementação lê fixtures locais. Os nomes de medidores e capacidades na fixture são exemplos do contrato normalizado. O cadastramento real precisa mapear os identificadores, unidades e agregações retornados pelo SKU do cliente.

| Fonte | Uso previsto | Acesso e lacunas |
|---|---|---|
| [Datadog Hourly Usage](https://docs.datadoghq.com/api/latest/usage-metering/get-hourly-usage-by-product-family/) | Medições por organização, hora e família. Paginar pelo cursor. | API key e App Key restrita a usage_read. Fixar site e public_id autorizado. Um agregado organizacional fica sem atribuição de ambiente. |
| [Datadog Usage Metering](https://docs.datadoghq.com/api/latest/usage-metering/) e [atribuição](https://docs.datadoghq.com/api/latest/usage-metering/get-hourly-usage-attribution/) | Uso pode atrasar até 72 horas. Atribuição por tags depende da configuração e cobertura do produto. | Acesso documentado para Pro e Enterprise. Confirmar habilitação e permissões na organização do cliente. Não somar atribuição ao total organizacional. |
| [Datadog Cost Details](https://docs.datadoghq.com/account_management/plan_and_usage/cost_details/) e [Estimated Cost](https://docs.datadoghq.com/api/latest/usage-metering/get-estimated-cost-across-your-account/) | Custos estimados do mês corrente e anterior, histórico por endpoint separado. | Confirmar acesso de organização pai e permissões de leitura de billing e usage para custos. Estimativa do provedor tem origem distinta de simulação AIRE e de fatura fechada. |
| [Dynatrace DPS usage v2](https://docs.dynatrace.com/docs/dynatrace-api/account-management-api/dynatrace-platform-subscription-api/usage/get-usage-environment) e [cost v3](https://docs.dynatrace.com/docs/dynatrace-api/account-management-api/dynatrace-platform-subscription-api/cost/get-cost-environment) | Uso e custo por ambiente e capacidade da assinatura. Preservar unitMeasure, intervalos e lastModifiedTime. | OAuth de conta com account-uac-read, accountUuid e subscriptionUuid autorizados. Restringir ambientes à integração. Homologar granularidade, fim do intervalo e correções. |
| [Dynatrace Classic](https://docs.dynatrace.com/docs/manage/account-management/license-subscription/license-overview-classic) | HU, HU-hours, DEM, DDU e ASU têm semânticas próprias. | Inventariar licença e export disponível. Coleta Classic pendente. Valores Classic não alimentam o simulador DPS. |

## Verificação por produto

- **Métricas customizadas.** A fixture separa a média horária de séries do volume aditivo. A presença de request_id é evidência sintética para investigação. Homologar quantidade de combinações de tags, dependências de dashboards, monitores e SLOs e efeito do SKU antes de quantificar redução.
- **Logs.** Manter ingestão em bytes, indexação em eventos, política de retenção em dias e retenção faturada em GiB-dia como grandezas independentes. Validar índices, filtros, arquivos, reidratação e requisitos de investigação.
- **APM.** Preservar ingestão e spans indexados em medidores separados. Homologar retenção de erros, latência de cauda, correlação e diagnóstico nas jornadas críticas antes de propor amostragem.
- **Infraestrutura.** Contagem média observada de hosts e containers não reproduz automaticamente o cálculo mensal faturável. Confirmar agregação, compromisso, franquias e excedentes do contrato.
- **DPS.** Vincular assinatura, capacidades e ambientes com a plataforma principal. Validar consumo consolidado e créditos do compromisso na moeda contratual. O cenário de pool exclusivo da fixture só se aplica se a abrangência do contrato tiver sido conferida.

## Maturidade

Parsers, cursor paginado, orçamento de chamadas, repetição de falhas transitórias e checkpoint são exercitados localmente. Os adaptadores não abrem conexões externas. Transporte HTTPS, renovação OAuth, Retry-After de respostas 429, importação de fatura, atribuição por tags, verificação automática de retenção, Classic e leitura do cofre central dependem da homologação. Trial valida formatos, acesso e fluxo. A validação financeira requer contrato vigente, extrato de consumo e reconciliação com fatura no mesmo escopo, moeda e período.
