# Аналитика производительности IT‑команд для топ‑менеджмента: визуализация, AI‑суммаризация и архитектура дэшбордов

> **Контекст.** Сервис анализа Jira‑данных для 1–5 команд по 5–10 человек (10–50 человек суммарно). Основной потребитель отчётности — C‑level (CTO/CIO/CPO/CEO/CFO‑tech) и Heads of Engineering. Ключевое ограничение: **30–60 секунд на считывание главного экрана**. Аналитика поверх Jira генерируется AI: summary, anomaly detection, trend explanations, recommendations.
>
> **Рекомендуемый визуальный стиль (референс инфографики):** тёмно‑синий навигационный дэшборд (bg `#0d1c33`, sidebar `#091527`, карточки `#0f2340`, бордюры `#1e3356`); cyan‑акценты `#00c9c8/#4db8e8`; жёлтый `#f5c842` для предупреждений; шрифт **Segoe UI**. Базовая раскладка: левый sidebar с SVG‑иконками + двухколоночная сетка карточек (donut‑chart, горизонтальные progress bars, 2×2 stat boxes, flow‑diagram, top‑3 список, star‑ratings). Этот стиль использовать как «design reference» по умолчанию для executive‑экранов.

---

## Часть I. Резюме для руководства (Executive Summary)

**Тезис №1.** Ценность не в количестве метрик, а в **иерархии**. Для C‑level достаточно 5–9 показателей на одном экране, разделённых на четыре линзы: *Delivery Health, Predictability, Risk, Quality*. Всё остальное — operational drill‑downs, скрытые за progressive disclosure.

**Тезис №2.** Топ‑менеджмент редко смотрит на абсолютные значения. Решающую ценность дают **тренд (Δ нед./мес.), статус‑светофор и AI‑интерпретация «почему»** — именно эту триаду нужно делать ядром каждой карточки.

**Тезис №3.** Метрики DORA остаются индустриальным стандартом, но для команды 5–10 человек на одной Jira их **недостаточно**: нужны flow‑метрики (cycle time, throughput, WIP, sprint predictability) и, опционально, корреляция с GitHub PR. AI‑суммаризатор должен объяснять корреляции между метриками — это и есть «McKinsey‑слой» сервиса.

**Тезис №4.** Главный анти‑паттерн — превратить дэшборд в инструмент микро‑менеджмента (developer leaderboards, individual velocity). Это разрушает доверие команд и даёт CTO фальшивый сигнал. Все рекомендации Gartner Market Guide for Software Engineering Intelligence (2024), Nicole Forsgren, McKinsey (после ответа Pragmatic Engineer/Kent Beck) и Swarmia сходятся на «team‑level only, system‑level outcomes».

**Тезис №5.** AI‑слой должен быть **grounded** — каждое утверждение в нарративе обязано иметь ссылку на конкретный Jira‑объект (issue key, sprint, period). Это критично с учётом подтверждённых исследованиями уровней галлюцинаций LLM (28–40% при свободной генерации; 1–3% при строгой RAG‑схеме). Выбор архитектуры: **structured prompt + JSON‑schema ответ + post‑hoc verification** против необработанных Jira‑метрик.

**Тезис №6.** Стек, оптимальный для размера 10–50 человек и executive‑аудитории: фронтенд React + **Apache ECharts** (либо Recharts для простых карточек), бэкенд на Python/Node с DuckDB/ClickHouse для агрегатов, AI‑слой через function‑calling LLM (GPT‑4‑class) с retrieval над собственным семантическим слоем поверх Jira REST API.

---

## Часть II. Engineering & Delivery Metrics — что измерять и как это видит топ‑менеджер

### 1. Иерархия метрик (4 уровня)

| Уровень | Аудитория | Назначение | Кол‑во метрик на экране |
|---|---|---|---|
| **L1 — Strategic / Executive** | CEO, CFO, CTO, Board | «Здоровье портфеля», бизнес‑риск | 5–7 |
| **L2 — Tactical / Delivery** | Head of Engineering, Delivery Director | Прогнозируемость доставки, узкие места | 8–12 |
| **L3 — Operational** | Engineering Manager, Tech Lead | Поток, ревью, бэклог | 12–20 |
| **L4 — Diagnostic** | Сама команда | Корневой анализ инцидентов | drill‑down |

Сервис должен поддерживать все четыре, **но дефолтный экран открывается на L1**.

### 2. Полный каталог метрик из Jira (и как они связаны с PR/CI, если интеграция включена)

#### 2.1 DORA‑квартет (industry baseline)

| Метрика | Что значит | Как достать из Jira | Что читает CEO/CTO | Бенчмарк (DORA 2024) |
|---|---|---|---|---|
| **Deployment Frequency (DF)** | Частота релизов в прод | Jira «Released» versions, либо событие `fix-version` + статус | «Скорость попадания ценности в руки клиента» | Elite: on‑demand; High: 1/день–1/нед; Low: 1/мес+ |
| **Lead Time for Changes (LTC)** | От первого коммита/issue start до прода | Jira: `created → status changed to Released` | «Сколько часов от идеи до клиента» | Elite: <1 день; High: 1д–1нед |
| **Change Failure Rate (CFR)** | % деплоев, потребовавших hotfix | Jira: `bug` + `hotfix` linked to release | «Качество доставки» | Elite: ≤5%; Low: >40% |
| **Failed Deployment Recovery Time** (бывш. MTTR) | Время восстановления после сбойного деплоя | Jira: incident issue created→resolved | «Устойчивость» | Elite: <1 час |

> **Новое в DORA 2024:** добавлена пятая метрика — **Rework Rate** (доля незапланированных деплоев на исправление user‑visible проблем). Полезна как «честная» альтернатива CFR в сервисах с feature flags.

**Визуализация для C‑level:** четыре KPI‑карточки в формате `значение + тренд‑спарклайн + цветовой бейдж (Elite/High/Medium/Low)`. Это «канонический Four Keys dashboard» Google. Никаких таблиц.

#### 2.2 Flow‑метрики (Jira‑native, главное для команд 5–10)

