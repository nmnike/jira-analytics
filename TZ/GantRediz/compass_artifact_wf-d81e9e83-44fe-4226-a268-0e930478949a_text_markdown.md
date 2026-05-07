# Open-source инструменты планирования ресурсов для маленькой команды

**Для команды до 10 человек оптимальный open-source стек выглядит так: Timefold Solver или PyJobShop для алгоритмической оптимизации, GanttProject (десктоп) либо OpenProject/Plane (web) для визуализации с зависимостями, и crewAI или Plane AI агенты для авто-распределения с подсказками.** Это решение покрывает все три заявленных аспекта без лицензионных ловушек: Timefold и PyJobShop под Apache-2.0/MIT, тогда как наиболее раскрученные web-планировщики (Plane, OpenProject, Leantime, Vikunja, Huly) сидят на копилефт-лицензиях AGPL/GPL/EPL — это нормально для self-hosting, но критично, если вы планируете встраивать их в проприетарный SaaS. Из 30+ исследованных репозиториев лишь горстка содержит реальную алгоритмическую составляющую (RCPSP-солверы, constraint programming, weighted routing); остальные — «ещё один task-tracker» с ручным назначением. Ниже — детальный разбор по трём категориям с пометками о том, какие репозитории объединяют несколько аспектов.

## Категория 1. Gantt-планировщики и self-hosted веб-приложения

### Self-hosted web-приложения с Gantt

**OpenProject** (`opf/openproject`, ~15k★, GPL-3.0) — самый зрелый OSS-планировщик, Ruby on Rails + Angular, релизы ежемесячные, последний v17.3.1 в апреле 2026. Поддерживает иерархию work packages, FS-зависимости, milestones, baselines, тайм-трекинг, BCF/IFC. **Критического пути и SS/FF/SF-зависимостей нет** — это его главное ограничение. Подходит для self-hosting через Docker/Helm; не embeddable.

**Plane** (`makeplane/plane`, ~46k★, AGPL-3.0) — самый популярный OSS-PM на GitHub, Next.js + Django. Документация заявляет визуализацию **критического пути** в Timeline, поддерживает Cycles (спринты), Modules (эпики), AI-агентов и MCP-сервер. AGPL-3.0 — серьёзный флаг для коммерческого встраивания.

**Leantime** (`Leantime/leantime`, ~9.7k★, AGPL-3.0) — PHP-планировщик, ориентированный на нейроотличных пользователей и не-PM-ов. Gantt-Timeline, milestones, неограниченная вложенность подзадач, идейные доски, lean canvas. Релизы регулярные (v3.7.3 в марте 2026). Алгоритмики не имеет.

**Vikunja** (`go-vikunja/vikunja`, ~4.1k★, AGPL-3.0) — Go + Vue, отличный кандидат для команды до 10 человек. В версии 2.2 добавили иерархию подзадач и стрелки зависимостей в Gantt; v2.3 (2026) принесла плагин-систему и OAuth. Есть CalDAV, импорт из Todoist/Trello/WeKan. Критического пути нет.

**Huly** (`hcengineering/platform`, ~25.4k★, EPL-2.0) — амбициозный TS-комбайн, заменяющий Linear/Jira/Slack/Notion. Содержит **Team Planner** (визуальная капасити-картинка), AI-помощник Hulia, Cards & Processes (триггеры, аппрувы, под-процессы), двунаправленную синхронизацию с GitHub. Релизы почти ежедневные. EPL-2.0 — слабый копилефт, требует юридической верификации.

### Gantt-библиотеки для встраивания

**Frappe Gantt** (`frappe/gantt`, ~5.9k★, **MIT** ✅) — лёгкая SVG-библиотека без зависимостей, наиболее популярный OSS-Gantt-компонент. v1.0.3 в феврале 2025 с полным переписыванием, PR-активность продолжается до марта 2026. Поддерживает FS-зависимости, drag-to-reschedule, режимы Day/Week/Month/Year. **Без критического пути, без SS/FF/SF, без resource view** — простота как фича.

**SVAR Gantt** (`svar-widgets/gantt`, `svar-widgets/react-gantt`, **MIT** ✅) — современный высокопроизводительный Svelte-компонент с React/Vue-обёртками, активно позиционируется как замена DHTMLX. Поддерживает **все четыре типа зависимостей FS/SS/FF/SF**, виртуализацию для 10k+ задач, MCP-сервер. v2.6.1 в апреле 2026. Важно: критический путь, baselines, авто-планирование и MS Project-импорт доступны только в коммерческой PRO-версии. **Команда mkozhukh — экс-XB Software/DHTMLX, русскоязычные разработчики из Беларуси.**

