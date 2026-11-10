# Relatório de manutenção preditiva - Downtime

## Visão geral

Visão geral do conjunto Downtime: 2500 leituras de sensores de 3 máquinas em 3 linhas de montagem, de 2021-11-24 a 2022-07-03. Ao todo, 1265 leituras (50,6%) terminaram em falha de máquina (Machine_Failure). Por máquina: Makino-L1-Unit1-2013 (Shopfloor-L1): 874 leituras, 454 falhas, taxa de 51,9%; Makino-L2-Unit1-2015 (Shopfloor-L2): 808 leituras, 396 falhas, taxa de 49,0%; Makino-L3-Unit1-2015 (Shopfloor-L3): 818 leituras, 415 falhas, taxa de 50,7%. A máquina com maior taxa de falha é Makino-L1-Unit1-2013 (51,9%).

## Falhas por mês

Falhas por mês no conjunto Downtime: 2021-11: 1 falha em 1 leitura; 2021-12: 13 falhas em 24 leituras; 2022-01: 87 falhas em 178 leituras; 2022-02: 296 falhas em 597 leituras; 2022-03: 533 falhas em 1048 leituras; 2022-04: 280 falhas em 527 leituras; 2022-05: 50 falhas em 116 leituras; 2022-06: 4 falhas em 8 leituras; 2022-07: 1 falha em 1 leitura. O mês com mais falhas foi 2022-03 (533 falhas). Os meses com poucas leituras têm taxas pouco confiáveis.

## Perfil dos sensores

Comparação das médias dos sensores entre leituras com falha e sem falha, ordenada pela maior diferença: pressão hidráulica: 84,77 com falha x 118,51 sem falha (-28,5%); força de corte: 3,06 com falha x 2,50 sem falha (+22,1%); torque: 22,79 com falha x 27,76 sem falha (-17,9%); temperatura do coolant: 19,98 com falha x 17,13 sem falha (+16,7%); rotação do spindle: 21.430,71 com falha x 19.204,33 sem falha (+11,6%); pressão do coolant: 5,11 com falha x 4,78 sem falha (+7,1%); vibração do spindle: 1,00 com falha x 1,02 sem falha (-1,2%); temperatura do rolamento do spindle: 34,99 com falha x 35,14 sem falha (-0,4%); vibração da ferramenta: 25,37 com falha x 25,45 sem falha (-0,3%); temperatura do óleo hidráulico: 47,57 com falha x 47,67 sem falha (-0,2%); tensão: 349,26 com falha x 348,73 sem falha (+0,2%); pressão do sistema de ar: 6,50 com falha x 6,50 sem falha (+0,1%). Diferenças pequenas indicam que o sensor, sozinho, não distingue as falhas.

## Zonas de risco por sensor

Sensor pressão hidráulica (hydraulic_pressure, em bar). Taxa de falha por faixa de valores (quintis):
15,33 a 71,64 bar: 94,8% de falha (501 leituras); 71,64 a 89,46 bar: 70,6% de falha (506 leituras); 89,46 a 110,82 bar: 50,1% de falha (493 leituras); 110,82 a 133,27 bar: 7,8% de falha (500 leituras); 133,27 a 191,00 bar: 29,4% de falha (500 leituras). Faixas de risco (taxa de falha pelo menos 1,4 vez a geral de 50,6%): baixa (15,33 a 71,64 bar, 94,8%). Faixas com poucas falhas: 110,82 a 133,27 bar (7,8%).

Sensor pressão do coolant (coolant_pressure, em bar). Taxa de falha por faixa de valores (quintis):
0,32 a 4,29 bar: 24,2% de falha (500 leituras); 4,29 a 4,78 bar: 100,0% de falha (500 leituras); 4,78 a 5,15 bar: 54,0% de falha (500 leituras); 5,15 a 5,61 bar: 15,6% de falha (500 leituras); 5,61 a 11,35 bar: 59,2% de falha (500 leituras). Faixas de risco (taxa de falha pelo menos 1,4 vez a geral de 50,6%): intermediária (4,29 a 4,78 bar, 100,0%). Faixas com poucas falhas: 5,15 a 5,61 bar (15,6%).