| Метрика | Сигнал бизнесу | Как считается | Лучшая визуализация |
|---|---|---|---|
| **Cycle Time** (от In Progress → Done) | «Скорость превращения идеи в результат» | Jira changelog: разница между `status WIP` и `Done` | **Scatter plot** (точка = issue, ось X = дата завершения, ось Y = дни). 50/85/95 процентильные линии. |
| **Throughput** (issues или story points за период) | «Производительность системы» | Count of `Done` per week/sprint | Bar chart по неделям + 3‑sprint moving average |
| **WIP** (Work in Progress) | Перегрузка/контекст‑свитчинг | Count of issues in active statuses | Гистограмма + WIP‑limit reference line |
| **Aging WIP** | «Зависшая работа» | Days since `status=In Progress` для незакрытых | Aging chart (точка = issue, цвет = риск) |
| **Flow Efficiency** | Доля «активного» времени над общим | Active time ÷ total cycle time | Donut + цель ≥40% |
| **Sprint Goal Completion** | Прогнозируемость sprint commitments | % committed scope completed | Trend line за 6–10 спринтов |
| **Sprint Predictability Index** | Стабильность плана | std.dev(velocity) ÷ mean(velocity) | KPI‑карточка + тренд |
| **Cumulative Flow Diagram (CFD)** | Узкие места в процессе | Jira встроенный + расширения | Stacked area chart с цветами по статусам |
| **Arrival vs Departure Rate** | Растёт ли бэклог быстрее, чем закрывается | Δ(arriving issues) vs Δ(closing) | Двойная линия, видна «крокодилья пасть» |

> **Применение Little's Law:** `Cycle Time = WIP / Throughput`. Это позволяет AI‑слою объяснять: *«Cycle time вырос на 28% — на 22% из‑за роста WIP, на 6% из‑за падения throughput»*. Такие декомпозиции ценны для CTO.

#### 2.3 Backlog & Capacity

| Метрика | Применение |
|---|---|
| **Backlog Health** | % issues с estimate, описанием, AC; «возраст» бэклога (медианный age). Тревожный сигнал, если >30% старше 90 дней. |
| **Backlog Growth Rate** | Δ open issues нед./нед. Сигнал, что бизнес заводит больше, чем команда успевает. |
| **Workload Distribution** | Доля Roadmap / Bugs / Tech Debt / Unplanned (Swarmia Investment Balance). Главный «McKinsey‑слой» для CFO: куда уходят деньги. |
| **Cross‑Team Dependencies** | Кол‑во issues с external links (`is blocked by`) между проектами. |
| **Blocked Work** | Issues в статусе `Blocked` или с label `blocked`; aging такого блока. |
| **SLA/SLO Compliance** | Для service‑desk проектов Jira: % tickets в SLA‑окне. |

#### 2.4 Качество и технический долг

| Метрика | Источник |
|---|---|
| **Defect Density** | Bugs ÷ delivered story points |
| **Escaped Defects** | Bugs с `Found in: Production` после релиза |
| **Reopen Rate** | % issues, переоткрытых после `Done` |
| **Tech Debt Ratio** | Issues с label `tech-debt` ÷ total |
| **Release Stability** | % релизов без hotfix в первые 48 часов |

#### 2.5 Code Review (если есть GitHub/GitLab интеграция)

| Метрика | Сигнал |
|---|---|
| **PR Cycle Time** (open→merge) | Узкое место «code review» |
| **PR Aging** (% PR старше 3 дней) | Stuck reviews |
| **Review Coverage** | % PR с ≥1 ревью |
| **PR Size** (median lines changed) | Связано с CFR — большие PR → больше багов |
| **First‑Response Time** | Скорость реакции ревьюверов |

#### 2.6 «McKinsey/SPACE» — производный слой

* **Investment Balance** (Roadmap/Bugs/Maintenance/Unplanned) — единственная метрика, которую CFO открывает первой.
* **Engineering Focus Time** — % времени без meeting/context‑switch (требует календарной интеграции, опционально).
* **Developer Experience score** (опросная, NPS‑like) — leading indicator.

> **Важно для С‑level:** не показывать **individual contributor metrics**. Это «harmful» по Gartner SEI Market Guide 2024 и приводит к gaming. Только агрегаты команды.

### 3. Соответствие метрик и executive‑вопросов

| Вопрос топ‑менеджера | Какие метрики отвечают |
|---|---|
| «Доставляем ли мы быстро?» | DF, LTC, Cycle Time, Throughput |
| «Можем ли мы прогнозировать?» | Sprint Predictability, Monte Carlo forecast, CFD |
| «Качество стабильно?» | CFR, MTTR, Escaped Defects, Reopen Rate |
| «Куда уходят деньги?» | Investment Balance, Workload Distribution |
| «Какие риски на горизонте 2–4 недели?» | Aging WIP, Blocked count, Dep. graph, Backlog Growth |
| «Здоровая ли команда?» | Focus Time, Workload variance, On‑call burden, DevEx survey |

---

## Часть III. Каталог визуализаций — ранжированный гайд

Каждая визуализация оценена по 4 критериям: **30‑sec readability** (R), **executive value** (E), **risk of misinterpretation** (M), **complexity to build** (C).

### A. ОБЯЗАТЕЛЬНЫЕ для executive‑экрана (R↑↑↑, E↑↑↑)

| Паттерн | Зачем | Когда использовать | Когда не использовать |
|---|---|---|---|
| **KPI‑карточка** (число + Δ + спарклайн + цветовой бейдж) | Мгновенное считывание статуса | 4–7 «hero metrics» наверху | Если нет тренда/контекста — пустое число вредно |
| **Светофор (RAG indicator)** | Бинарное решение «нужно ли вмешиваться» | Project health, SLA, deployment status | Не показывать без объяснения порогов — «жёлтый» без причины раздражает |
| **Спарклайн / Trend mini‑chart** | Тренд за 8–13 точек данных без потери места | Внутри KPI‑карточки | Если нужны точные значения — заменить на line chart |
| **Donut chart с одним фокус‑сегментом** | Распределение в 3–5 категорий (Investment Balance) | Roadmap vs Bugs vs Tech Debt | Не использовать для >5 категорий — перейти на stacked bar |
| **Horizontal Progress Bars** | Прогресс к цели или сравнение команд | Sprint completion %, OKR progress | Не сравнивать несопоставимые сущности |
| **Top‑3 list** (anomalies/risks) | AI‑генерируемый «что важно сегодня» | Daily executive feed | Без объяснения «почему» — бесполезно |