**gantt-task-react** (`MaTeMaTuK/gantt-task-react`, ~1k★, MIT) — React + TypeScript, milestone, FS-зависимости, множество view-режимов. **Borderline-статус**: основные коммиты автора остановились в 2024, но community-PRs приходят в 2025. Автор по нику и истории — русскоязычный. Если ищете живые форки — смотрите `gantt-task-react-pro`.

**jsgantt-improved** (`jsGanttImproved/jsgantt-improved`, ~515★, BSD/MIT) — единственная JS-библиотека с **полной поддержкой FS, SS, FF, SF** через суффиксы предшественников. Плюс ng-gantt и react-jsgantt (обновлены в декабре 2025/январе 2026). Ядро последний раз пушилось в августе 2024 — на грани двухлетней отсечки.

⚠️ **gantt-schedule-timeline-calendar** (`neuronetio/gantt-schedule-timeline-calendar`, ~3.4k★) **исключён**: лицензия NEURONET Free License — не OSI-approved, требует регистрации ключа для коммерческого применения. Автор Rafał Pośpiech, польский разработчик.

### Десктопные Gantt-инструменты с алгоритмикой

**GanttProject** (`bardsoftware/ganttproject`, ~1k★, GPL-3.0) — единственный полноценно живой OSS-десктоп с **настоящим scheduling-движком**: критический путь, FS/SS/FF/SF-зависимости, ресурсная нагрузка, MS Project XML/MPP импорт-экспорт, праздничные календари 30+ стран. Java + Kotlin/JavaFX. Последний коммит — октябрь 2025. **Сопровождает Дмитрий Барашев (BarD Software), русскоязычный разработчик.** Это самый сильный кандидат, объединяющий алгоритмическую оптимизацию и визуализацию в одном пакете.

⚠️ **ProjectLibre** **исключён**: исходники на SourceForge, последний OSS-релиз 1.9.3 (2020), GitHub-зеркала заброшены, разработка ушла в закрытый SaaS.

## Категория 2. Алгоритмическая оптимизация: RCPSP, CP-SAT, MIP

### Тяжеловесные solver-фреймворки

**Google OR-Tools** (`google/or-tools`, ~13.1k★, **Apache-2.0** ✅) — фундамент для всего. Содержит state-of-the-art CP-SAT, GLOP/PDLP, MIP-обёртки, маршрутизацию, упаковку. **Критически важно: в `examples/python/rcpsp_sat.py` лежит готовый RCPSP-солвер, читающий PSPLIB напрямую.** Конструкции `add_cumulative` и `new_interval_var` позволяют смоделировать командное распределение задач буквально в десяток строк. Релиз v9.15 в январе 2026.

**Timefold Solver** (`TimefoldAI/timefold-solver`, **Apache-2.0** ✅, Community Edition) — прямой наследник OptaPlanner (форк 2023 года той же командой), Java 21+/Kotlin, интеграция с Quarkus и Spring Boot. Реализует local search, tabu search, simulated annealing, late acceptance. Решает Vehicle Routing, **Employee Rostering, Task Assignment, Project Job Scheduling, Job Shop**. Constraint Streams DSL с HardSoft-скорингом. **Это лучший выбор для задачи «распределить людей по задачам с учётом скиллов, доступности и справедливости».**

**Timefold Quickstarts** (`TimefoldAI/timefold-quickstarts`, ~500★, **Apache-2.0** ✅) — **готовый шаблон для команды**. Подкаталоги `project-job-scheduling` и `quarkus-task-assigning` дают рабочий solver с REST-API и UI после `mvn quarkus:dev`. Это ровно то, что просит задача: «готовые шаблоны/примеры использования Timefold для распределения задач команды».

**OptaPlanner** (`apache/incubator-kie-optaplanner`, ~3.4k★, Apache-2.0) — классическая референсная реализация, форвард-разработка ушла в Timefold с апреля 2023. Используйте Timefold для новых проектов; OptaPlanner — для исторического контекста.

### Python-библиотеки constraint programming и моделирования