Sensor pressão do sistema de ar (air_system_pressure, em bar). Taxa de falha por faixa de valores (quintis):
5,06 a 6,16 bar: 48,4% de falha (500 leituras); 6,16 a 6,40 bar: 51,2% de falha (500 leituras); 6,40 a 6,61 bar: 52,0% de falha (500 leituras); 6,61 a 6,85 bar: 52,0% de falha (500 leituras); 6,85 a 7,97 bar: 49,4% de falha (500 leituras). Nenhuma faixa tem taxa de falha muito acima da geral (50,6%): a pressão do sistema de ar sozinha não é um bom indicador de falha neste conjunto.

Sensor temperatura do coolant (coolant_temperature, em °C). Taxa de falha por faixa de valores (quintis):
4,10 a 8,80 °C: 38,1% de falha (501 leituras); 8,80 a 16,10 °C: 50,4% de falha (500 leituras); 16,10 a 23,20 °C: 38,0% de falha (508 leituras); 23,20 a 26,40 °C: 56,4% de falha (551 leituras); 26,40 a 98,20 °C: 72,3% de falha (440 leituras). Faixas de risco (taxa de falha pelo menos 1,4 vez a geral de 50,6%): alta (26,40 a 98,20 °C, 72,3%).

Sensor temperatura do óleo hidráulico (hydraulic_oil_temperature, em °C). Taxa de falha por faixa de valores (quintis):
35,20 a 44,50 °C: 50,7% de falha (513 leituras); 44,50 a 46,70 °C: 51,7% de falha (491 leituras); 46,70 a 48,60 °C: 50,1% de falha (513 leituras); 48,60 a 50,80 °C: 51,3% de falha (497 leituras); 50,80 a 61,40 °C: 49,2% de falha (486 leituras). Nenhuma faixa tem taxa de falha muito acima da geral (50,6%): a temperatura do óleo hidráulico sozinha não é um bom indicador de falha neste conjunto.

Sensor temperatura do rolamento do spindle (spindle_bearing_temperature, em °C). Taxa de falha por faixa de valores (quintis):
22,60 a 31,80 °C: 53,3% de falha (508 leituras); 31,80 a 34,10 °C: 51,7% de falha (513 leituras); 34,10 a 36,10 °C: 47,6% de falha (492 leituras); 36,10 a 38,20 °C: 49,9% de falha (497 leituras); 38,20 a 49,50 °C: 50,4% de falha (490 leituras). Nenhuma faixa tem taxa de falha muito acima da geral (50,6%): a temperatura do rolamento do spindle sozinha não é um bom indicador de falha neste conjunto.

Sensor vibração do spindle (spindle_vibration, em µm). Taxa de falha por faixa de valores (quintis):
0,01 a 0,72 µm: 52,2% de falha (500 leituras); 0,72 a 0,93 µm: 51,2% de falha (500 leituras); 0,93 a 1,10 µm: 51,2% de falha (502 leituras); 1,10 a 1,29 µm: 47,3% de falha (499 leituras); 1,29 a 2,00 µm: 51,1% de falha (499 leituras). Nenhuma faixa tem taxa de falha muito acima da geral (50,6%): a vibração do spindle sozinha não é um bom indicador de falha neste conjunto.

Sensor vibração da ferramenta (tool_vibration, em µm). Taxa de falha por faixa de valores (quintis):
2,16 a 20,03 µm: 51,4% de falha (500 leituras); 20,03 a 23,91 µm: 49,6% de falha (500 leituras); 23,91 a 27,03 µm: 50,6% de falha (500 leituras); 27,03 a 30,77 µm: 51,6% de falha (500 leituras); 30,77 a 45,73 µm: 49,8% de falha (500 leituras). Nenhuma faixa tem taxa de falha muito acima da geral (50,6%): a vibração da ferramenta sozinha não é um bom indicador de falha neste conjunto.