### B. ВЫСОКАЯ ЦЕННОСТЬ для tactical уровня (Head of Engineering)

| Паттерн | Применение | Замечания |
|---|---|---|
| **Cumulative Flow Diagram (CFD)** | Узкие места процесса | Считывается за 60+ сек, требует обучения. Включать в L2, не L1. |
| **Cycle Time Scatter Plot** + 50/85/95% перцентили | Вариативность доставки, прогноз | Лучшая визуализация для probabilistic forecasting (Daniel Vacanti, Troy Magennis). |
| **Burn‑up chart** (с trend forecast) | Прогноз достижения релизной цели | Лучше burndown — показывает scope creep явно. |
| **Monte Carlo forecast** (cone of uncertainty) | «Когда будет готово?» с 50%/85%/95% доверительными интервалами | Идеальная альтернатива «дате релиза». Использовать throughput за последние 8–12 спринтов. |
| **Heatmap** (команды × недели или активность × часы) | Workload distribution, on‑call burden | Не использовать для individual performance — только агрегаты. |
| **Aging WIP chart** | Зависшая работа | Точка = issue, цвет = риск/тип. |
| **Control Chart** (cycle time с ±2σ) | Стабильность процесса | Полезен для senior engineering managers, не для C‑level. |
| **Stacked Area Chart** (Investment Balance over time) | Тренд распределения капекса | Альтернатива donut при показе истории. |

### C. УСЛОВНО ПОЛЕЗНЫЕ — использовать осторожно

| Паттерн | Риски |
|---|---|
| **Sankey diagram** (потоки issue по статусам) | Красиво на демо, плохо на executive‑экране — слишком плотная информация. Только в drill‑down. |
| **Dependency Graph** (cross‑team) | Полезен, если связей <30; иначе — «тарелка спагетти». |
| **Radar / Spider chart** | Subjective scorecards (DORA bench). Психологически завышает «слабые» категории. Лучше — bar chart. |
| **Risk Matrix 2×2** (likelihood × impact) | Хорошо для портфеля рисков, но риски нужно регулярно ревьюить — иначе устаревают. |
| **Gantt / Roadmap timeline** | Полезен квартально, на еженедельном дэшборде — шум. |

### D. АНТИ‑ПАТТЕРНЫ (НЕ ИСПОЛЬЗОВАТЬ)

| Паттерн | Почему |
|---|---|
| **Pie chart >5 сегментов** | Stephen Few: визуально неразличимо. |
| **3D‑графики любого вида** | Искажают пропорции. |
| **Gauges/спидометры** | Занимают место, дают одно число. Заменить на KPI‑карточку. |
| **Tables с >7 колонками на executive‑экране** | Не считывается за 30 сек. |
| **Velocity team‑comparison bar chart** | Велосити не сравнима между командами — поощряет gaming. |
| **Individual developer leaderboards** | Разрушают доверие; противоречат SPACE и Gartner SEI guidance. |
| **Burn‑down only** | Без burn‑up не виден scope creep. |
| **Wall‑of‑numbers**, >12 KPI на одном экране | Cognitive overload. Stephen Few: 5–9 KPI = верхний предел. |

### E. Распределение по уровням аудитории

```
Executive (CEO/CTO/Board)         → A + Monte Carlo + Investment Balance
Head of Engineering / Director    → A + B (всё)
Engineering Manager / Tech Lead   → B + C
Команда                            → всё, plus diagnostic drill-downs
```

---

## Часть IV. Каталог open‑source и vendor‑экосистемы

### 1. Open‑source платформы и репозитории

| Проект | URL | Что это | Стек | Сильные / слабые стороны |
|---|---|---|---|---|
| **Apache DevLake** (incubating) | github.com/apache/incubator-devlake | Самая зрелая OSS Engineering Intelligence платформа. Преднастроенные Grafana‑дэшборды для DORA, throughput, code review, retro | Go + Python plugins, MySQL, Grafana | **+** широкая интеграция (Jira, GitHub, GitLab, Jenkins, Bitbucket, SonarQube, Copilot Metrics); **+** активное Apache‑комьюнити; **−** Grafana как UI ограничивает дизайн под executive. |
| **DORA Four Keys** (Google) | github.com/dora-team/fourkeys (mirror на GoogleCloudPlatform/fourkeys) | Канонический пайплайн DORA на GCP (BigQuery + Cloud Run + DataStudio) | Python, Terraform, BigQuery | **+** «эталонная» имплементация; **−** репозиторий не активно поддерживается, привязан к GCP. |
| **WatchOps** | github.com/italolelis/watchops | DORA‑платформа Helm‑чарт, легко на Kubernetes | Helm/K8s | **+** lightweight; **−** малое комьюнити. |
| **DeloitteDigitalUK / jira-agile-metrics** | github.com/DeloitteDigitalUK/jira-agile-metrics | CLI‑утилита: cycle time, CFD, control chart, Monte Carlo прогноз из Jira | Python | **+** богатый набор метрик; **+** генерирует HTML отчёты; **−** не SaaS, batch‑режим. |
| **ActionableAgile / jira-to-analytics** | github.com/ActionableAgile/jira-to-analytics | Экстрактор Jira → CSV для ActionableAgile (Daniel Vacanti) | Node.js | Эталонный коннектор для flow‑метрик; служит как референс. |
| **Praqma / atlassian-metrics** | github.com/Praqma/atlassian-metrics | Jira → Prometheus → Grafana | Groovy ScriptRunner + Prometheus | Старый, но архитектурно поучительный. |
| **q-rapids / qrapids-dashboard-jira-gadget** | github.com/q-rapids/qrapids-dashboard-jira-gadget | Quality assessment gadget внутри Jira | Atlassian SDK | Точечный — для embed‑опыта. |
| **lunivore / montecarluni** | github.com/lunivore/montecarluni | Monte Carlo прогноз из CSV‑экспорта Jira | Kotlin | Минимальный референс для Monte Carlo. |
| **Plane** | github.com/makeplane/plane | OSS Jira‑альтернатива (~36k★) | Django + Next.js | Не аналитика, но архитектурный референс продукта. |
| **Atlassian Python API** | github.com/atlassian-api/atlassian-python-api | Обёртка над Jira REST | Python | Базовая зависимость для своего пайплайна. |
| **Focused Objective Throughput Forecaster** | focusedobjective.com (Excel) | Эталонный Monte Carlo Troy Magennis | Excel | Алгоритмический референс — формулы перенести в свой движок. |