**PyJobShop** (`PyJobShop/PyJobShop`, ~107★, **MIT** ✅) — самая интересная новинка 2025 года. Python поверх OR-Tools CP-SAT и IBM CP Optimizer, единый API для **single/parallel machines, hybrid flow shop, open shop, job shop, flexible job shop, distributed shop и RCPSP** с возобновляемыми и потребляемыми ресурсами. Поддержка release dates, deadlines, multiple modes, sequence-dependent setups, no-wait, blocking, breaks. v0.0.8 в январе 2026, бэкается arXiv-публикацией. Идеальный выбор, если нужен один Python-API для всего спектра задач.

**CPMpy** (`CPMpy/cpmpy`, ~346★, **Apache-2.0** ✅) — высокоуровневая моделирующая прослойка с numpy-переменными, транслирует в OR-Tools, CP Optimizer, Choco, MiniZinc, Z3, Gurobi, CPLEX. В `examples/` лежит **flexible jobshop с готовой Plotly-визуализацией Gantt-диаграммы**. Медали XCSP3 2024-2025. Лучший баланс гибкости и читаемости.

**cpsat-primer** (`d-krupke/cpsat-primer`, ~725★, CC BY 4.0) — образцовый туториал-книга от TU Braunschweig с практическими CP-SAT-рецептами по scheduling. Используйте как стартовый шаблон для собственных моделей.

**airbus/discrete-optimization** (~52★, **MIT** ✅) — Python-обёртка над OR-Tools/MiniZinc/Gurobi с поддержкой RCPSP в вариантах multi-mode/preemptive/multi-skill, плюс робастная оптимизация со сценариями. Используется Airbus AI Research; парный репозиторий `airbus/scikit-decide` (тоже MIT) даёт RL-планирование.

**ProcessScheduler** (`tpaviot/ProcessScheduler`, ~39★, ⚠️ **GPLv3+**) — Python поверх Z3 SMT-солвера, решает RCPSP, flow shop, multi-objective. Уникален тем, что **встроенно рендерит Gantt через matplotlib и Plotly** — то есть объединяет алгоритмику и визуализацию. v0.6.1 в апреле 2025. GPL — серьёзное ограничение.

**job_shop_lib** (`Pabloo22/job_shop_lib`, ~77★, **MIT** ✅) — JSSP с dispatching rules, CP и **RL-агентами через Gymnasium**, плюс GNN-интеграция. Built-in Gantt-чарты и GIF-визуализация. Активный, ноябрь 2025.

**ALNS** (`N-Wouda/ALNS`, ~586★, **MIT** ✅) — универсальная Adaptive Large Neighborhood Search метаэвристика. Содержит полный RCPSP-пример, конкурентоспособный с PSPLIB best-known. JOSS-публикация. Применяйте, когда CP/MIP не масштабируется.

**psplib** (`PyJobShop/psplib`, **MIT** ✅) — стандартный парсер PSPLIB/Patterson/RCPSP-max/MPLIB. Связка `psplib` + `PyJobShop` стала de facto стандартом 2025–2026 для экспериментов с PSPLIB.

### MIP-моделлеры и устаревшая классика

**PuLP** (`coin-or/pulp`, ~2.3k★, **MIT** ✅) и **Python-MIP** (`coin-or/python-mip`, ~594★, EPL/permissive) — классические MILP-моделлеры под CBC/Gurobi/HiGHS. Не scheduling-специфичные, но множество community-шаблонов формулирует RCPSP через time-indexed pulse-формулировки.

**pyschedule** (`timnon/pyschedule`, ~307★, Apache-2.0) — классический Python-DSL вида `S += T1 < T2`, `T1 += R | R2`, ровно для сценария «10 ресурсов, 100 задач». **Разработка фактически остановилась до мая 2024**, но как историческая референция остаётся ценной — её цитируют все обзоры team scheduling.

## Категория 3. Авто-распределение и AI-роутинг

### GitHub Action-боты с алгоритмами routing

**pozil/auto-assign-issue** (~82★, **CC0-1.0** ✅) — единственный action с реальным **weighted random**: указываете `a:1, b:5, c:2` и распределение учитывает веса плюс расширение команд. v3.0.0 в апреле 2026. Простейшее, но рабочее «manual assignment with auto hints».

**wow-actions/auto-assign** (~44★, **MIT** ✅) — TypeScript, поддержка `org/team` slug, random-pick из N ревьюеров, skipKeywords, label-triggered. v3.0.2 в январе 2025. Жив, активно.

