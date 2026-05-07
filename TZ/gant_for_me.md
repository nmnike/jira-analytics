# Высокоуровневая архитектура и концепция системы Resource Planning поверх Jira

## Введение и принципы проектирования

Документ описывает концептуальный design системы планирования ресурсов (далее — **RPM, Resource Planning Module**), которая надстраивается над уже существующей аналитической системой на базе Jira. Ключевая идея: Jira остаётся **системой записи** (system of record) для задач, статусов, оценок, исполнителей и связей; RPM выступает **системой решения** (system of decision) — слоем, в котором эти же данные интерпретируются как сетевой график, расписание и план загрузки ресурсов.

Принципы, которым подчинён весь дизайн:

| Принцип | Что означает на практике |
|---|---|
| **Read-mostly над Jira** | RPM не пишет автоматически в Jira; любая запись (e.g. предлагаемые даты, новый assignee) проходит через явный commit пользователя. |
| **Sandbox-семантика** | План — это «параллельный мир» поверх Jira. По образцу Atlassian Plans / BigPicture сценарии живут отдельно от issues, пока не «опубликованы». |
| **Идемпотентность пересчёта** | Любой пересчёт расписания при тех же входах даёт тот же результат; алгоритмы детерминированы (или seed-управляемы для метаэвристик). |
| **Объяснимость (no black box)** | Для каждой задачи в Gantt должно быть видно, ПОЧЕМУ она поставлена в эту дату (предшественник X, ресурсная конкуренция Y, calendar Z). |
| **Деградация на грязных данных** | Отсутствующая оценка, разорванная ссылка, нулевой assignee — это нормальный кейс, а не ошибка. RPM должен работать в degraded-режиме с явной маркировкой неполных данных. |
| **Масштаб 1k+ задач** | Расчётный движок проектируется на инкрементальные пересчёты и партиционирование по проектам; полный пересчёт — fallback, не норма. |
| **Технологическая нейтральность** | Логика отделена от UI и от хранилища. Проектируем модели и алгоритмы, а не конкретный фреймворк. |

---

## 1. Architecture Overview

### 1.1. Слоевая модель

RPM спроектирован как набор из четырёх логических слоёв, связанных однонаправленно (от Jira «вверх» к UI). Это даёт чистое разделение обязанностей и возможность независимо тестировать каждый слой.

```
┌──────────────────────────────────────────────────────────────────────────┐
│  L4. Presentation Layer (Gantt UI, Capacity Heatmap, What-If Workbench) │
│      ↑ запрос проекций, push-обновления через event-bus                 │
├──────────────────────────────────────────────────────────────────────────┤
│  L3. Planning Logic Layer                                               │
│      • Scheduling Engine (CPM, leveling, RCPSP-эвристики)              │
│      • Resource Allocation Engine (auto-assignment, skill match)        │
│      • Conflict Detector                                                │
│      • Scenario Manager (what-if, baselines, diff)                      │
├──────────────────────────────────────────────────────────────────────────┤
│  L2. Canonical Domain Model + Planning Store                            │
│      • Project / Task / Dependency / Resource / Allocation / Calendar   │
│      • Snapshots, baselines, scenarios                                  │
├──────────────────────────────────────────────────────────────────────────┤
│  L1. Data Ingestion Layer                                               │
│      • Jira REST/Webhook adapter                                        │
│      • Normalizer & Data Quality module                                 │
│      • Existing Analytics DB (исторические worklogs, velocity)         │
└──────────────────────────────────────────────────────────────────────────┘
                            ↑       ↓
                        Jira Cloud / DC (system of record)
```

### 1.2. Назначение слоёв

**L1. Data Ingestion.** Отвечает за извлечение и обновление данных из Jira и из существующей аналитической БД. Состоит из:

- **Jira Adapter** — обёртка над REST API (`/search`, `/issue/{key}`, `/issuelink`, `/sprint`, `/worklog`, `/user`, `/field`); работает в двух режимах — bulk-sync (по расписанию, для пакетной загрузки квартальных проектов) и event-driven (через webhooks `jira:issue_updated`, `jira:issue_created`, `jira:issue_link_created/deleted`).
- **Historical Analytics Reader** — читает уже накопленные исторические данные (фактическая длительность похожих задач, velocity команд, throughput по типам issue) — они нужны как fallback-источник оценок и для калибровки.
- **Normalizer** — приводит сырые JSON к канонической доменной модели (см. §2). Сюда же входит **Data Quality module**, который маркирует каждую сущность набором флагов (`missing_estimate`, `assignee_inactive`, `circular_dependency_suspected`, `no_dates`).

**L2. Canonical Domain Model + Planning Store.** Промежуточный слой, в котором живут «очищенные» сущности и состояния планов. Это собственная БД RPM (graph- или relational-like), не Jira. В ней же хранятся:

- snapshot’ы планов (immutable)
- baselines (зафиксированные «обещанные» расписания для сравнения с фактом)
- scenarios (рабочие копии для what-if)
- calendars и resource pools

**L3. Planning Logic.** Чистые алгоритмические модули, без I/O. Каждый получает на вход доменную модель (или её срез) и возвращает новый scenario state:

- **Scheduling Engine** — CPM (forward/backward pass), Critical Path, обработка типов зависимостей, scheduling modes (ASAP, ALAP, MFO/MSO).
- **Resource Allocation Engine** — назначение задач на конкретных людей с учётом ролей, скиллов, capacity, календарей.
- **Conflict Detector** — классификатор и quantifier конфликтов.
- **Leveling/RCPSP solver** — двигает задачи во времени, чтобы убрать overallocation, при ограничении не нарушать дедлайны критического пути.
- **Scenario Manager** — управляет сценариями, diff-ами и сравнениями.

**L4. Presentation.** Gantt, Resource Heatmap, Capacity Dashboard, Scenario Comparator, конфликт-инспектор. UI читает **проекции** (read-models), не доменную модель напрямую — это изолирует визуализацию от изменений алгоритмики.

### 1.3. Потоки данных (data flows)

Существуют четыре основных потока:

1. **Initial Load (бутстрап квартала).** Список утверждённых проектов → JQL-запросы в Jira → Normalizer → canonical store → автоматический первичный schedule (ASAP) → baseline #0.
2. **Continuous Sync.** Webhook от Jira → инкрементальное обновление сущностей → re-trigger планировочного движка только на затронутом подграфе → publish событий в UI.
3. **What-If Flow.** Пользователь форкает scenario → редактирует (двигает дату, меняет ресурс, удаляет задачу) → движок пересчитывает → diff против baseline → визуализация.
4. **Commit Flow.** Принятый сценарий (или его часть) → генерирует diff-команды для Jira (через тот же Adapter, в режиме записи) → Jira становится consistent с планом.

### 1.4. Ключевые компоненты (компонентная диаграмма)

```
[Jira] ⇄ Jira Adapter ─→ Normalizer ─→ Canonical Store ─→ Scheduling Engine
                            │              │ ↑              ↓
                            ↓              │ │            Critical Path Calc
                       DQ Flags      Scenario Mgr ─────→ Allocation Engine
                                          │ ↑              ↓
                                          │ │           Conflict Detector
                                          ↓ │              ↓
                                      Read Models ←── Leveling/RCPSP
                                          ↓
                                 Gantt UI / Heatmaps / Dashboards
```

Расчётные модули устроены как **pipeline of pure functions**: `(state, command) → state'`. Это упрощает логирование, repro-кейсы и unit-тестирование без mock-объектов Jira.

---

## 2. Data Model

### 2.1. Канонические сущности

Доменная модель сознательно беднее, чем у MS Project — в ней зафиксировано только то, что осмысленно поверх Jira-данных.

#### Project
| Поле | Описание |
|---|---|
| `project_id` | Внутренний UUID. |
| `jira_keys[]` | Список Jira-проектов/JQL-источников, формирующих scope. Поддерживается множественность, как у Jira Plans. |
| `name`, `quarter`, `priority` | Утверждённый список квартала задаёт `quarter` и `priority` (для leveling). |
| `start_target`, `end_target` | Целевые границы квартала (мягкие constraint’ы). |
| `default_calendar_id` | Календарь по умолчанию для задач, у которых нет ресурса. |