### 2. BI‑инструменты, применимые поверх Jira‑данных

| Инструмент | Применимость | Замечания |
|---|---|---|
| **Grafana** | DevLake, Four Keys по умолчанию | Хорошо для ops, слабее для executive UX |
| **Apache Superset** | Self‑hosted SQL‑дэшборды | Гибкий, но вид «корпоративный»; кастомизация под executive — много работы |
| **Metabase** | Быстрый старт, хорошая UX | Идеален для middle‑management, но «потолок» для C‑level дизайна |
| **Redash** | SQL‑first | Минимально для команд‑аналитиков |
| **Microsoft Power BI / Tableau** | Если уже в стеке корпорации | Дорогие, тяжело embed |

### 3. Коммерческие Engineering Intelligence платформы (для конкурентного анализа)

| Платформа | Размер целевой компании | Ключевая особенность | Слабость для нашего use‑case |
|---|---|---|---|
| **Jellyfish** | 100+ инженеров, enterprise | Investment allocation, R&D capitalization, отчёты для CFO | Дорого ($30–100k+/год); избыточно для 10–50 человек |
| **LinearB** | 30–500 | gitStream PR automation, DORA dashboards | Per‑seat pricing, weak Jira‑native deep flow |
| **Swarmia** | 30–300 | DORA + SPACE + Investment Balance, developer surveys | Limited customization (частая жалоба в G2) |
| **Allstacks** | 100+ | Predictive delivery, value stream mapping | Enterprise pricing |
| **Faros AI** | 100+ | Open metadata model, deep extensibility | Сложная настройка |
| **Athenian** | 50–500 | GitHub‑first, Pulse‑метрики | Слабый Jira |
| **Haystack** | 20–100 | Slack‑first reports | Ограниченная глубина |
| **Code Climate Velocity** | 50–500 | Старейший игрок, Velocity 2.0 | Воспринимается как legacy |
| **Pluralsight Flow** (бывш. GitPrime) | 100+ | Behavioral data | Репутационные риски (individual metrics) |
| **Sleuth** | 30–200 | DORA + change tracking | Узкая специализация |
| **DX (GetDX)** | 100+ | Developer Experience surveys + research‑backed | Дорого, опросный фокус |
| **GitHub Insights / Atlassian Compass** | любой | Native, бесплатно | Базовый функционал, плохой executive‑UI |

**Вывод:** ниша «Jira‑first SEI для команд 10–50 с AI‑первого взгляда» — практически свободна. Конкуренты или enterprise‑тяжёлые (Jellyfish), или GitHub‑first (Athenian, CodePulse). Это конкретный позиционирующий козырь.

---

## Часть V. AI‑генерируемые executive summaries

### 1. Типология AI‑артефактов

| Артефакт | Триггер | Длина | Аудитория |
|---|---|---|---|
| **Daily Pulse** | Каждое утро 09:00 | 3–5 предложений + top‑3 риска | Head of Engineering |
| **Weekly Executive Brief** | Понедельник | 1 «headline» + 3 секции (Delivery / Quality / Risks) ≈ 200–300 слов | C‑level |
| **Sprint Closing Narrative** | По окончании sprint | 1 страница + AI‑recommendations | Engineering Manager + product |
| **Monthly Operational Review** | 1‑е число месяца | 2 страницы + графики | CTO |
| **Quarterly Engineering Performance Review** | 1‑е число квартала | 5–7 страниц + бенчмарки | Board, CFO |
| **Anomaly Alert** | Срабатывание правила | 2–3 предложения с глубокой ссылкой | Eng manager + on‑call |
| **Risk Report** | Еженедельно | Top‑5 рисков с probability×impact, drilldown | C‑level + delivery |
| **Recommendation Card** | Постоянно, в контексте метрики | 1 действие, 1 KPI, ожидаемый эффект | Eng manager |

### 2. Архитектура AI‑слоя (защита от галлюцинаций)

Свободно сгенерированные LLM‑тексты на основе сырых метрик показывают **до 28–40% уровень ошибок** (Chelli 2024 и др.). Для executive‑контекста это неприемлемо. Минимально допустимая архитектура:

```
[Jira REST] → [ETL] → [Semantic Metric Layer (DuckDB/ClickHouse)]
                                ↓
                  [Deterministic Computation Engine]
                  (вычисляет все метрики, аномалии, тренды)
                                ↓
                  [Structured Findings JSON]
                  { metric, value, delta, status, evidence: [issueKey...] }
                                ↓
                  [LLM Narrator with strict prompt]
                  (получает ТОЛЬКО findings, не raw данные)
                                ↓
                  [Self-check / Faithfulness validator]
                  (проверяет: каждое утверждение → есть ли в findings)
                                ↓
                  [Executive Narrative + clickable evidence]
```

**Ключевые принципы:**