**kentaro-m/auto-assign-action** (~388★, MIT) — самый звёздный, но последний релиз — январь 2024, сидит на грани двухлетней отсечки. Используйте pozil или wow-actions вместо него.

⚠️ Стоит отметить: GitHub Team/Enterprise plan включает **встроенный round-robin и load-balance** для код-ревью с учётом 30-дневной активности и Busy-статуса. Если команда на платном GitHub, это покрывает базовый сценарий бесплатно.

### Self-hosted PM с auto-assignment и AI

**Plane** уже упомянут выше: его AI-агенты и Slack-интеграция (`@Plane create work and assign it`) обеспечивают AI-triage входящих задач — это реальная авто-маршрутизация поверх обычного PM.

**Huly Platform** (`hcengineering/platform`, ~25.4k★, EPL-2.0) — Hulia AI + автоматизационный движок Cards & Processes (триггеры, аппрувы) дают workflow-уровневое распределение задач, плюс Team Planner для визуальной капасити.

**Leantime** даёт уникальный «эмоджи-рейтинг» приоритетов как UX-подсказку — это редкий пример «суджесшнов через UX, а не алгоритм».

⚠️ **Taiga и OpenProject** — оба явно подтверждают в документации/форумах, что **автоматического распределения и расчёта капасити у них нет**. Это чистые трекеры с ручным назначением; включать в категорию авто-распределения некорректно.

### AI-агенты и LLM-маршрутизация задач

**crewAI** (`crewAIInc/crewAI`, ~44.3k★, **MIT** ✅) — самый релевантный AI-движок маршрутизации задач. Hierarchical Process автоматически создаёт Manager-агента, делегирующего задачи crew-членам по ролям/инструментам/способностям. Параметр `allow_delegation=True` позволяет агентам запрашивать помощь у соседей. Активные релизы весь 2026 год.

**Microsoft Agent Framework** (`microsoft/agent-framework`, **MIT** ✅) — наследник AutoGen + Semantic Kernel, GA в 2025. Граф-ориентированные multi-agent workflows с sequential/parallel/Magentic-оркестрацией, A2A и MCP-интеропом. AutoGen (`microsoft/autogen`, ~57.5k★) **переведён в maintenance mode** — для новых проектов используйте agent-framework.

**OpenHands** (`All-Hands-AI/OpenHands`, ~68.6k★, MIT кроме enterprise/) — мультиагентная dev-платформа (бывший OpenDevin) с иерархической делегацией CodeActAgent → BrowsingAgent / VerifierAgent / RepoStudyAgent через инструмент `delegate`. Релевантно, если «команда» включает AI-агентов.

**claude-task-master** (`eyaltoledano/claude-task-master`, ⚠️ **MIT с Commons Clause**) — AI-управление задачами для Cursor/Claude Code/Windsurf. Парсит PRD, разбивает на подзадачи, анализирует сложность, **рекомендует «следующую задачу» с учётом графа зависимостей**, линкует с GitHub Issues/Jira/Linear. 36 MCP-инструментов. Идеальный пример «manual assignment with auto suggestions», но Commons Clause ограничивает коммерческую перепродажу.

### Капасити-нишевые инструменты

**sourcepole/redmine_workload** (GPL-2.0) — плагин Redmine с per-user weekday capacity, отпусками, daily-hour load. Оригинал затих, но форк `JostBaron/redmine_workload` живой. Только если уже на Redmine.

**salzpate/sprint-capa-calc** (Apache-2.0) — JavaFX-десктоп для расчёта sprint capacity FE/BE-команд с Jira-интеграцией. Маленький, но активный.

**aleksandrrudenko/team-schedule** — open-source 24/7 follow-the-sun планировщик с авто-балансом нагрузки между Americas/APAC/EMEA, лимитом овертайма 165–185 ч/мес и справедливой on-call ротацией. Node.js + PostgreSQL. **Автор по нику русскоязычный**, реализован настоящий алгоритм балансировки с жёсткими ограничениями. Лицензию следует уточнить непосредственно в репозитории перед адаптацией.

## Гибридные репозитории, объединяющие несколько аспектов