#### Task
| Поле | Описание |
|---|---|
| `task_id`, `jira_key`, `summary` | Идентификация. |
| `type` | Тип Jira (Story/Task/Bug/Epic), используется для эвристик. |
| `status`, `status_category` | To Do / In Progress / Done — влияют на scheduling (см. §3). |
| `original_estimate_h`, `remaining_estimate_h`, `story_points` | Сырые оценки. |
| `derived_duration_d` | Расчётная длительность в **календарных днях** после применения правил конвертации (см. §4). |
| `assignee_user_id` | Может быть `null`. |
| `required_role`, `required_skills[]` | Из custom fields или маппинга по типу задачи (см. §2.3). |
| `scheduling_mode` | `ASAP` / `ALAP` / `MUST_START_ON` / `MUST_FINISH_ON` / `START_NO_EARLIER_THAN` / `FINISH_NO_LATER_THAN`. По умолчанию ASAP. |
| `manual_dates` | Если PM явно зафиксировал даты — pin. |
| `computed_es, ef, ls, lf, slack` | Результат CPM. |
| `is_on_critical_path` | bool. |
| `dq_flags[]` | `missing_estimate`, `no_assignee`, `inactive_assignee`, `cycle_suspected`, ... |

#### Dependency
| Поле | Описание |
|---|---|
| `from_task_id`, `to_task_id` | Направление. |
| `type` | `FS` / `SS` / `FF` / `SF`. |
| `lag_d` | Лаг в календарных днях, может быть отрицательным (lead). |
| `source` | `jira_link` (issue link типа Blocks/Depends on), `manual`, `inferred` (вывели из иерархии Epic→Story). |
| `confidence` | Низкая для inferred, высокая для explicit. |

#### Resource
| Поле | Описание |
|---|---|
| `resource_id` | Может быть человеком (`user`) или ролью (`role`/«виртуальный ресурс»). |
| `jira_account_id` | NULL для ролевых ресурсов. |
| `roles[]`, `skills[]` | Multi-skill. |
| `team_id`, `cost_rate` | Опционально. |
| `calendar_id` | Личный календарь. |
| `capacity_per_day_h` | Обычно 6 часов на рабочий день (focused capacity, не 8). |
| `availability_factor` | 0..1, «практическая» ёмкость с учётом митингов, on-call и т. п. |

#### Allocation
| Поле | Описание |
|---|---|
| `allocation_id`, `task_id`, `resource_id` | Ключи. |
| `units` | Доля занятости (0..1+). 1.0 = full-time на эту задачу, 0.5 = половина. |
| `start_date`, `end_date` | Календарные. |
| `hours_total`, `hours_per_day_curve` | Распределение нагрузки внутри окна (плоское/треугольное/профильное). |
| `assignment_source` | `jira` / `manual` / `auto-role` / `auto-skill`. |

#### Calendar
| Поле | Описание |
|---|---|
| `calendar_id`, `name` | — |
| `working_days[]` | Маски недели. |
| `working_hours_per_day` | По умолчанию 8, конвертация см. §4. |
| `exceptions[]` | Праздники, отпуска, sprint goals, индивидуальные absence-периоды. |
| `timezone` | — |

#### Дополнительные сущности

- **Scenario** — `scenario_id`, `parent_id` (форкинг), `created_at`, `description`, набор overrides поверх baseline.
- **Baseline** — снимок состояния плана на момент его утверждения. Поддерживается несколько baseline’ов (B0, B1, B2 …), как в MS Project (там их 11). Используется для сравнения с фактом.
- **Conflict** — материализованный объект (см. §5), а не только runtime-warning. Это нужно для истории и assignment’а владельцев конфликта.

### 2.2. Маппинг Jira → планировочная модель

| Jira-источник | Канонический атрибут | Правило |
|---|---|---|
| Issue Link типа `blocks` / `is blocked by` | Dependency FS | Стандартное соответствие, как в Advanced Roadmaps. |
| Issue Link типа `depends on`, `causes` | Dependency FS | Аналогично. |
| Custom link types `starts with`, `finishes with` | SS/FF | Если в инстансе Jira настроены такие типы. |
| Epic → Story link | Hierarchy, не dependency | Не превращается в FS автоматически (anti-pattern Advanced Roadmaps). |
| `Original estimate` (h) | `original_estimate_h` | Прямое чтение. |
| `Story points` | `story_points` | Конвертация в часы через velocity команды (historical). |
| `Sprint` | Подсказка для scheduling | Если есть sprint и нет дат — план берёт даты sprint, как в Plans. |
| `Due date` | `manual_dates.end` или `FINISH_NO_LATER_THAN` constraint | По выбору пользователя. |
| `Assignee` | `Allocation.resource_id` | Создаётся как manual allocation. |
| Custom field `Required Role` | `Task.required_role` | Если нет — выводится из Project + issue type. |
| Worklog | Не входит в forward-looking, но используется для калибровки velocity и в Conflict Detector (фактическая загрузка). |  |
| Sub-task | Hierarchy + mostly FS sequence | По умолчанию sub-task’и считаются параллельно реализуемыми, если иначе не указано. |

### 2.3. Правила обработки missing-данных

Это критическая часть, потому что Jira-данные несовершенны. Для каждого «дырявого» поля определена стратегия:

| Дырка | Стратегия | Маркировка |
|---|---|---|
| Нет original estimate, есть story points | Конвертация по средней скорости команды за последние N спринтов: `hours = SP × hours_per_SP_team`. Если команда новая — используется глобальная медиана. | `dq_flags: estimate_inferred` |
| Нет ни estimate, ни SP | Подстановка медианной длительности по `(project, issue_type)` из исторических данных. Если истории нет — подставляется default (например, 3 дня) с пометкой. | `estimate_default` |
| Нет assignee | Задача попадает в **virtual resource pool** соответствующей роли. Allocation Engine может назначить её в фазе auto-assignment. | `no_assignee` |
| Inactive / уволенный assignee | Игнорируется, задача переводится в pool как выше. | `inactive_assignee` |
| Битая ссылка (link на удалённый issue) | Пропускается, событие логируется. | `broken_link` |
| Подозрение на цикл в dependency-графе | Цикл локализуется, последняя «проблемная» ребро помечается как `disabled` для расчёта, выдаётся warning. | `cycle_suspected` |
| Story в нескольких Epic’ах с разными датами | Берётся пересечение констрейнтов; если оно пусто — конфликт. | `epic_conflict` |
| Нет dates вообще, нет sprint | ES = ASAP-from-deps; если нет deps — ES = project.start_target. | `auto_dated` |

Все DQ-флаги выводятся в UI как **бэйджи** на task bar, чтобы PM сразу видел, насколько данной строке Gantt можно доверять. Это и есть «explainability» в действии.

---

## 3. Scheduling Logic

### 3.1. Граф задач и сетевая модель

Внутренне расписание представлено как **AON (Activity-on-Node) DAG**: вершины — задачи, рёбра — зависимости с типом и lag’ом. Перед запуском CPM граф проверяется на:
- ацикличность (топологическая сортировка через Kahn algorithm; ребро, ломающее порядок, помечается и исключается из расчёта),
- наличие источников (задач без предшественников) и стоков (без преемников).

### 3.2. Forward Pass (расчёт ES/EF)

Идёт в топологическом порядке. Для каждой задачи `i`:

```
ES_i = max( predecessor_finish + lag, project_start, manual_constraint_min )
EF_i = ES_i + duration_i
```

Где `predecessor_finish` зависит от типа зависимости:

| Тип | Формула вклада в ES_i |
|---|---|
| **FS** (Finish-to-Start) | `EF_pred + lag` |
| **SS** (Start-to-Start) | `ES_pred + lag` |
| **FF** (Finish-to-Finish) | вклад в EF: `EF_i ≥ EF_pred + lag` |
| **SF** (Start-to-Finish) | вклад в EF: `EF_i ≥ ES_pred + lag` (редкий тип) |

Все даты в системе — **рабочие даты** (working dates) с учётом календаря ресурса. То есть «+ 5 дней» означает «+ 5 рабочих дней по календарю того, кто назначен на задачу или, если не назначен, по project default calendar».

### 3.3. Backward Pass (расчёт LS/LF)

Идёт в обратной топологической последовательности. Стартовое значение для последней (последних) задачи:

```
LF_last = max(EF_last, project_end_target)
LS_i = LF_i − duration_i
```

Для предшественников:

```
LF_i = min over successors ( LS_succ − lag    if FS
                           | EF_succ − lag    if FF
                           | LS_succ − lag    if SS — вклад в LS_i, не в LF_i
                           | EF_succ − lag    if SF )
```

### 3.4. Slack и Critical Path

```
Total Slack_i = LS_i − ES_i = LF_i − EF_i
Free Slack_i  = min(ES_succ) − EF_i     (для FS-преемников)
```

**Базовый Critical Path**: множество задач с `Total Slack ≤ 0` (нулевой slack или отрицательный — последнее означает уже невыполнимые сроки). Цепочка визуализируется красным.

**Продвинутый Critical Path**:
1. **Resource-Critical Path (RCP)** — учитывает не только логические зависимости, но и ресурсные. После leveling задачи могут «упереться» друг в друга через общий ресурс, формируя resource-induced dependencies. RCP — это критический путь по DAG, расширенному этими виртуальными рёбрами.
2. **Multi-tier critical path** — задачи с отрицательным slack (uncatchable) показываются ярко-красным, нулевым slack — красным, slack ≤ threshold (e.g. 2 дня) — оранжевым. Это даёт PM «зону риска», а не только бинарный критический путь.
3. **Probabilistic CP (PERT-style)** — для каждой задачи считаем `t_e = (t_o + 4·t_m + t_p) / 6` и `σ²`. Затем длительность пути = сумма `t_e`, дисперсия = сумма `σ²`. Получаем не одну дату завершения, а распределение, и можем сказать «P90 окончания проекта = такая дата». Реализуется опционально как Monte-Carlo over CPM.

### 3.5. Параллельные задачи и обработка отсутствия зависимостей

Задачи без предшественников стартуют в `project.start_target` (с учётом scheduling mode). Задачи без преемников «упираются» в `project.end_target` при backward pass.

Если две задачи не связаны зависимостью, они **параллельны** по графу. Это нормально: их одновременная исполнимость дальше проверяется ресурсным слоем (§4), который и решит, что либо нужен второй ресурс, либо одна из задач должна сдвинуться.

### 3.6. Scheduling modes для отдельных задач

| Режим | Поведение |
|---|---|
| `ASAP` (по умолчанию) | ES = max ограничений; задача ставится как можно раньше. |
| `ALAP` | LF = min ограничений; задача ставится как можно позже. Полезно для «неблокирующих» работ. |
| `MUST_START_ON` / `MUST_FINISH_ON` | Жёсткая фиксация даты; нарушение — конфликт типа `unrealistic_deadline`. |
| `START_NO_EARLIER_THAN` / `FINISH_NO_LATER_THAN` | Мягкие границы. |

Поведение совпадает с MS Project Constraint Types и обеспечивает PM-контроль над теми задачами, где Jira-данные неточны.

### 3.7. Обработка задач, уже находящихся в процессе

Задачи в статусе `In Progress` не пересчитываются назад: их ES = фактическая дата начала, оставшаяся длительность считается по `remaining_estimate`, а не по `original`. Задачи в статусе `Done` исключаются из расчёта (но остаются на Gantt как историческая полоса).

### 3.8. Инкрементальный пересчёт

Полный CPM по 1000+ задачам — это секунды. Но при каждом webhook’е делать full pass — расточительно. Поэтому:

1. При изменении задачи `T` определяется её **forward closure** (все потомки) и **backward closure** (все предки).
2. Пересчитываются только эти подграфы.
3. Если изменился ресурс или его календарь — пересчитываются только задачи с этим ресурсом.

Для масштаба 1k+ задач это даёт sub-second реактивность.

---

## 4. Resource Allocation

### 4.1. Манульное назначение (из Jira)

Если у задачи есть `assignee` в Jira, RPM создаёт `Allocation` со `source = jira` и `units = 1.0` (если не указано иначе через custom field). Это базовый случай — для большинства задач он сразу даёт работающий план.

### 4.2. Auto-assignment по ролям и скиллам

Для задач без assignee (или с `inactive_assignee`) запускается **Resource Allocation Engine**. Алгоритм многошаговый:

**Шаг 1. Определение требования.** Задача описывается тройкой `(required_role, required_skills[], hours_total)`. Если эти поля не заполнены явно, они выводятся:
- из issue type (например, `Bug` → role `Developer`),
- из labels / components (`label: frontend` → skill `React`),
- из истории (по похожим прошлым задачам этого проекта).

**Шаг 2. Формирование пула кандидатов.** Из всех `Resource` отбираются те, у кого:
- `roles ⊇ {required_role}`,
- `skills ⊇ required_skills` (полное совпадение) или `|skills ∩ required_skills| / |required_skills| ≥ θ` (частичное, маркируется `partial_skill_match`).

**Шаг 3. Скоринг кандидатов.** Каждый кандидат получает score:

```
score = w1 · skill_match
      + w2 · availability_in_window
      + w3 · historical_velocity_on_similar_tasks
      − w4 · current_load_in_window
      − w5 · context_switches (число параллельных проектов)
```

Веса конфигурируются. Это важно: алгоритм не black-box, а явно ранжирует кандидатов по понятным метрикам.

**Шаг 4. Назначение.** Выбирается top-1 кандидат, при условии что после allocation его загрузка не превысит порог `over_threshold` (см. §5). Если превышает — берётся next-best, либо задача попадает в pool «без ресурса» с конфликтом `understaffed`.

**Шаг 5. Тай-брейкеры.** При равенстве score — приоритет: (1) уже работает на этом проекте, (2) меньше параллельных проектов, (3) algorithm-stable порядок (для воспроизводимости).

Auto-assignment работает в двух режимах:
- **Suggestion mode** (по умолчанию): RPM показывает рекомендации, PM подтверждает.
- **Auto-apply mode**: для типов задач, помеченных `auto_assignable: true`, ассайнмент происходит без подтверждения, но всегда логируется и обратим.

### 4.3. Конвертация estimates в календарные блоки

Это узкая, но критическая логика. Estimate в Jira — это **трудозатраты** (effort), а не **длительность** (duration). Между ними нужна явная конвертация:

```
duration_days = ceil( hours_total / (resource.capacity_per_day_h × allocation.units) )
```

Пример: задача 24h, ресурс с capacity 6h/day, units = 0.5 (половина рабочего дня) → duration = 24 / (6 × 0.5) = 8 рабочих дней.

Дополнительно учитываются:
- **Календарь ресурса**: 8 рабочих дней раскладываются в окно с пропуском weekend и personal absence.
- **Профиль нагрузки**: по умолчанию плоский (равномерное распределение часов по дням), но поддерживаются:
  - **front-loaded** (больше в начале — для discovery-задач),
  - **back-loaded** (больше в конце — для тестирования / стабилизации),
  - **bell** (треугольный — для имплементации).
- **Минимальный неделимый блок**: задачи короче 0.5 дня округляются до 0.5 для предотвращения «крошки».

Если задача оценена в SP, конвертация двойная: `SP → hours (через team velocity) → duration (через calendar)`.

### 4.4. Учёт capacity и non-working days

Каждый ресурс имеет:
- базовый capacity (например, 6h/day × 5 days = 30h/week — это уже учитывает митинги/контекст-свитчинг),
- календарь с государственными праздниками,
- персональные исключения (отпуск, болезнь — обычно вносятся вручную или sync с HR-системой),
- `availability_factor` для системного срезания (например, 0.8 для тимлида, у которого 20% времени уходит на менеджмент).

Effective daily capacity = `capacity_per_day_h × availability_factor` в рабочие дни календаря.

### 4.5. Multi-project resource leveling

Это ключевой пункт, отличающий portfolio-планировщик от single-project. RPM знает обо всех квартальных проектах одновременно и леверит ресурсы across-project.

**Алгоритм leveling**:

1. **Compute violations.** Для каждого ресурса и каждого дня квартала считается `daily_load(r, d) = Σ allocations active on d`. Если `daily_load > capacity × over_threshold` — violation.