1. **LLM не считает метрики.** Все числа считаются детерминистически. LLM получает уже вычисленные `findings` с источниками.
2. **Каждое числовое утверждение в нарративе обязано иметь evidence link** на конкретный Jira issue / sprint / период.
3. **Schema‑constrained output** (JSON Schema, function calling): LLM возвращает структурированный объект, не свободный текст. UI рендерит из объекта.
4. **Faithfulness validator**: после генерации nlp‑ или LLM‑judge проверяет, что каждое цифровое утверждение присутствует в `findings`. Несоответствие → блокировка.
5. **Calibrated uncertainty**: добавлять «вероятно», «по 4 спринтам, что мало для статистики» — это калибровка.
6. **Запрет на сравнение личностей** на уровне system prompt.

### 3. Эталонная схема prompt для weekly executive brief

```
SYSTEM:
Ты — старший engineering analyst. Пишешь brief для CTO.
Правила:
- Используй ТОЛЬКО данные из блока FINDINGS.
- Каждое числовое утверждение должно ссылаться на findings[i].id.
- Не выдумывай метрики, которых нет в FINDINGS.
- Если данных мало (<6 спринтов) — явно указывай низкую уверенность.
- Никаких сравнений отдельных людей.
- Стиль: McKinsey one-pager. Без воды.
- Структура: 1 headline (≤15 слов) → Delivery → Quality → Risks → 1 Recommendation.

FINDINGS (JSON):
[
  {"id": "F1", "metric": "cycle_time_p85", "value": 11.2, "unit": "days",
   "delta_pct": +28, "period": "last_4_weeks", "trend": "rising",
   "evidence": ["JIRA-123","JIRA-145","JIRA-198"], "anomaly": true,
   "decomposition": {"wip_growth": +22, "throughput_drop": -6}},
  {"id": "F2", "metric": "deployment_frequency", "value": 2.1, "unit":"per_week",
   "delta_pct": -10, "dora_band": "high", "trend":"stable"},
  ...
]

OUTPUT JSON SCHEMA:
{
 "headline": str (≤15 words),
 "delivery": {"text": str, "sources": [F-ids]},
 "quality":  {"text": str, "sources": [F-ids]},
 "risks":    [{"title": str, "severity": "high|med|low", "sources": [F-ids]}],
 "recommendation": {"action": str, "expected_impact": str, "sources":[F-ids]}
}
```

### 4. Пример good vs. poor

**Плохой (типичная LLM‑галлюцинация):**
> *«Производительность команды Alpha улучшилась благодаря усилиям разработчика Ивана. Вероятно, на следующей неделе мы увидим рост скорости.»*
*Проблемы*: упоминание персоналии, причинно‑следственная фантазия, «вероятно» без модели.

**Хороший:**
> *«Cycle time (P85) команды Alpha вырос с 8.7 → 11.2 дней за 4 недели (+28%). 22 п.п. этого роста объясняются увеличением WIP с 14 до 19 issues; 6 п.п. — падением throughput. 5 issues находятся «in progress» >10 дней (JIRA‑123, JIRA‑145, JIRA‑198, JIRA‑201, JIRA‑212). Рекомендация: ввести WIP‑limit = 12, ожидаемое сокращение cycle time на 15–20% за 2 спринта.»*

### 5. Anti‑patterns AI‑суммаризатора

* Никогда не сравнивать конкретных людей.
* Не транслировать «разработчик X — top performer» — это leaderboard‑ловушка.
* Избегать пустых клише («команда работает усердно», «процесс улучшается»).
* Не заменять числа словами без указания значения.
* Не «округлять оптимистично» (LLM склонны к flattering).

---

## Часть VI. Архитектура дэшборда и UX

### 1. Информационная иерархия (3 уровня)

```
[L1] OVERVIEW SCREEN — открывается по умолчанию (30-сек правило)
  ├ AI Headline (1 предложение)
  ├ 4-6 KPI cards (DF, LTC, CFR, MTTR, Predictability, Investment Balance)
  ├ Top-3 Risks (AI-ranked)
  └ Trend strip (cycle time + throughput, 8 weeks)

[L2] LENS SCREENS — клик по KPI карточке
  ├ Delivery Health      → DF, LTC, CFD, burn-up
  ├ Predictability       → Monte Carlo, sprint goal trend, scatter
  ├ Quality              → CFR, MTTR, defect density, escaped bugs
  ├ Risks & Bottlenecks  → Aging WIP, blocked, dependencies
  └ Investment / Capacity → Workload distribution, focus time

[L3] DRILL-DOWN — клик по элементу (issue / sprint / repo)
  ├ Список Jira issues с фильтрами
  ├ Timeline события issue
  └ Выгрузка для команды
```

### 2. Принципы (Stephen Few + Linear/Height/Notion референсы)

* **10/80/10 принцип:** 10% метрик — стратегические (executive), 80% — operational, 10% — diagnostic.
* **Critical few:** на L1 — максимум 5–9 индикаторов. Иначе — overload.
* **Single screen** для L1 (без скролла на десктопе ≥1440px).
* **Единая цветовая семантика:** cyan = норма, жёлтый = внимание, красный = критично, серый = нет данных. **Никогда** не использовать зелёный/красный без backup‑знака (доступность).
* **Progressive disclosure:** advanced‑метрики и фильтры — за expandable‑секциями, hover‑popover, modal‑drill‑down. Никаких popup‑lightbox, только in‑page expand.
* **Контекст у каждого числа:** значение **+** Δ vs предыдущий период **+** статус‑бейдж **+** AI‑объяснение «почему» (по hover/click).
* **Тренд > значение.** Спарклайн рядом с каждым KPI.
* **Зеро‑state aware:** «<6 спринтов данных» прямо на UI, иначе ложная уверенность.
* **Mobile**: на мобильном показываем ТОЛЬКО L1 + AI‑headline. Карточки в один столбец.
* **Dark / Light:** тёмный режим — дефолт для executive (рекомендуемая палитра в начале документа); светлый — экспортные PDF.
* **Печать:** каждый L2 экран должен иметь «Export to PDF» с правильным форматом (A4 landscape).

### 3. Альтернативная навигация (sidebar + tabs)

В соответствии с референсной палитрой: **левый sidebar** с SVG‑иконками для разделов (Overview / Delivery / Predictability / Quality / Risks / Investment / Reports), **верхний breadcrumb** для drill‑down, **right‑rail** для AI‑комментария к выбранной метрике.