| Репозиторий | Алгоритмика | Визуализация Gantt | Авто-подсказки | Лицензия |
|---|:---:|:---:|:---:|---|
| **GanttProject** | ✅ critical path, FS/SS/FF/SF | ✅ полноценный десктоп | — | GPL-3.0 |
| **ProcessScheduler** | ✅ Z3 SMT, RCPSP | ✅ matplotlib/Plotly | — | GPL-3.0 ⚠️ |
| **PyJobShop + psplib** | ✅ CP-SAT, RCPSP/JSSP | ✅ через CPMpy/Plotly | — | MIT ✅ |
| **job_shop_lib** | ✅ CP, RL, GNN | ✅ Gantt + GIF | — | MIT ✅ |
| **Timefold Quickstarts** | ✅ constraint solver | базовый HTML/JS | — | Apache-2.0 ✅ |
| **CPMpy flexible jobshop example** | ✅ CP | ✅ Plotly Gantt | — | Apache-2.0 ✅ |
| **Plane** | частично (AI triage) | ✅ Timeline + critical path | ✅ AI-агенты | AGPL-3.0 ⚠️ |
| **Huly** | частично (Processes) | ✅ Team Planner | ✅ Hulia AI | EPL-2.0 ⚠️ |

**Чистая алгоритмика без воды:** OR-Tools (RCPSP-пример), Timefold-solver, PyJobShop, CPMpy, ALNS, ProcessScheduler, job_shop_lib, airbus/discrete-optimization. Все остальные «PM-системы» с авто-распределением реально применяют либо weighted random (pozil), либо LLM-делегацию (crewAI, Plane AI, Huly Hulia) — это *не* математическая оптимизация.

**Готовые шаблоны под Timefold/OR-tools для команды:**
- `TimefoldAI/timefold-quickstarts` → подкаталоги `project-job-scheduling` и `quarkus-task-assigning` — самый прямой ready-to-run шаблон.
- `google/or-tools` → `examples/python/rcpsp_sat.py` (PSPLIB-совместимый RCPSP).
- `CPMpy/cpmpy` → `examples/flexible_jobshop` с готовой Gantt-визуализацией.
- `d-krupke/cpsat-primer` → авторитетный обучающий код CP-SAT.

## Русскоязычные разработчики и их проекты

В исследовании уверенно идентифицировано **четыре проекта с русскоязычными мейнтейнерами**: **GanttProject** (Дмитрий Барашев, BarD Software) — самый сильный десктопный планировщик с критическим путём; **SVAR Gantt** (команда mkozhukh, ex-XB Software/DHTMLX из Беларуси) — современный модульный Gantt-компонент под MIT; **gantt-task-react** (`MaTeMaTuK`) — популярная React-библиотека, но активность автора замедлилась; и **team-schedule** (`aleksandrrudenko`) — нишевый, но единственный из найденных с настоящим алгоритмом балансировки нагрузки. Полноценных русскоязычных RCPSP/CP-проектов в активной поддержке найти не удалось — здесь рекомендуется отдельный целевой поиск, если это критическое требование.

## Заключение и практические выводы

Главный неочевидный вывод: **наиболее звёздные репозитории (Plane 46k, Huly 25k, OpenProject 15k) почти не содержат настоящей алгоритмической оптимизации** — они дают визуализацию, manual assignment и в лучшем случае LLM-агента поверх. Реальная математика живёт в Apache-2.0/MIT-библиотеках с 100–1500 звёздами (Timefold, PyJobShop, OR-Tools примеры, CPMpy). Это означает, что для команды до 10 человек **архитектурно правильно разделить два слоя**: PM-фронт (Plane/OpenProject/Huly или embedded Frappe/SVAR Gantt) для UX и backend-solver (Timefold или PyJobShop) для оптимизации, связанные через REST-API.

Второй существенный вывод касается лицензий: **AGPL/GPL/EPL практически неизбежны в зрелых web-PM** (Plane, OpenProject, Leantime, Vikunja, Huly, GanttProject) — это нормально для внутреннего self-hosting, но делает их непригодными для продуктивизации в коммерческий SaaS без юридической работы. Все ключевые solver-библиотеки и embeddable Gantt-компоненты, наоборот, под MIT/Apache-2.0 — встраивайте свободно.

Третий вывод: «AI task routing» как маркетинговая категория в 2026 году означает либо **LLM-делегацию между агентами** (crewAI, Microsoft Agent Framework, OpenHands) — это уже реальная технология, либо **AI-suggestion над графом зависимостей задач** (claude-task-master, Plane AI). Оба сценария дополняют, а не заменяют constraint-based оптимизацию: для распределения 50–100 задач между 10 разработчиками с учётом скиллов и календарей Timefold даст математически оптимальный результат, тогда как LLM-агент полезнее для семантической классификации входящих и подсказки приоритетов.