Sensor rotação do spindle (spindle_speed, em RPM). Taxa de falha por faixa de valores (quintis):
12.788,00 a 17.726,00 RPM: 27,5% de falha (581 leituras); 17.726,00 a 19.258,20 RPM: 68,3% de falha (419 leituras); 19.258,20 a 20.801,00 RPM: 58,6% de falha (519 leituras); 20.801,00 a 23.372,60 RPM: 16,8% de falha (481 leituras); 23.372,60 a 27.957,00 RPM: 86,8% de falha (500 leituras). Faixas de risco (taxa de falha pelo menos 1,4 vez a geral de 50,6%): alta (23.372,60 a 27.957,00 RPM, 86,8%). Faixas com poucas falhas: 20.801,00 a 23.372,60 RPM (16,8%).

Sensor tensão (voltage, em V). Taxa de falha por faixa de valores (quintis):
202,00 a 311,00 V: 51,1% de falha (503 leituras); 311,00 a 337,00 V: 51,3% de falha (503 leituras); 337,00 a 361,00 V: 48,5% de falha (517 leituras); 361,00 a 388,00 V: 49,7% de falha (481 leituras); 388,00 a 479,00 V: 52,4% de falha (496 leituras). Nenhuma faixa tem taxa de falha muito acima da geral (50,6%): a tensão sozinha não é um bom indicador de falha neste conjunto.

Sensor torque (torque, em Nm). Taxa de falha por faixa de valores (quintis):
14,11 a 20,56 Nm: 83,8% de falha (500 leituras); 20,56 a 23,74 Nm: 1,0% de falha (500 leituras); 23,74 a 25,81 Nm: 90,8% de falha (500 leituras); 25,81 a 31,62 Nm: 73,5% de falha (509 leituras); 31,62 a 55,55 Nm: 2,6% de falha (491 leituras). Faixas de risco (taxa de falha pelo menos 1,4 vez a geral de 50,6%): baixa (14,11 a 20,56 Nm, 83,8%); intermediária (23,74 a 25,81 Nm, 90,8%); intermediária (25,81 a 31,62 Nm, 73,5%). Faixas com poucas falhas: 20,56 a 23,74 Nm (1,0%); 31,62 a 55,55 Nm (2,6%).

Sensor força de corte (cutting, em kN). Taxa de falha por faixa de valores (quintis):
1,80 a 2,08 kN: 3,0% de falha (500 leituras); 2,08 a 2,62 kN: 79,5% de falha (508 leituras); 2,62 a 2,90 kN: 50,4% de falha (498 leituras); 2,90 a 3,55 kN: 32,0% de falha (581 leituras); 3,55 a 3,93 kN: 99,0% de falha (413 leituras). Faixas de risco (taxa de falha pelo menos 1,4 vez a geral de 50,6%): intermediária (2,08 a 2,62 kN, 79,5%); alta (3,55 a 3,93 kN, 99,0%). Faixas com poucas falhas: 1,80 a 2,08 kN (3,0%).

## Diagnósticos

Diagnóstico de superaquecimento pela temperatura do coolant: leituras acima de 28,70 °C (percentil 90 do histórico). Foram 206 leituras nessa condição, com 163 falhas (79,1%), taxa maior que a taxa geral de 50,6%. Essa condição está associada a mais falhas do que o normal. Por máquina: Makino-L1-Unit1-2013: 60 leituras, 78,3% de falha; Makino-L2-Unit1-2015: 68 leituras, 86,8% de falha; Makino-L3-Unit1-2015: 78 leituras, 73,1% de falha.

Diagnóstico de superaquecimento pela temperatura do óleo hidráulico: leituras acima de 52,40 °C (percentil 90 do histórico). Foram 241 leituras nessa condição, com 120 falhas (49,8%), taxa parecida com a taxa geral de 50,6%. Essa condição, sozinha, não muda a chance de falha. Por máquina: Makino-L1-Unit1-2013: 81 leituras, 53,1% de falha; Makino-L2-Unit1-2015: 77 leituras, 42,9% de falha; Makino-L3-Unit1-2015: 83 leituras, 53,0% de falha.