### 4. Уведомления и приоритизация алертов

| Категория | Канал | Trigger |
|---|---|---|
| **Critical** | Slack DM + email + dashboard banner | CFR > 30%, MTTR > 4h, sprint at risk >50% |
| **Warning** | Slack channel | Aging WIP issue >10 дней, throughput −20% |
| **Info** | Weekly digest | Тренды, анализ |
| **AI insight** | In‑dashboard «What's new» | Аномалии, decomposition |

Никаких email‑бомбардировок. По умолчанию — один Monday brief + critical alerts.

---

## Часть VII. Шаблоны отчётов

### 1. Daily Pulse (для Head of Engineering)

* **AI Headline** (1 строка)
* 4 KPI‑карточки: вчерашние deployments, новые блокеры, открытые critical bugs, sprint progress
* **Top‑3 Risks** (AI‑ranked) — с прямыми ссылками на issues
* **What changed since yesterday** (нарратив, ≤80 слов)

### 2. Weekly Executive Brief (для CTO/CEO)

* **AI Headline** (например: *«Доставка стабильна, но cycle time +28% из‑за роста WIP — рекомендуем WIP‑limit»*)
* **Delivery section:** DF, LTC, throughput trend (3 KPI + 1 спарклайн)
* **Quality section:** CFR, escaped defects, MTTR (3 KPI + бейджи)
* **Risk section:** Top‑5 рисков с severity и owner
* **Investment Balance:** donut % Roadmap/Bugs/Tech Debt/Unplanned + Δ
* **One Recommendation** (AI)

### 3. Sprint Closing Narrative

* Goal completion %
* Committed vs Done (story points / issues)
* Карбонит‑тренд: predictability index за 6 sprints
* Pulled‑in / dropped issues
* AI‑секция «что стоит обсудить на ретро»

### 4. Monthly Operational Review (для CTO)

* DORA‑бейджи (по командам)
* Cycle time scatter за месяц
* CFD за 4 недели
* Investment Balance month‑over‑month
* Tech Debt accumulation chart
* Recommendation backlog (что AI предложил, что выполнили)

### 5. Quarterly Engineering Performance Review (для Board)

* Бенчмарки vs DORA Elite/High/Medium/Low
* Delivery throughput (story points + issues, 13 weeks)
* Predictability index trend (4 quarters)
* Investment portfolio (Roadmap/Bugs/Tech Debt/Compliance)
* Top‑10 delivered initiatives с ETA vs actual
* Risk register
* AI‑narrative о квартале (3–5 страниц)
* Forward‑looking forecast (Monte Carlo)

### 6. Project Health Report (для PMO/Delivery)

* RAG status per project
* Burn‑up + forecast
* Top blockers
* Cross‑team dependency graph

### 7. Delivery Risk Report

* Risk matrix 2×2
* Aging WIP top‑10
* Dependency violations
* SLA breaches

### 8. Portfolio Dashboard (1–5 команд)

* Heatmap: команды × 6 ключевых метрик (cycle time, DF, CFR, predictability, throughput, investment balance)
* Per‑team mini‑sparkline
* Cross‑team dep. graph
* Aggregate Investment Balance

---

## Часть VIII. Сравнительный анализ — матрица решений

### Сравнение по ключевым осям (для нашего use‑case 10–50 человек, executive аудитория)

| Платформа | Vis. quality | Exec. readability | AI capabilities | Extensibility | OSS | Кастомизация | Сложность внедрения | Цена/seat |
|---|---|---|---|---|---|---|---|---|
| **Jellyfish** | ★★★★ | ★★★★★ | ★★★ | ★★★ | — | ★★★ | High | $$$$ |
| **LinearB** | ★★★★ | ★★★★ | ★★★ | ★★★ | — | ★★ | Medium | $$$ |
| **Swarmia** | ★★★★★ | ★★★★ | ★★★ | ★★ | — | ★ | Low | $$$ |
| **Allstacks** | ★★★ | ★★★★ | ★★★★ | ★★★ | — | ★★★ | High | $$$$ |
| **Faros AI** | ★★★ | ★★★ | ★★★★ | ★★★★★ | partial | ★★★★ | High | $$$$ |
| **Athenian** | ★★★ | ★★★ | ★★ | ★★★ | partial | ★★★ | Medium | $$$ |
| **Haystack** | ★★ | ★★★ | ★★ | ★★ | — | ★★ | Low | $$ |
| **Apache DevLake** | ★★ (Grafana) | ★★ | — | ★★★★★ | ✓ | ★★★★★ | High self‑host | Free |
| **DORA Four Keys** | ★★ | ★★★ | — | ★★ | ✓ | ★★★ | Medium (GCP) | Free |
| **Atlassian Compass** | ★★★ | ★★★ | ★★ | ★★★ | — | ★★★ | Low | $$ |
| **GitHub Insights** | ★★ | ★★ | ★★ | ★ | — | ★ | None | Included |

**Свободная ниша:** Высокая executive readability **+** AI‑first (★★★★★) **+** простое внедрение **+** Jira‑first **+** для 10–50 человек. Никто не закрывает все пять одновременно.

---

## Часть IX. Технологические рекомендации

### 1. Frontend / Visualization

| Уровень | Рекомендация | Почему |
|---|---|---|
| **База** | React 18 + TypeScript | Стандарт, экосистема компонентов |
| **UI kit** | Radix UI / shadcn‑ui (или Mantine) | Headless, легко тематизировать под dark navy |
| **Charts (primary)** | **Apache ECharts 6** через `echarts-for-react` | Лучший баланс: 50+ типов графиков (включая CFD, Sankey, heatmap, scatter), отличная производительность (10M точек, sub‑second render), декларативный API, активная поддержка Apache Foundation; OpenObserve и многие SaaS перешли с Plotly на ECharts именно из‑за производительности и кастомизации тем |
| **Charts (simple cards)** | **Recharts** | Для простых KPI‑спарклайнов и progress bars — declarative, React‑native, минимальный bundle |
| **Charts (custom)** | **D3.js** (только при необходимости) | Только для уникальных визуализаций, которых нет в ECharts (например, custom dependency graph) |
| **НЕ выбирать** | Plotly как primary | Тяжёлый bundle (>1 MB), визуальный стиль «academic», много CSS‑оверрайдов |
| **Layout** | CSS Grid + Tailwind | Быстрая адаптация под breakpoints |
| **State** | Zustand или Redux Toolkit | Для cross‑widget filter state |
| **Tables** | TanStack Table | Если нужны drill‑down таблицы |