2. **Сортировка задач для разрешения.** Используется priority queue, как в MS Project «Standard» алгоритме. Приоритеты (от выше к ниже):
   1. `Project.priority` (утверждённый ранг).
   2. `Total Slack` (меньше slack — выше приоритет, нельзя двигать).
   3. Длительность (короткие двигаются легче).
   4. Дата start (ранние идут раньше).
   5. Ручной `Task.priority` (если задан).

3. **Стратегии разрешения** (применяются по очереди, для каждой задачи):
   - **Delay** — сдвиг задачи в slack’е (если slack > 0). Нулевая стоимость.
   - **Split** — разбиение задачи на два сегмента, если ресурс свободен «островами». Опционально, поскольку в Jira это не нативно.
   - **Reassign** — попытка переназначить на другого ресурса с теми же скиллами. Использует тот же скоринг, что и auto-assignment.
   - **Compress** — увеличение `units` или подключение второго ресурса (если задача не fixed-duration). Уменьшает длительность.
   - **Escalate as conflict** — если ничего не сработало, leveling помечает задачу как `unresolvable_overallocation`, и её приходится решать руками.

4. **Cross-project arbitrage.** Если два проекта конкурируют за одного человека, leveling ставит более приоритетный проект первым (по `Project.priority`), а второй — двигает на slack или pool. Если slack нет — конфликт эскалируется (см. §5).

5. **Multi-objective minimization.** Целевая функция:
```
minimize:  Σ delay_critical_tasks · w_critical
         + Σ (peak_load − avg_load)² · w_smoothness
         + Σ context_switches · w_switching
subject to: precedence, calendars, hard constraints
```

Это стандартный RCPSP в академической формулировке. Для задач квартала (≤2k задач, ≤200 ресурсов) даже простая priority-rule heuristic (SGS — Serial Generation Scheme с правилом «minimum slack first») даёт качество в пределах нескольких процентов от оптимума за миллисекунды. Опционально можно подключить генетический алгоритм для batch-режима overnight (как в исследованиях RCPSP на PSPLIB).

### 4.6. Поведение для частичной занятости и shared resources

Поддерживается случай `units < 1` (50% time на задачу) и одновременно несколько таких задач у одного человека (например, 0.5 + 0.5 = 100%). Если сумма units в данный день ≤ 1.0 — это не конфликт. Если > 1.0 — overallocation.

---

## 5. Conflict Detection

### 5.1. Типология конфликтов

| Код | Тип | Описание | Severity |
|---|---|---|---|
| `OVR.LIGHT` | Overbooking 100–110% | Лёгкое превышение capacity, в пределах буфера. | low (warning) |
| `OVR.MED` | Overbooking 110–120% | Заметное превышение, требует внимания. | medium |
| `OVR.HIGH` | Overbooking >120% | Критическое; либо людей не хватает, либо плохие оценки. | **critical** |
| `PAR.OVL` | Parallel overload | Один ресурс одновременно на 3+ задачах разных проектов. Сам по себе не overbooking (units могут давать ≤1.0), но context-switch penalty велик. | medium |
| `DEAD.MISS` | Unrealistic deadline | EF задачи > Due date или > project end. Slack < 0. | critical |
| `SKILL.MIS` | Skill mismatch | Назначен ресурс без нужных скиллов (или с partial-match ниже θ). | medium |
| `ROLE.MIS` | Role mismatch | Junior на Senior-задаче (по historical velocity сильно медленнее). | low |
| `DEP.BROKEN` | Broken dependency | Ссылка указывает на removed/closed issue. | low |
| `DEP.CYCLE` | Cycle in dependencies | Обнаружен цикл; логика разорвала ребро для расчёта. | medium |
| `EST.MISSING` | No estimate (DQ) | Использован default — план ненадёжен. | low |
| `ASSIGN.NONE` | No assignee | Задача в virtual pool, не aut-assigned. | low/medium |
| `CAL.HOLIDAY` | Allocation на нерабочий день | Конфликт календаря (обычно после ручного редактирования). | medium |
| `CAP.PROJECT` | Project-level overcommit | Сумма demand по проекту > сумма capacity всех его команд за квартал. | critical (на capacity dashboard) |

### 5.2. Пороги (thresholds) и их конфигурируемость

Пороги вынесены в **policy configuration**, чтобы организация могла адаптировать систему под свою культуру. Дефолты:

| Параметр | Значение по умолчанию | Где задаётся |
|---|---|---|
| `over_threshold_warning` | 100% | global |
| `over_threshold_critical` | 120% | global, override per team |
| `parallel_tasks_max` | 2 одновременно | per role |
| `partial_skill_threshold θ` | 0.6 | global |
| `slack_warning_days` | 2 | global |
| `min_estimate_h` | 1h | global (всё короче округляется) |

### 5.3. Правила детекции

Detector работает в двух режимах:

**Real-time** — после каждого scheduling-расчёта, для каждого ресурса по дням; для каждой задачи; для каждого ребра графа. Сложность O((tasks + resources × days)) — линейна.

**Aggregate** — раз в N (или по запросу), считает quarter-level конфликты `CAP.PROJECT` через суммы по всему кварталу.

Для каждого обнаруженного конфликта создаётся объект `Conflict`:

```
Conflict {
  id, type, severity,
  affected_tasks[], affected_resources[],
  window: [date_from, date_to],
  metric_value (например, 145% load),
  suggested_resolutions[] (delay 3d / reassign to user X / split),
  status (open / acknowledged / resolved / muted),
  created_at, scenario_id
}
```

Это позволяет вести **conflict register** — список открытых проблем, владельцев, истории.

### 5.4. Объяснимость конфликтов

Для каждого конфликта система должна уметь ответить на вопрос «почему?»:

> «Ресурс Иванов И. перегружен 13 марта на 145% потому, что одновременно активны: TASK-101 (units 1.0, проект A, slack 3 дня), TASK-204 (units 0.5, проект B, slack 0 — критический путь). Рекомендация: сдвинуть TASK-101 на +3 дня в пределах его slack’а.»

Эта генерация рекомендаций — простая rule-based логика поверх метрик задач, не ML. Это обеспечивает explainability.

---

## 6. Gantt Representation

### 6.1. Структура данных Gantt (read-model)

Для UI создаётся проекция, оптимизированная под рендеринг:

```
GanttProjection {
  rows: [
    GanttRow {
      row_id, parent_row_id (для иерархии Project → Epic → Story),
      label, jira_key,
      bar: { start_date, end_date, progress_pct, color, pattern },
      slack_indicator: { trailing_bar: [end_date, end_date + slack] },
      is_on_critical_path: bool,
      dq_badges: [...],
      conflict_badges: [...],
      assignee: {name, avatar},
      milestone_at: optional_date  // для milestone типов
    }
  ],
  arrows: [
    GanttArrow { from_row, to_row, type (FS/SS/FF/SF), is_violated }
  ],
  swimlanes: [   // альтернативная группировка
    Swimlane { resource_id, daily_load_curve[], capacity_curve[] }
  ],
  timescale: { granularity (day/week/month), start, end }
}
```

### 6.2. Ключевые элементы UI

| Элемент | Поведение |
|---|---|
| **Task bar** | Полоса от ES до EF. Цвет: серый (To Do), синий (In Progress), зелёный (Done), красный (Critical Path), оранжевый (near-critical, slack ≤ threshold). Прогресс — заливкой. |
| **Slack tail** | Полупрозрачный «хвост» справа от bar до LF — визуализирует free slack. |
| **Dependency arrow** | Линия со стрелкой между bar’ами. Тип помечается миниатюрной нотацией FS/SS/FF/SF на стрелке. Нарушенные зависимости (если manual override) — красные. |
| **Critical path highlight** | Все задачи и стрелки CP подсвечены. Toggle on/off. Можно показывать также Resource-CP отдельным цветом. |
| **Milestone** | Ромбик/diamond shape, нулевая длительность. |
| **DQ badge** | Маленькая пиктограмма у task bar: «?» если нет estimate, «👤» если no assignee, «⚠» при cycle. Hover — детали. |
| **Conflict badge** | Красный/оранжевый кружок с числом (количество конфликтов на задаче). |
| **Resource swimlane mode** | Альтернативный режим: рядом с каждым ресурсом — все его задачи + heat-bar daily load (зелёный <80%, жёлтый 80–100%, красный >100%). |
| **Today marker** | Вертикальная линия. |
| **Baseline overlay** | Тонкая линия под task bar — где задача планировалась изначально. Сдвиг = drift. |