Diagnóstico de superaquecimento pela temperatura do rolamento do spindle: leituras acima de 40,00 °C (percentil 90 do histórico). Foram 242 leituras nessa condição, com 127 falhas (52,5%), taxa parecida com a taxa geral de 50,6%. Essa condição, sozinha, não muda a chance de falha. Por máquina: Makino-L1-Unit1-2013: 84 leituras, 57,1% de falha; Makino-L2-Unit1-2015: 70 leituras, 54,3% de falha; Makino-L3-Unit1-2015: 88 leituras, 46,6% de falha.

Diagnóstico de torque elevado pelo torque: leituras acima de 33,92 Nm (percentil 90 do histórico). Foram 236 leituras nessa condição, com 5 falhas (2,1%), taxa menor que a taxa geral de 50,6%. Nessa condição as falhas são menos frequentes do que o normal. Por máquina: Makino-L1-Unit1-2013: 74 leituras, 1,4% de falha; Makino-L2-Unit1-2015: 80 leituras, 2,5% de falha; Makino-L3-Unit1-2015: 82 leituras, 2,4% de falha.

Diagnóstico de torque baixo pelo torque: leituras abaixo de 16,45 Nm (percentil 10 do histórico). Foram 226 leituras nessa condição, com 226 falhas (100,0%), taxa maior que a taxa geral de 50,6%. Essa condição está associada a mais falhas do que o normal. Por máquina: Makino-L1-Unit1-2013: 85 leituras, 100,0% de falha; Makino-L2-Unit1-2015: 80 leituras, 100,0% de falha; Makino-L3-Unit1-2015: 61 leituras, 100,0% de falha.

Diagnóstico de pressão hidráulica baixa pela pressão hidráulica: leituras abaixo de 62,34 bar (percentil 10 do histórico). Foram 250 leituras nessa condição, com 248 falhas (99,2%), taxa maior que a taxa geral de 50,6%. Essa condição está associada a mais falhas do que o normal. Por máquina: Makino-L1-Unit1-2013: 86 leituras, 98,8% de falha; Makino-L2-Unit1-2015: 83 leituras, 98,8% de falha; Makino-L3-Unit1-2015: 81 leituras, 100,0% de falha.

## Recomendações por máquina

Recomendação de manutenção para a máquina Makino-L1-Unit1-2013 (Shopfloor-L1), com base nas 20 leituras mais recentes (2022-05-10 a 2022-07-03): risco estimado moderado (51,2%), com 10 falhas registradas nesse intervalo. Sensores em faixa de risco:
- Força de corte na faixa intermediária (2,08 a 2,62 kN) em 11 das 20 leituras recentes; historicamente 79,5% das leituras nessa faixa terminaram em falha. Ação sugerida: acompanhar a força de corte e comparar com a faixa usual da máquina.
- Torque na faixa baixa (14,11 a 20,56 Nm) em 10 das 20 leituras recentes; historicamente 83,8% das leituras nessa faixa terminaram em falha. Ação sugerida: investigar perda de carga: ferramenta quebrada, escorregamento ou falha no acionamento.
- Pressão do coolant na faixa intermediária (4,29 a 4,78 bar) em 4 das 20 leituras recentes; historicamente 100,0% das leituras nessa faixa terminaram em falha. Ação sugerida: acompanhar a pressão do coolant e comparar com a faixa usual da máquina.
- Pressão hidráulica na faixa baixa (15,33 a 71,64 bar) em 2 das 20 leituras recentes; historicamente 94,8% das leituras nessa faixa terminaram em falha. Ação sugerida: inspecionar bomba hidráulica, vazamentos, filtros e nível de óleo.

Nota: o risco estimado é a média das taxas históricas de falha das faixas em que cada sensor indicador (pressão do coolant, temperatura do coolant, força de corte, pressão hidráulica, rotação do spindle, torque) se encontra; é uma heurística baseada em frequência, não um modelo treinado.