### 2. Backend / Data

| Слой | Рекомендация | Зачем |
|---|---|---|
| **API** | FastAPI (Python) или NestJS | Близко к LLM/data‑экосистеме |
| **Jira ETL** | Jira REST API + webhook + changelog API | Webhook для near‑real‑time, REST для backfill |
| **Хранилище сырых событий** | PostgreSQL | Транзакционная база для issues, changelog |
| **Аналитический слой** | **DuckDB** (для команд до 50) или **ClickHouse** (если ≥100) | OLAP, секунды на агрегаты по миллионам issue‑changelog событий; DuckDB = embedded, ноль ops |
| **Семантический слой / metrics layer** | dbt models или Cube.js | Единственный источник правды для определений метрик |
| **Очередь** | Redis Streams или RabbitMQ | Для AI‑воркера и webhook backpressure |
| **Кеш** | Redis | Для дешбордов |

### 3. AI‑слой

| Компонент | Рекомендация |
|---|---|
| **LLM provider** | OpenAI GPT‑4‑class (или Anthropic Claude 3.5) для production; локальные Llama‑3 70B/Qwen — для on‑prem клиентов |
| **Function calling / structured output** | OpenAI function calling или Pydantic AI / Instructor library — обязательно JSON Schema |
| **RAG** | Не нужен полноценный RAG; нужен «findings retrieval» — вынуть детерминистически вычисленные метрики, дать LLM как context |
| **Validator** | LLM‑as‑judge на отдельной модели + regex проверка, что числа в narrative соответствуют findings |
| **Observability** | Langfuse / LangSmith / Helicone — трейсинг каждого вызова |
| **Hallucination scoring** | Vectara HHEM или собственный faithfulness metric с эталонной разметкой |

### 4. Infrastructure

| Слой | Рекомендация |
|---|---|
| **Деплой** | Docker Compose (для small/self‑hosted) → Kubernetes (для multi‑tenant SaaS) |
| **Auth** | Clerk / Auth0 / собственный SSO |
| **Multi‑tenancy** | Schema‑per‑tenant в Postgres, отдельные DuckDB‑файлы или namespace |
| **Безопасность** | OAuth Atlassian, encryption at rest, RBAC, audit log, минимальный scope `read:jira-work` |

### 5. Стек принятия решений (если бы я строил MVP)

```
Frontend:   React + TS + Apache ECharts + shadcn-ui + Tailwind
Backend:    FastAPI (Python) + Celery
Data:       PostgreSQL (raw) → dbt → DuckDB (analytical)
AI:         OpenAI GPT-4o + Instructor + Langfuse
Auth:       Atlassian OAuth + Clerk
Infra:      Docker → Fly.io (MVP) → AWS ECS (scale)
```

Это даёт time‑to‑market 8–12 недель для команды из 3–4 инженеров.

---

## Часть X. Финальные рекомендации (Deliverables)

### A. Executive Summary (повтор тезисов)

Сервис должен сделать ставку на **AI‑first executive layer** поверх Jira, который существующие SEI‑платформы (Jellyfish, LinearB, Swarmia) делают слабо. Ключевая дифференциация — **30‑секундная читаемость + grounded AI‑narratives + low setup cost** для команд 10–50 человек.

### B. Топ‑10 визуализационных паттернов в порядке убывания executive‑ROI

1. **AI Headline + KPI карточки c трендом и бейджем DORA‑band** — сердце дэшборда.
2. **Cycle Time Scatter с P50/P85/P95 перцентилями** — говорит о предсказуемости в 1 взгляд.
3. **Investment Balance donut + stacked area over time** — лучший CFO‑вопрос «куда уходят деньги».
4. **Burn‑up с Monte Carlo прогнозом** — лучшая замена burndown для executive разговоров о датах.
5. **Cumulative Flow Diagram (упрощённый)** — для tactical уровня, мощный диагностический инструмент.
6. **Aging WIP chart** — сразу показывает «где зависает».
7. **Top‑3/Top‑5 AI Risks list** — действенно и человеко‑читаемо.
8. **Heatmap «команды × метрики»** для портфеля 2–5 команд.
9. **Trend strip** (cycle time + throughput, 8–13 weeks) — система VS вариация.
10. **Light/Dark RAG matrix project health** — для Delivery Director.

### C. Рекомендованная структура дэшборда

```
SIDEBAR (icons)               OVERVIEW (default)
─────────────                 ─────────────────────────────────────
[ Overview ]                   ┌─ AI Headline ──────────────────────┐
[ Delivery ]                   │ "Cycle time +28% — WIP rising. "   │
[ Predict. ]                   │  Recommend WIP-limit at 12."        │
[ Quality  ]                   └────────────────────────────────────┘
[ Risks    ]                   ┌──────────┬──────────┬──────────┬──────────┐
[ Invest.  ]                   │ DF       │ LTC      │ CFR      │ Predict. │
[ Reports  ]                   │ 2.1/wk ↗ │ 18h ↗   │ 7%  ↘   │ 84% ↗   │
[ Settings ]                   │ HIGH     │ HIGH     │ ELITE    │ GOOD     │
                                └──────────┴──────────┴──────────┴──────────┘
                                ┌── Top-3 Risks ────┐ ┌── Investment ──┐
                                │ ★ JIRA-123 …      │ │      donut      │
                                │ ★ Sprint-42 …     │ │  Roadmap 62%    │
                                │ ★ Dep. blocker    │ │  Bugs 18% …     │
                                └───────────────────┘ └─────────────────┘
                                ┌── 8-week trend strip ──────────────────┐
                                │  cycle time + throughput sparklines    │
                                └────────────────────────────────────────┘
```