### 6.3. Временные шкалы

Минимум три уровня масштабирования:
- **Days** — для оперативного планирования спринта (горизонт 2–4 недели).
- **Weeks** — для квартального плана (горизонт 3 месяца).
- **Months** — для portfolio-обзора (горизонт год).

Принцип: при zoom in/out **группируется** иерархия (Epic-уровень в weeks/months, Story-уровень в days). Это критично для масштаба 1k+ задач — single-row на 1000 задач нечитаем.

### 6.4. Иерархическое сворачивание

WBS-дерево слева от Gantt:
- Project → Epic → Story → Sub-task.
- Сворачивание parent’а агрегирует bar’ы детей в **roll-up bar** (с минимальной ES детей и максимальной EF). Это поведение и BigPicture, и MS Project.

### 6.5. Требования к UI

- **Drag & drop** task bar для изменения дат (с валидацией: нельзя двигать так, чтобы нарушить hard constraint).
- **Drag dependency** — рисование стрелки между задачами создаёт `manual` dependency.
- **Inline edit** длительности и assignee, с немедленным пересчётом.
- **Filters**: по проекту, ресурсу, статусу, наличию конфликтов, slack’у.
- **Export**: в PNG/PDF/MS Project XML — последнее для совместимости.
- **Keyboard navigation** — для production-режима.
- **Виртуализация рендеринга** — без неё 1000+ строк не вытянуть.

---

## 7. Replanning Logic

### 7.1. Триггеры для перепланирования

| Событие | Источник | Реакция |
|---|---|---|
| Изменение estimate в Jira | webhook | пересчёт duration → forward/backward closure → recompute |
| Смена статуса (To Do → In Progress) | webhook | start_actual фиксируется, ES задачи pin’ится |
| Смена статуса (→ Done) | webhook | задача исключается из активного расчёта, снижает demand |
| Смена assignee | webhook | recalculate allocation (новый календарь, новая capacity) |
| Создание/удаление dependency | webhook | rebuild соответствующего подграфа |
| Резерв absence ресурса | manual / HR-sync | calendar update → recompute allocations этого ресурса |
| Изменение scope проекта (добавили/убрали задачу) | webhook + бизнес-решение | full project subgraph recompute |
| Изменение приоритетов (Project.priority) | manual | relevel multi-project |
| Manual drag в Gantt | UI | apply override → recompute → diff против baseline |

### 7.2. Event-driven update model

Используется **event sourcing-light** подход:

```
PlanningEvent {
  event_id, scenario_id, timestamp, actor,
  type (one of above),
  payload (старое значение, новое значение, затронутые id),
}
```

Каждое событие проходит через **reducer pipeline**:

```
[ingest] → [validate] → [apply to canonical state]
       → [identify affected closure]
       → [recompute scheduling on closure]
       → [recompute allocations on closure]
       → [recompute conflicts on closure]
       → [emit deltas to UI]
```

Каждый шаг — pure function. Поэтому история событий + reducer = воспроизводимое состояние плана в любой момент. Это даёт **time-travel debugging** и поддерживает требование объяснимости.

### 7.3. Auto-shift зависимых задач

При сдвиге задачи `T` на `Δd` дней:

1. **Forward shift** (T закончилась позже, чем планировалось):
   - Все потомки по FS пересчитываются: `ES_succ ≥ EF_T_new + lag`.
   - Если у потомка был slack ≥ Δd — он просто «съедается», даты потомка не меняются.
   - Если slack < Δd — потомок сдвигается на `(Δd − slack)`.
   - Каскад продолжается до листьев. Для критического пути это означает сдвиг всего хвоста проекта.

2. **Backward shift** (T закончилась раньше — реже встречается):
   - Потомки могут стартовать раньше, если они в режиме ASAP.

3. **Constraints check**: если auto-shift нарушает `MUST_FINISH_ON` или `Due date` потомка — генерируется конфликт `DEAD.MISS`.

### 7.4. Recompute конфликтов

После любого shift пересчитываются конфликты только в окне `[min(старый ES), max(новый EF)] ± buffer` — нет смысла трогать задачи, на которые изменение не повлияло. Это inkremental conflict detection.

### 7.5. Стратегии реакции на скоуп-чейнджи

| Тип изменения | Default-стратегия | Альтернатива |
|---|---|---|
| Добавлена задача в проект | Поставить в конец очереди (после задач на CP) | Manual: PM позиционирует через drag |
| Удалена задача | Зависимости с её участием помечаются `broken_link`, потомки могут стартовать раньше | — |
| Удалена зависимость | Граф пересчитывается, slack’и перераспределяются | — |
| Изменена приоритезация проектов | Полный re-leveling | — |
| Длительный absence ключевого ресурса | Auto-leveling попытается reassign; если невозможно — конфликт | Manual reassignment |

### 7.6. Защита от «штормов» событий

При массовых импортах из Jira (например, восстановление backup’а) webhook’и могут прийти тысячами в минуту. RPM применяет:
- **Debouncing**: события на одну задачу за < 500ms объединяются.
- **Batch reducer**: при > N событий в окне — применяются батчем с одним финальным recompute.
- **Coalescing на уровне closure**: если два события затрагивают пересекающиеся подграфы — пересчёт проводится по объединению.

---

## 8. Capacity Planning (Quarter Level)

### 8.1. Demand vs Capacity модель

На уровне квартала ключевая абстракция — **bucketized supply/demand grid**:

```
Grid[role × week] = (demand_hours, capacity_hours, gap)
```

Где bucket — `(role, team, week)` или `(skill, week)`.

**Capacity** для bucket:
```
capacity = Σ resources_in_bucket( capacity_per_day_h × working_days_in_week × availability_factor )
```

**Demand** для bucket:
```
demand = Σ tasks_active_in_week( hours_required_in_role_in_week )
```

Где `hours_required_in_role_in_week` берутся из allocations, но если задача еще не назначена — из `required_role` и распределения её часов по календарной неделе по профилю нагрузки.

### 8.2. Метрики и формулы

| Метрика | Формула | Смысл |
|---|---|---|
| **Utilization** | `demand / capacity × 100%` | Загрузка bucket’а. Целевой коридор — 75–85%. |
| **Capacity Gap** | `capacity − demand` | Если < 0 — нехватка людей. |
| **Overallocation %** | `max(0, (demand − capacity) / capacity) × 100%` | Степень превышения. |
| **Underutilization %** | `max(0, (capacity − demand) / capacity) × 100%` | Простой. |
| **Demand smoothness (CV)** | `σ(demand_per_week) / μ` | Чем выше — тем хуже сглажена нагрузка. |
| **Skill coverage** | `Σ tasks_with_skilled_match / Σ tasks` | Доля задач с подходящими скиллами. |
| **Effective availability** | `working_days × availability_factor` | Реальная доступность ресурса. |
| **Critical Path Buffer Index** | `slack_total_quarter / duration_quarter` | Запас по времени на квартал. |

### 8.3. Идентификация overloaded / underutilized teams

**Overloaded**: команды/роли с `utilization > 100%` хотя бы в N последовательных неделях квартала или со средней utilization > 95%.

**Underutilized**: utilization < 60% средняя за квартал — кандидаты на переброс задач или разгрузку других команд.

**Skill bottleneck**: ситуация, когда demand на конкретный скилл превышает sum capacity всех ресурсов с этим скиллом независимо от роли. Часто это «один senior на десять команд» — самый болезненный паттерн.

Все три отображаются в **Capacity Heatmap** — матрице `(team × week)` с цветовой шкалой.

### 8.4. What-if сценарии

Сценарий — это форк baseline’а с набором overrides. Поддерживаемые изменения:

| Override | Эффект |
|---|---|
| **Add resource** | Виртуальный новый человек с заданной capacity и скиллами — отвечает на «что если наймём?» |
| **Remove resource** | Имитация ухода / болезни. |
| **Shift project** | Сдвиг project.start_target — что если отложить проект на 2 недели? |
| **Drop project** | Полное удаление проекта из квартала — что если откажемся? |
| **Change priority** | Re-leveling даст новую картину. |
| **Change estimates** | Что если эта команда на 30% оптимистичнее своих оценок? |
| **Resize team** | Добавление K универсальных ресурсов — для общих оценок. |
| **Calendar override** | «Что если в августе все в отпусках?» |
| **Скоуп-чендж** | Добавить N задач из бэклога в проект. |