Recomendação de manutenção para a máquina Makino-L2-Unit1-2015 (Shopfloor-L2), com base nas 20 leituras mais recentes (2022-05-14 a 2022-06-19): risco estimado moderado (53,8%), com 12 falhas registradas nesse intervalo. Sensores em faixa de risco:
- Torque na faixa baixa (14,11 a 20,56 Nm) em 13 das 20 leituras recentes; historicamente 83,8% das leituras nessa faixa terminaram em falha. Ação sugerida: investigar perda de carga: ferramenta quebrada, escorregamento ou falha no acionamento.
- Pressão do coolant na faixa intermediária (4,29 a 4,78 bar) em 9 das 20 leituras recentes; historicamente 100,0% das leituras nessa faixa terminaram em falha. Ação sugerida: acompanhar a pressão do coolant e comparar com a faixa usual da máquina.
- Força de corte na faixa intermediária (2,08 a 2,62 kN) em 7 das 20 leituras recentes; historicamente 79,5% das leituras nessa faixa terminaram em falha. Ação sugerida: acompanhar a força de corte e comparar com a faixa usual da máquina.
- Pressão hidráulica na faixa baixa (15,33 a 71,64 bar) em 3 das 20 leituras recentes; historicamente 94,8% das leituras nessa faixa terminaram em falha. Ação sugerida: inspecionar bomba hidráulica, vazamentos, filtros e nível de óleo.

Nota: o risco estimado é a média das taxas históricas de falha das faixas em que cada sensor indicador (pressão do coolant, temperatura do coolant, força de corte, pressão hidráulica, rotação do spindle, torque) se encontra; é uma heurística baseada em frequência, não um modelo treinado.

Recomendação de manutenção para a máquina Makino-L3-Unit1-2015 (Shopfloor-L3), com base nas 20 leituras mais recentes (2022-05-06 a 2022-06-07): risco estimado moderado (51,0%), com 8 falhas registradas nesse intervalo. Sensores em faixa de risco:
- Torque na faixa intermediária (25,81 a 31,62 Nm) em 10 das 20 leituras recentes; historicamente 73,5% das leituras nessa faixa terminaram em falha. Ação sugerida: acompanhar o torque e comparar com a faixa usual da máquina.
- Força de corte na faixa intermediária (2,08 a 2,62 kN) em 7 das 20 leituras recentes; historicamente 79,5% das leituras nessa faixa terminaram em falha. Ação sugerida: acompanhar a força de corte e comparar com a faixa usual da máquina.
- Pressão do coolant na faixa intermediária (4,29 a 4,78 bar) em 6 das 20 leituras recentes; historicamente 100,0% das leituras nessa faixa terminaram em falha. Ação sugerida: acompanhar a pressão do coolant e comparar com a faixa usual da máquina.
- Pressão hidráulica na faixa baixa (15,33 a 71,64 bar) em 5 das 20 leituras recentes; historicamente 94,8% das leituras nessa faixa terminaram em falha. Ação sugerida: inspecionar bomba hidráulica, vazamentos, filtros e nível de óleo.

Nota: o risco estimado é a média das taxas históricas de falha das faixas em que cada sensor indicador (pressão do coolant, temperatura do coolant, força de corte, pressão hidráulica, rotação do spindle, torque) se encontra; é uma heurística baseada em frequência, não um modelo treinado.

## Metodologia

Metodologia dos relatórios do Downtime: cada sensor foi dividido em 5 faixas com o mesmo número de leituras (quintis). Uma faixa é de risco quando tem pelo menos 50 leituras e taxa de falha pelo menos 1,4 vez a taxa geral (50,6%); é segura quando a taxa é de no máximo 20,0%. Os diagnósticos de superaquecimento e torque usam os percentis 90 e 10 do histórico como limites. No próprio histórico, o risco estimado médio das leituras com falha é 36,1 pontos percentuais maior que o das leituras sem falha; como é medido nos mesmos dados usados para definir as faixas, esse número é otimista.