### D. KPI‑система (4 уровня)

**L1 Executive (5–7 метрик):** Deployment Frequency · Lead Time for Changes · Change Failure Rate · Sprint Predictability · Investment Balance · Top Risk count · AI Headline.

**L2 Operational (8–12 метрик):** Cycle Time P50/P85 · Throughput · WIP · Aging WIP · CFD · Burn‑up · Backlog Health · PR Cycle Time · Review Coverage · MTTR · Escaped Defects · Reopen Rate.

**L3 Engineering (drill‑down):** PR aging, blocked time, status time decomposition, individual issue trace.

**L4 Risk:** Aging issues >10 дней · Cross‑team dep. count · SLA at risk · Backlog growth rate · DevEx survey.

### E. AI‑Summary рекомендации (свод)

* JSON‑schema constrained output, не свободная генерация.
* LLM не считает числа — только перефразирует findings.
* Каждое число → evidence link на Jira.
* Faithfulness validator на каждый output.
* Никаких индивидуальных сравнений.
* Калиброванная неуверенность («<6 спринтов»).
* Длина: brief = 200–300 слов; sprint = 1 страница; quarterly = 3–5 страниц.
* Структура: Headline → 3 секции → 1 Recommendation.
* Inline‑комментарии к графикам (hover‑popover «AI explains this trend»).
* Daily / weekly / sprint‑close / monthly / quarterly cadence.

### F. Технологические рекомендации (свод)

| Слой | Выбор |
|---|---|
| Frontend | React + TS + **Apache ECharts** + shadcn‑ui + Tailwind |
| Charts (cards) | Recharts |
| Backend | FastAPI / NestJS |
| Аналитика | DuckDB (или ClickHouse при scale) + dbt |
| AI | GPT‑4o / Claude 3.5 + Instructor + Langfuse |
| Pipeline | Webhooks + REST + Celery/Redis |
| Стиль | Dark navy (`#0d1c33`) + cyan/yellow accents + Segoe UI |

### G. Open‑source каталог (для inspirational research и возможной интеграции)

* **Apache DevLake** — самая зрелая OSS‑альтернатива; референс архитектуры.
* **DORA Four Keys** — каноническая имплементация DORA pipeline (Google).
* **DeloitteDigitalUK/jira-agile-metrics** — отличная база для cycle time, CFD, Monte Carlo.
* **ActionableAgile/jira-to-analytics** — экстрактор Jira с правильной семантикой.
* **lunivore/montecarluni** — Monte Carlo референс.
* **Focused Objective Throughput Forecaster (Excel)** — алгоритмический эталон Monte Carlo (Troy Magennis).
* **Praqma/atlassian-metrics** — Jira → Prometheus → Grafana, исторический референс.
* **q-rapids/qrapids-dashboard-jira-gadget** — embed в Jira UI.
* **Plane** — UX‑референс «Linear‑style» project management.

### H. Anti‑patterns (категорически избегать)

| Анти‑паттерн | Почему вредит | Что вместо |
|---|---|---|
| Individual developer leaderboards | Разрушает доверие, поощряет gaming | Только team‑aggregates |
| Velocity comparison между командами | Story points не сопоставимы | Throughput в issues + контекст |
| 20+ метрик на executive экране | Cognitive overload | 5–9 hero KPI |
| 3D pie charts | Stephen Few warning | Donut ≤5 сегментов или bar |
| Зелёный/красный без shape/icon | Доступность | RAG + иконка |
| Свободная LLM‑генерация на raw данных | 28–40% галлюцинации | Findings JSON + faithful narrative |
| Burndown без burn‑up | Скрывает scope creep | Always burn‑up |
| Деплой как goal без качества | Goodhart's law | Парные метрики (DF + CFR) |
| Mid‑sprint pivot на еженедельной метрике | Шум, не сигнал | 6‑sprint moving averages |
| Email‑бомбардировка алертами | Alert fatigue | Tiered notifications + digest |
| Дэшборд без AI‑объяснения тренда | «Голые» числа | Каждый KPI → AI‑hover |
| Сравнение с другими компаниями без контекста | Misleading | DORA bands как рамка, не stacked rank |
| Недельный sample <6 спринтов как «тренд» | Statistical noise | UI явно указывает «низкая уверенность» |
| Использование Jira‑velocity как primary KPI для CEO | Гейминг + плохо интерпретируется | Throughput + Lead Time + Predictability |
| Drill‑down через popup‑modal | Прерывает контекст | In‑page expand + breadcrumb |
| Радар‑чарт для DORA‑скоринга | Искажает восприятие слабых категорий | Group bar chart с DORA‑бейджами |

---

## Заключение

Сервис, ориентированный на executive‑аудиторию для команд 10–50 человек на Jira, выигрывает на **трёх осях одновременно**: (1) **дисциплина 30‑секундной читаемости** — жёсткая иерархия 5–9 KPI, AI‑headline, единая семантика цвета; (2) **AI‑first nарратив с гарантированной заземлённостью** — детерминистические findings + JSON‑schema LLM + faithfulness validator; (3) **Jira‑native deep flow аналитика**, которую LinearB/Athenian/CodePulse делают слабо. Открывшаяся ниша — между «лёгкими» инструментами (GitHub Insights, Compass) и «тяжёлыми» enterprise (Jellyfish/Allstacks). Дизайн‑референс — тёмно‑синий dashboard со cyan‑акцентами, donut + horizontal bars + 2×2 stat boxes + flow diagram + top‑3 list — формирует визуальную идентичность, которая воспринимается C‑level как «премиальная аналитика», а не «yet another Grafana».

Главный совет команде продукта: **относитесь к executive‑дэшборду не как к UI поверх метрик, а как к продукту коммуникации между инженерной системой и бизнесом**. Метрики — это фундамент; визуализация — это синтаксис; AI‑narrative — это смысл. Только все три слоя вместе превращают данные Jira в инструмент стратегических решений.