Сценарий хранится как diff поверх baseline; при пересчёте применяется overlay → recompute. Можно строить дерево сценариев (S0 → S1 → S2). По образцу Atlassian Plans, изменения в сценарии не пишутся в Jira до явного commit’а.

### 8.5. Сравнение сценариев

UI «Scenario Comparator» — side-by-side представление:

| Метрика | Baseline | Scenario A | Scenario B |
|---|---|---|---|
| Project end date | 30 июня | 28 июня | 5 июля |
| Critical path длина | 67 дней | 65 дней | 71 день |
| Кол-во проектов в срок | 3 / 5 | 4 / 5 | 5 / 5 |
| Avg utilization | 92% | 87% | 78% |
| Pick load | 145% | 118% | 99% |
| Conflicts (critical) | 7 | 3 | 0 |
| Cost / total hours | 12 400h | 12 100h | 14 800h |
| Skill bottlenecks | 2 | 1 | 0 |

Визуально — Gantt-overlay (две полосы — baseline и scenario), heatmap-diff (зелёные/красные клетки — улучшилось/ухудшилось).

### 8.6. Итерационный workflow capacity planning

```
1. Initial load квартала → начальный schedule (ASAP, без leveling) → baseline B0
2. Run conflict detection → видны overloads и deadline misses
3. Run leveling → получаем feasible plan → baseline B1
4. PM создаёт what-if scenarios для рисковых проектов
5. Сравнение сценариев → принятие решения (нанять / перенести / урезать)
6. Commit выбранного сценария → baseline B2 = «обещание квартала»
7. В течение квартала — replanning через event-driven loop, drift против B2
```

---

## 9. Example Walkthrough

Демонстрация работы на маленьком, но реалистичном датасете.

### 9.1. Входные данные

**Проекты (3, утверждены на квартал):**

| ID | Имя | Priority | Start target | End target |
|---|---|---|---|---|
| P1 | Payment Refactor | 1 (high) | 2026-01-06 | 2026-03-13 |
| P2 | Mobile Onboarding | 2 | 2026-01-06 | 2026-02-27 |
| P3 | Internal Dashboard | 3 | 2026-01-20 | 2026-03-31 |

**Ресурсы (5):**

| ID | Имя | Роль | Скиллы | Capacity (h/d) | Avail factor |
|---|---|---|---|---|---|
| R1 | Анна | Backend | java, kafka, sql | 6 | 0.9 |
| R2 | Борис | Backend | java, sql | 6 | 1.0 |
| R3 | Вера | Frontend | react, typescript | 6 | 1.0 |
| R4 | Глеб | Mobile | swift, kotlin | 6 | 0.85 |
| R5 | Дина | QA | api-testing, e2e | 6 | 1.0 |

Все на дефолтном календаре пн-пт, 8 часов. Праздник 23 февраля.

**Задачи (12):**

| Key | Project | Тип | Estimate (h) | Required role | Assignee | Deps |
|---|---|---|---|---|---|---|
| PAY-1 | P1 | Story | 24h | Backend | Анна | — |
| PAY-2 | P1 | Story | 16h | Backend | Анна | FS PAY-1 |
| PAY-3 | P1 | Story | 32h | Backend | (none) | FS PAY-1 |
| PAY-4 | P1 | Story | 16h | QA | Дина | FS PAY-2, FS PAY-3 |
| MOB-1 | P2 | Story | 40h | Mobile | Глеб | — |
| MOB-2 | P2 | Story | 24h | Frontend | Вера | SS MOB-1 |
| MOB-3 | P2 | Story | 8h | QA | Дина | FS MOB-1, FS MOB-2 |
| DSH-1 | P3 | Story | — (нет estimate) | Backend | (none) | — |
| DSH-2 | P3 | Story | 13 SP | Frontend | Вера | FS DSH-1 |
| DSH-3 | P3 | Story | 16h | Backend | Борис | SS DSH-1 |
| DSH-4 | P3 | Story | 8h | QA | (none) | FS DSH-2, FS DSH-3 |
| DSH-5 | P3 | Bug | 4h | Backend | Анна | (нет связи, parallel) |

### 9.2. Этап 1 — Normalization и DQ

- DSH-1: нет estimate → подстановка медианы (8h по историческим Backend Story в P3 — по аналитической БД), флаг `estimate_default`.
- DSH-2: 13 SP → conversion: средний P3 velocity team = 1 SP ≈ 4h → 52h. Флаг `estimate_inferred`.
- PAY-3, DSH-1, DSH-4: assignee=null → `no_assignee`, идут в virtual pool по role.
- DSH-5: нет ссылок — task ставится параллельно остальным. Это нормальный случай.
- Все ссылки `Blocks` маппятся на FS, `Starts with` (custom) у MOB-2 → SS.

### 9.3. Этап 2 — Forward / Backward Pass (без ресурсного levelling)

Конвертация estimate → duration (при units=1, capacity 6h/d, avail 0.9 для R1):

| Task | Hours | Assignee | Capacity eff. | Duration (рабочих дней) |
|---|---|---|---|---|
| PAY-1 | 24 | Анна | 5.4 | 5 |
| PAY-2 | 16 | Анна | 5.4 | 3 |
| PAY-3 | 32 | pool | 6.0 | 6 |
| PAY-4 | 16 | Дина | 6.0 | 3 |
| MOB-1 | 40 | Глеб | 5.1 | 8 |
| MOB-2 | 24 | Вера | 6.0 | 4 |
| MOB-3 | 8 | Дина | 6.0 | 2 |
| DSH-1 | 8 | pool | 6.0 | 2 |
| DSH-2 | 52 | Вера | 6.0 | 9 |
| DSH-3 | 16 | Борис | 6.0 | 3 |
| DSH-4 | 8 | pool | 6.0 | 2 |
| DSH-5 | 4 | Анна | 5.4 | 1 |

**Forward pass** (project P1, старт 2026-01-06 = вторник):

```
PAY-1: ES=Jan 06 → EF=Jan 12 (5 раб. дн.: 6,7,8,9,12)
PAY-2: ES=Jan 13 → EF=Jan 15 (3 дн.)
PAY-3: ES=Jan 13 → EF=Jan 21 (6 дн., есть 19=пн, 20, 21)
PAY-4: ES=max(EF PAY-2=Jan 15, EF PAY-3=Jan 21) → ES=Jan 22 → EF=Jan 26
```

Аналогично для P2, P3. **Project end dates (initial)**: P1 = Jan 26, P2 = Feb 03, P3 = Mar 04.

**Backward pass** даёт LF/LS, например для PAY-2: EF=Jan 15, LF=Jan 21 (PAY-4 LS), slack = 4 дня. PAY-3: slack = 0 → critical. Critical path P1: PAY-1 → PAY-3 → PAY-4. P2: MOB-1 → MOB-3. P3: DSH-1 → DSH-2 → DSH-4.

### 9.4. Этап 3 — Resource Allocation

Auto-assignment для PAY-3, DSH-1, DSH-4:
- PAY-3 (Backend, 32h): кандидаты Анна (overload risk, уже на PAY-1, PAY-2), Борис (свободен в этом окне). Score:
  - Анна: skill=1.0, avail=0.3 (занята), velocity=1.1, load=high, switches=0 → score=низкий.
  - Борис: skill=0.9, avail=0.95, velocity=1.0, load=low, switches=+1 (новый проект для него) → score=высокий.
  → Назначен **Борис**, source=`auto-role`.
- DSH-1 (Backend, 8h, default estimate): кандидаты Анна, Борис. Анна свободна с Jan 27, Борис свободен после PAY-3 (с Jan 22 до Jan 21 он занят? нет, PAY-3 ES=Jan 13–EF=Jan 21, потом свободен с Jan 22). DSH-1 ES=2026-01-20 (P3.start). Берём Анну (после PAY-2 свободна с Jan 16). → **Анна**.
- DSH-4 (QA, 8h): только Дина. → **Дина**.

### 9.5. Этап 4 — Conflict Detection

После allocation запускаем detector:

| День | Ресурс | Загрузка | Конфликт |
|---|---|---|---|
| Jan 13–15 | Анна | PAY-2 (1.0) | ok |
| Jan 13–21 | Борис | PAY-3 (1.0) | ok |
| Jan 22–26 | Дина | PAY-4 (1.0) | ok |
| Jan 26–Feb 04 | Глеб | MOB-1 (1.0) | ok |
| Jan 26–30 | Вера | MOB-2 (1.0, но SS, идёт параллельно с MOB-1) | ok |
| Feb 05–06 | Дина | MOB-3 (1.0) | ok |
| Feb 09–17 | Вера | DSH-2 (1.0) | ok |
| Jan 20–21 | Борис | DSH-3 (SS DSH-1, ES=Jan 20) + PAY-3 (всё ещё активна!) | **OVR.HIGH 200%** |
| Mar … | Анна | DSH-5 (Bug, parallel, ставим как ASAP=Jan 06) — конфликт с PAY-1 | **OVR.HIGH** |

Обнаружены два critical конфликта:
1. Борис: с Jan 20 по Jan 21 одновременно PAY-3 и DSH-3 (200%).
2. Анна: DSH-5 поставился на Jan 06, но PAY-1 уже занимает её — overlap 1 день.

### 9.6. Этап 5 — Leveling

Detector передаёт конфликты в Leveling Engine.

**Конфликт 1 (Борис).** Приоритеты: P1 (priority 1) > P3 (priority 3). DSH-3 имеет slack (DSH-4 ES=Feb 18, DSH-3 EF=Jan 22 → slack ≈ 18 рабочих дней). Стратегия — delay DSH-3 на 2 дня (до Jan 22, после окончания PAY-3). Slack DSH-3 уменьшается, но остаётся +16 дней. **Resolved by delay.**

**Конфликт 2 (Анна, DSH-5).** DSH-5 не имеет deps. Slack велик (вся дельта до конца квартала). Стратегия — delay до момента, когда Анна освободится. Анна занята PAY-1 (до Jan 12), затем PAY-2 (до Jan 15), затем DSH-1 (Jan 20–21). DSH-5 ставится на Jan 22 (1 день). **Resolved by delay.**

После leveling — все ресурсы ≤ 100% загрузки.

### 9.7. Этап 6 — Gantt Output

Финальный план (упрощённо):

```
Янв       06 07 08 09 12 13 14 15 16 19 20 21 22 23 26 27 28 29 30 ...
PAY-1 (А) ████████████
PAY-2 (А)              ██████
PAY-3 (Б)              ███████████████ ← critical (CP красный)
PAY-4 (Д)                                ██████████ ← critical
MOB-1 (Г)                                            ████████████████
MOB-2 (В)                                            ██████████ (SS)
MOB-3 (Д)                                                              ████
DSH-1 (А)                              ████ (auto-assigned)
DSH-2 (В)                                          █████████████████
DSH-3 (Б)                                  ██████ (delayed by leveling)
DSH-4 (Д)                                                          ████
DSH-5 (А)                                  █ (delayed by leveling)
```

В Gantt для каждой DSH-* виден badge `auto-assigned` или `estimate_inferred`, для DSH-1 — `estimate_default`. Все три проекта укладываются в свои end_target. Critical path P1: PAY-1 → PAY-3 → PAY-4. Slack tail у некритических задач визуализирован.

В Capacity Heatmap (по неделям):

| Ресурс | W2 | W3 | W4 | W5 | W6 | W7 |
|---|---|---|---|---|---|---|
| Анна | 100% | 100% | 75% | — | — | — |
| Борис | — | 100% | 100% | — | — | — |
| Вера | — | — | — | 100% | 100% | 100% |
| Глеб | — | — | — | 100% | 100% | — |
| Дина | — | — | 60% | 40% | — | — |

Дина недозагружена → underutilized → может быть привлечена к доп. задачам или другому проекту в what-if сценарии.

### 9.8. Этап 7 — What-If пример

Сценарий: «Что если Глеб уходит в отпуск с 1 по 7 февраля?»

После применения override:
- MOB-1 не помещается в окно → его EF уезжает на Feb 09 → MOB-3 (CP) сдвигается → **проект P2 рискует не уложиться**.
- Конфликт `DEAD.MISS` — slack у MOB-3 теперь отрицательный.
- Рекомендация автоматически: либо нанять второго Mobile-разработчика (попробуйте — добавьте virtual resource), либо урезать scope MOB-1.

Сравнение сценариев в Comparator показывает: baseline finishes Feb 03, scenario finishes Feb 11, conflicts +2.

---

## 10. Limitations & Improvements + сравнение с MS Project

### 10.1. Сравнительная матрица возможностей

| Категория | MS Project (полный desktop) | Primavera P6 | Jira Plans / Advanced Roadmaps | BigPicture / Structure.Gantt | **Предлагаемый RPM** |
|---|---|---|---|---|---|
| **Источник данных** | Собственный .mpp | Собственная БД | Jira issues | Jira issues | Jira issues + аналитическая БД |
| **CPM / forward-backward pass** | Да, полный | Да, расширенный | Нет (rank-based scheduler) | Да (BigPicture, Gantt+Structure) | **Да, полный + Resource-CP + PERT** |
| **Типы зависимостей FS/SS/FF/SF** | 4 типа + lag/lead | 4 типа + lag/lead | Только blocks (sequential/concurrent) | FS+SS+FF (BigPicture) | **4 типа + lag/lead** |
| **Auto-leveling** | Да (Standard/Priority алгоритм) | Да, продвинутый | Частично (rank-based) | Да (BigPicture Resources) | **Да, multi-project, RCPSP-эвристика** |
| **Auto-assignment по скиллам** | Базовый (через resource pool) | Через roles | Нет (только команды) | Базовый | **Да, многокритериальный скоринг** |
| **Multi-project resource pool** | Да | Да | Через teams | Да | **Да** |
| **What-if сценарии** | Через копию плана | Yes, многосценарный | Да (sandbox) | Да (BigPicture) | **Да, с deep diff** |
| **Sравнение сценариев** | Через baselines (до 11) | Через baselines | Базовое | Базовое | **Side-by-side с метриками** |
| **Baselines** | До 11 baselines | Да, многоверсионные | Базовый snapshot | Да (BigPicture: один baseline на task) | **Многоуровневые** |
| **EVM (Earned Value)** | Да, полный | Да, полный | Нет | Базовый | **Не в MVP, рекомендация** |
| **Ресурсы: cost / rate / overtime** | Да | Да | Нет | Базовый | **Cost — опционально, overtime — нет в MVP** |
| **Material/Cost/Work resources** | 3 типа | Все типы | Нет | Только Work | **Только Work** |
| **Fixed-duration vs fixed-work** | 3 task type’а (Fixed Duration, Fixed Units, Fixed Work) | Полная свобода | Нет | Нет | **Только Fixed Work** (упрощение) |
| **Calendars: project / resource / task** | 3 уровня | 3 уровня | Простые sprint dates | Project + Resource | **Project + Resource (без task-level)** |
| **Probabilistic CPM (PERT/Monte-Carlo)** | Через Add-ins | Через P6 Risk | Нет | Нет | **Опционально, как продвинутый режим** |
| **Объяснимость (почему задача здесь)** | Слабая | Средняя | Слабая | Средняя | **Сильная — first-class feature** |
| **Read-only поверх системы записи** | Self-contained | Self-contained | Sandbox-mode | Sandbox-mode | **Sandbox-mode** |
| **Real-time updates (event-driven)** | Нет | Нет (batch) | Частично | Частично | **Да, webhook-driven** |
| **Масштаб 1k+ задач** | Да | 100k+ | 1k–5k | 5k+ | **Дизайн на 5k+** |

### 10.2. Что упрощено относительно MS Project

| Упрощение | Почему | Последствие |
|---|---|---|
| **Один тип задачи — Fixed Work** (effort-driven), без Fixed Duration / Fixed Units | В Jira нативно живёт effort (estimate). Fixed Duration требует семантики «эта задача всегда 5 дней независимо от ресурсов» — её в Jira нет | Нельзя моделировать события/encembly-задачи, длительность которых не зависит от effort |
| **Только Work resources** (люди и роли), без Material/Cost | Jira не оперирует материалами | Бюджетирование по материалам и оборудованию вне scope |
| **Нет task-level calendars**, только resource и project | Усложнение, редко используется | Невозможно сказать «эта задача может выполняться 24/7 несмотря на календарь ресурса» |
| **Один уровень scheduling priority** (через Project.priority + Task.priority), без MS Project «Priority 1–1000» | Достаточно для большинства кейсов | Меньшая тонкость в leveling |
| **Базовый baseline mechanism**, без 11 параллельных baseline’ов MS Project | Многобейзлайны редко используются | Можно сделать N baseline’ов в дизайне, но интерфейс упрощён |
| **Нет lag в формате процентов** (только дни/часы) | Проценты сложны и редки в IT-проектах | — |
| **Splits (разбиение задачи на куски)** опционально и осторожно | В Jira нет нативной поддержки разрывов; разбиение требует sub-task’ов | Auto-leveling предпочитает delay, чем split |
| **Effort-driven scheduling без recalibration units** | MS Project пересчитывает units при добавлении ресурса; в RPM это явный шаг | Меньше «магии», больше контроля |
| **Нет deadline-style finish constraints с hard penalty** (только soft warning) | Чтобы не блокировать planning при нереалистичных дедлайнах | Конфликты вместо ошибок |

### 10.3. Что отсутствует совсем (рекомендации к будущим версиям)

| Не реализовано | Рекомендация |
|---|---|
| **EVM (Earned Value Management)** — PV, EV, AC, CPI, SPI | Добавить в фазу 2; данные для AC уже есть в Jira worklogs, для PV — в плане |
| **Cost & budget tracking** | Добавить cost_rate в Resource, бюджеты в Project. Roll-up cost по WBS |
| **Risk register с привязкой к задачам и Monte-Carlo** | Расширить Conflict-объект до Risk-объекта с probability/impact |
| **Resource overtime model** | Сейчас > 100% = конфликт; в фазе 2 — допускать controlled overtime со штрафом в objective |
| **Cross-team contracts (SLA на доступность)** | Полезно для shared services (DevOps, дизайн) |
| **AI-based estimate forecasting** | Использовать аналитическую БД для ML-модели «похожие задачи → ожидаемая длительность с CI» |
| **Probabilistic CP по умолчанию** | Сейчас — опция; в фазе 2 сделать default view |
| **Drag-and-drop split** | Нет в MVP, нужна сложная UX-логика |
| **Bulk what-if по «топ-10 рисков»** | Автогенерация типовых сценариев («что если ключевой человек уволится?») |

### 10.4. Что сделано лучше под Jira

| Улучшение | Почему это лучше |
|---|---|
| **Native event-driven replanning** | MS Project / P6 — batch-инструменты. RPM реактивен на webhooks Jira, что соответствует agile-ритму. |
| **Data Quality first-class** | MS Project предполагает чистые данные. RPM прямо моделирует missing/inferred/default и явно показывает их в Gantt — это уникально для среды, где данные грязные by design. |
| **Sandbox-семантика** | Любые changes в RPM не пишутся в Jira до commit. Это повторяет паттерн Plans/Advanced Roadmaps, но с полноценным CPM, чего у Plans нет. |
| **Multi-project leveling из коробки** | MS Project делает это через master project; в RPM это базовый use case (квартальный портфель). |
| **Объяснимость как требование** | MS Project часто работает как black box leveling. RPM по дизайну даёт ответ «почему задача здесь и почему этот ресурс». |
| **Hierarchy-aware (Epic → Story → Sub-task)** | Jira-нативная иерархия используется напрямую как WBS. В MS Project WBS — отдельная сущность, в RPM — это Jira-структура. |
| **Sprint-aware** | RPM понимает спринты как мягкие constraints (issue без даты, но в спринте → даты спринта). MS Project не знает про спринты. |
| **Skill matrix + auto-assignment с скорингом** | В MS Project assignment ручной или basic Resource Engagements. RPM делает многокритериальный recommend, объясняя выбор. |
| **Аналитическая БД как fallback для оценок** | MS Project не имеет источника исторических данных. RPM использует историю как «учитель» для inference. |
| **Conflict register как first-class объект** | MS Project показывает overallocation, но не материализует конфликты как сущности с владельцами и историей. |

### 10.5. Edge cases, не покрытые в концептуальном дизайне

Их нужно явно обсуждать в детальном дизайне:

1. **Циклы в Jira-связях, индуцированные через Epic-Story-blocks-Story-другого-Epic.** Логика разрыва ребра должна выбирать «какое именно ребро резать», иначе результаты непредсказуемы.
2. **Ресурс с переменной capacity** (например, 100% в первые 2 месяца, 50% в третий из-за parental leave). Текущая модель Calendar+Availability покрывает это, но нужна удобная UX-форма для ввода.
3. **Distributed teams с разными timezone’ами**. Часы пересечения важны для тасок, требующих pair-work. Не моделируется.
4. **Long-running maintenance tasks** (типа «on-call» 24×7) — не дискретны, конфликтуют с любой allocation. Нужна спец-семантика «background allocation».
5. **Joint allocation на одну задачу нескольких ресурсов с разной long-of-work**. Сейчас допускается несколько Allocation на одну Task, но координация их sub-windows нетривиальна.
6. **Зависимости между разными квартальными планами** (cross-quarter projects). Текущий scope — один квартал.
7. **Manual override’ы и их «прилипание»** — если PM руками сдвинул задачу, надо ли её дальше двигать auto-leveling’у? Нужны explicit pin/unpin маркеры.
8. **Concurrent edits** двух пользователей в одном сценарии. Optimistic lock или CRDT — отдельный design.
9. **Импорт исторических baseline’ов из MS Project** — для миграции инструмента.
10. **Очень короткие задачи (< 1 day)** — могут вызывать численные артефакты в leveling; стоит установить минимальный bucket.

### 10.6. Рекомендации по поэтапному внедрению (roadmap)

| Фаза | Содержание | Зачем |
|---|---|---|
| **MVP (фаза 1)** | L1–L4 в базовом виде; CPM с FS/SS/FF/SF; manual + simple auto-assignment; basic leveling (priority-rule SGS); single-project Gantt; conflict detector с базовыми типами | Доказать ценность за 2–3 месяца |
| **Фаза 2** | Multi-project leveling; RCPSP genetic optimization batch-mode; Resource-CP; what-if + scenario comparator; capacity heatmap; baselines; Drag-Gantt | Полный заявленный scope |
| **Фаза 3** | Probabilistic CPM/Monte-Carlo; ML-forecasting estimates; cost/EVM; risk register; advanced calendars; export to MS Project XML | Enterprise-grade |
| **Фаза 4** | Cross-quarter planning; portfolio scoring; integration with HR/timesheet systems; AI-assisted scenario generation | Стратегический PPM |

### 10.7. Резюме

Предложенная архитектура опирается на четыре проверенные группы практик:

1. **Классические алгоритмы PM** (CPM, PERT, RCPSP) — дают математическую корректность и переносимый набор метрик (slack, critical path, utilization).
2. **MS Project / Primavera best practices** — типы зависимостей, scheduling modes, leveling priority rules, baselines.
3. **Jira-нативные паттерны** (Plans, BigPicture, Structure.Gantt) — sandbox-семантика, sprint-awareness, иерархия эпиков, JQL-источники, webhook-driven обновления.
4. **Современные принципы data-driven систем** — event-sourcing, инкрементальный пересчёт, явная модель качества данных, объяснимость как first-class требование.

В отличие от MS Project, RPM не пытается быть универсальным планировщиком на все случаи жизни. Его фокус — **forward-looking планирование портфеля проектов в среде Jira с грязными данными и agile-ритмом изменений**. Сознательные упрощения (один тип задач, отсутствие material resources, отсутствие task-level calendars) делают систему понятной и масштабируемой; при этом за счёт встроенной аналитической БД, native multi-project leveling, объяснимых конфликтов и first-class scenarios она в своей нише превосходит и MS Project, и существующие Jira-плагины.

Документ описывает концепцию и логику; следующий шаг — детальный design каждого компонента (схема БД, API ingestion, конкретные алгоритмы leveling, прототипы UI), который должен опираться на эту архитектуру как на каркас.